"""
DigiBioFi — FastAPI application factory.

Run locally:
    uvicorn app.main:app --reload

Production:
    gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4
"""
import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Tuple

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.owner import apply_owner_access, is_owner_email
from app.core.security import AUTH_COOKIE_NAME, clear_auth_cookie, clear_csrf_cookie
from app.core.templates import templates
from app.db.database import engine
from app.db.schema import assert_schema_ready
from app.routers import auth, dashboard, public, admin, billing, legal
from app.core.dependencies import get_current_user_optional, get_db

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Application lifespan ──────────────────────────────────────────────────────

def _owner_username() -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]", "", settings.admin_email.split("@", 1)[0]).strip()
    return base or "owner"


def _unique_username(base: str, db) -> str:
    from app.models.user import User

    username = base
    suffix = 1
    while db.query(User).filter(User.username == username).first():
        username = f"{base}{suffix}"
        suffix += 1
    return username


def _seed_admin_user():
    """Ensure the configured owner account exists with permanent elite access."""
    from app.db.database import SessionLocal
    from app.core.security import hash_password
    from sqlalchemy import func

    db = SessionLocal()
    try:
        from app.models.user import User
        from app.models.profile import Profile
        from app.services import qr_service
        from app.utils.slug import unique_slug

        user = (
            db.query(User)
            .filter(func.lower(User.email) == settings.admin_email.lower())
            .first()
        )
        if not user:
            username = _unique_username(_owner_username(), db)
            user = User(
                email=settings.admin_email.lower(),
                username=username,
                hashed_password=hash_password(settings.admin_password),
                role="admin",
                subscription_tier="elite",
                subscription_status="active",
                is_active=True,
                is_verified=False,
            )
            db.add(user)
            db.flush()
            profile = Profile(user_id=user.id, slug=unique_slug(username, db))
            db.add(profile)
            db.commit()
            db.refresh(user)
            db.refresh(profile)
            try:
                qr_service.generate_qr_for_profile(profile, db)
            except Exception as e:
                logger.warning(f"Owner QR seed failed: {e}")
            logger.info("Owner account created")
            return

        changed = apply_owner_access(user)
        profile = user.profile
        if not profile:
            profile = Profile(user_id=user.id, slug=unique_slug(user.username, db))
            db.add(profile)
            changed = True

        if changed:
            db.commit()
            db.refresh(user)
            db.refresh(profile)
            logger.info("Owner access ensured")

        if profile and not profile.qr_code:
            try:
                qr_service.generate_qr_for_profile(profile, db)
            except Exception as e:
                logger.warning(f"Owner QR sync failed: {e}")
    except Exception as e:
        logger.warning(f"Admin seed failed: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup requires a migrated schema.
    """
    # Import models so relationship access in startup paths is registered.
    import app.models as app_models  # noqa: F401

    for sub in ("profile_images", "qr_codes", "resumes", "certificates", "project_thumbnails"):
        (settings.upload_path / sub).mkdir(parents=True, exist_ok=True)

    if settings.free_daily_profile_view_limit < 1:
        raise RuntimeError("FREE_DAILY_PROFILE_VIEW_LIMIT must be at least 1.")

    stripe_enabled = bool(
        settings.stripe_webhook_secret.strip()
        or settings.stripe_price_basic.strip()
        or settings.stripe_price_elite.strip()
        or settings.stripe_price_premium.strip()
    )
    if stripe_enabled and not settings.stripe_secret_key.strip():
        raise RuntimeError("Stripe is enabled but STRIPE_SECRET_KEY is missing.")

    if app.state.environment != "testing":
        if not settings.adsense_client_id.strip():
            logger.warning("AdSense not configured; ad placements remain disabled.")
        elif not any(
            slot.strip()
            for slot in (
                settings.adsense_public_inline_slot,
                settings.adsense_public_sidebar_slot,
                settings.adsense_dashboard_slot,
            )
        ):
            logger.warning("AdSense client configured without any slots; ad placements remain disabled.")

        if (
            settings.smtp_host == "smtp.example.com"
            or not settings.smtp_user.strip()
            or not settings.smtp_password.strip()
        ):
            logger.warning("Email is not fully configured; email delivery features remain disabled.")

    if app.state.environment != "testing":
        assert_schema_ready(engine)
        _seed_admin_user()

    logger.info(f"DigiBioFi starting — env={settings.app_env}, base_url={settings.base_url}")
    yield
    logger.info("DigiBioFi shutting down.")


# ── Rate Limiting ─────────────────────────────────────────────────────────────
# Simple in-memory rate limiter: {ip: (timestamp, count)}
# NOTE: This is memory-based and will reset on application restart or multiple
# workers. For a distributed production environment, use Redis-based limiting.
_rate_limits: Dict[str, Tuple[float, int]] = {}
_rate_limit_lock: asyncio.Lock | None = None


def _get_rate_limit_lock() -> asyncio.Lock:
    global _rate_limit_lock
    if _rate_limit_lock is None:
        _rate_limit_lock = asyncio.Lock()
    return _rate_limit_lock

def get_client_ip(request: Request) -> str:
    """
    Extract client IP from request, checking trusted proxy headers first.
    In production, this helps get the real client IP when behind a load balancer.
    """
    # Check X-Forwarded-For (most common with proxies)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs; use the first one
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP (used by some proxies)
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct connection IP
    if request.client:
        return request.client.host

    return "unknown"

def is_rate_limited(ip: str) -> bool:
    global _rate_limits
    if settings.app_env == "testing":
        return False
    now = time.time()
    
    # Cleanup old entries (every 1000 checks, remove entries older than 1 hour)
    if len(_rate_limits) % 1000 == 0:
        cutoff = now - 3600
        _rate_limits = {
            k: v for k, v in _rate_limits.items() if v[0] > cutoff
        }
    
    if ip not in _rate_limits:
        _rate_limits[ip] = (now, 1)
        return False

    last_reset, count = _rate_limits[ip]
    if now - last_reset > settings.rate_limit_seconds:
        _rate_limits[ip] = (now, 1)
        return False

    if count >= settings.rate_limit_requests:
        return True

    _rate_limits[ip] = (last_reset, count + 1)
    return False


async def rate_limiter(request: Request) -> JSONResponse | None:
    """Best-effort in-memory rate limiter that never breaks the request chain."""
    if request.app.state.environment == "testing":
        return None

    try:
        async with _get_rate_limit_lock():
            ip = get_client_ip(request)
            if is_rate_limited(ip):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please slow down."},
                )
    except Exception:
        logger.exception("Rate limiter failed")

    return None


def _apply_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    script_src = (
        "'self' 'unsafe-inline' https://cdn.tailwindcss.com "
        "https://unpkg.com https://cdnjs.cloudflare.com"
    )
    img_src = (
        "'self' data: blob: https://images.unsplash.com "
        "https://img.youtube.com https://i.vimeocdn.com"
    )
    connect_src = "'self'"
    frame_src = "'self'"

    if settings.adsense_client_id:
        script_src += " https://pagead2.googlesyndication.com"
        img_src += (
            " https://pagead2.googlesyndication.com"
            " https://tpc.googlesyndication.com"
            " https://googleads.g.doubleclick.net"
        )
        connect_src += (
            " https://pagead2.googlesyndication.com"
            " https://googleads.g.doubleclick.net"
        )
        frame_src += (
            " https://googleads.g.doubleclick.net"
            " https://tpc.googlesyndication.com"
        )

    csp = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        f"script-src {script_src}; "
        f"img-src {img_src}; "
        "font-src 'self' https://fonts.gstatic.com https://fonts.googleapis.com; "
        f"connect-src {connect_src}; "
        f"frame-src {frame_src}; "
        "frame-ancestors 'none';"
    )

    if settings.is_production:
        csp += " upgrade-insecure-requests;"

    response.headers["Content-Security-Policy"] = csp

    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

    return response


def _request_expects_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept or "application/xhtml+xml" in accept


def _response_is_html(response) -> bool:
    content_type = response.headers.get("content-type", "")
    return content_type.startswith("text/html")


def _apply_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _redirect_to_login() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    clear_auth_cookie(response)
    clear_csrf_cookie(response)
    response.delete_cookie("digibiofi_session", path="/")
    return _apply_no_cache_headers(response)


def _safe_error_response(request: Request, status_code: int = 500):
    if _request_expects_html(request):
        return templates.TemplateResponse(
            request=request, name="errors/500.html", context={"request": request},
            status_code=status_code,
        )
    return JSONResponse(
        status_code=status_code,
        content={"detail": "Internal server error"},
    )

# ── Rate Limiting ─────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    description="Digital resume & identity platform",
    version="1.0.0",
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# Set environment state for use in functions
app.state.environment = settings.app_env

# ── Middleware ────────────────────────────────────────────────────────────────

@app.middleware("http")
async def security_and_rate_limit_middleware(request: Request, call_next):
    auth_cookie_present = bool(request.cookies.get(AUTH_COOKIE_NAME))

    try:
        if not request.url.path.startswith("/admin"):
            limited_response = await rate_limiter(request)
            if limited_response is not None:
                return _apply_security_headers(limited_response)

        response = await call_next(request)
    except HTTPException as exc:
        if exc.status_code == 401 and _request_expects_html(request):
            response = _redirect_to_login()
        else:
            response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    except Exception:
        logger.exception("Unhandled request error")
        response = _safe_error_response(request, status_code=500)

    if response.status_code == 401 and _request_expects_html(request):
        response = _redirect_to_login()

    if auth_cookie_present and (_response_is_html(response) or _request_expects_html(request)):
        _apply_no_cache_headers(response)

    response = _apply_security_headers(response)

    if not request.cookies.get("csrf_token"):
        from app.core.security import generate_csrf_token, set_csrf_cookie

        token = getattr(request.state, "csrf_token", None) or generate_csrf_token(request)
        set_csrf_cookie(response, token)

    return response

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="digibiofi_session",
    max_age=3600 * 24 * 30, # 30 days
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ──────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Serve user uploads (profile images, QR codes, resumes) as static files.
# In production, offload this to nginx or a CDN.
_uploads_path = Path(settings.upload_dir)
_uploads_path.mkdir(exist_ok=True)
qr_path = settings.upload_path / "qr_codes"
qr_path.mkdir(parents=True, exist_ok=True)
for subdir in ("profile_images", "project_thumbnails", "certificates"):
    public_dir = settings.upload_path / subdir
    public_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        f"/uploads/{subdir}",
        StaticFiles(directory=str(public_dir)),
        name=f"uploads-{subdir}",
    )
app.mount("/qr_codes", StaticFiles(directory=str(qr_path)), name="qr_codes")


# ── Robots.txt ───────────────────────────────────────

from fastapi.responses import FileResponse

@app.get("/robots.txt")
def robots():
    return FileResponse("app/static/robots.txt")



# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(public.router)
app.include_router(admin.router)
app.include_router(billing.router)
app.include_router(legal.router)

# ── Stripe Webhook ───────────────────────────────────────────────────────────

def _get_user_by_stripe(db, customer_id: str | None, user_id_str: str | None):
    """Look up a User by Stripe customer ID or metadata user_id."""
    from app.models.user import User
    if customer_id:
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            return user
    if user_id_str:
        try:
            return db.query(User).filter(User.id == int(user_id_str)).first()
        except (ValueError, TypeError):
            pass
    return None


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request, db=Depends(get_db)):
    """
    Handle Stripe payment events to keep subscription state in sync.
    Signature verification is mandatory — set STRIPE_WEBHOOK_SECRET in .env.
    
    Webhook events are idempotent — duplicate event IDs are rejected to prevent
    processing the same event multiple times (Stripe retries on failure).
    """
    if not settings.stripe_webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured — webhook rejected")
        return JSONResponse({"error": "webhook not configured"}, status_code=400)

    try:
        import stripe
        stripe.api_key = settings.stripe_secret_key
        payload = await request.body()
        sig = request.headers.get("stripe-signature", "")
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except ImportError:
        return JSONResponse({"error": "stripe not installed"}, status_code=500)
    except Exception as e:
        logger.warning(f"Stripe webhook signature error: {e}")
        return JSONResponse({"error": "invalid"}, status_code=400)

    # Check if event has already been processed (idempotency)
    event_id = event.get("id")
    if event_id:
        from app.models.stripe import StripeEvent
        existing = db.query(StripeEvent).filter(StripeEvent.event_id == event_id).first()
        if existing:
            logger.debug(f"Stripe webhook event {event_id} already processed, skipping")
            return JSONResponse({"received": True})

    event_type = event["type"]
    obj = event["data"]["object"]

    # Wrap processing in a transaction
    try:
        if event_type == "checkout.session.completed":
            customer_id = obj.get("customer")
            subscription_id = obj.get("subscription")
            metadata = obj.get("metadata", {}) or {}
            plan = metadata.get("plan", "elite")
            tier = "elite" if plan != "basic" else "basic"
            user = _get_user_by_stripe(db, customer_id, metadata.get("user_id"))
            if user:
                if is_owner_email(user.email):
                    apply_owner_access(user)
                else:
                    user.subscription_tier = tier
                    user.subscription_status = "active"
                    if customer_id and not user.stripe_customer_id:
                        user.stripe_customer_id = customer_id
                    if subscription_id:
                        user.stripe_subscription_id = subscription_id
                logger.info(f"User {user.id} upgraded to {tier} via checkout.session.completed")
            else:
                logger.warning(f"checkout.session.completed: no user found for customer={customer_id}")

        elif event_type == "customer.subscription.updated":
            customer_id = obj.get("customer")
            subscription_id = obj.get("id")
            status = obj.get("status")  # active, past_due, canceled, unpaid, etc.
            user = _get_user_by_stripe(db, customer_id, None)
            if user:
                if is_owner_email(user.email):
                    apply_owner_access(user)
                else:
                    if subscription_id:
                        user.stripe_subscription_id = subscription_id
                    if status == "active":
                        user.subscription_status = "active"
                    elif status in ("past_due", "unpaid"):
                        user.subscription_status = status
                    elif status in ("canceled", "incomplete_expired"):
                        user.subscription_status = "canceled"
                        user.subscription_tier = "free"
                logger.info(f"User {user.id} subscription updated: status={status}")

        elif event_type == "customer.subscription.deleted":
            customer_id = obj.get("customer")
            user = _get_user_by_stripe(db, customer_id, None)
            if user:
                if is_owner_email(user.email):
                    apply_owner_access(user)
                else:
                    user.subscription_status = "canceled"
                    user.subscription_tier = "free"
                    user.stripe_subscription_id = ""
                logger.info(f"User {user.id} subscription deleted")

        elif event_type == "invoice.payment_failed":
            customer_id = obj.get("customer")
            user = _get_user_by_stripe(db, customer_id, None)
            if user:
                if is_owner_email(user.email):
                    apply_owner_access(user)
                else:
                    user.subscription_status = "past_due"
                    logger.warning(f"User {user.id} invoice payment failed — status set to past_due")

        # After successful processing, record the event ID for idempotency
        if event_id:
            from app.models.stripe import StripeEvent
            new_event = StripeEvent(event_id=event_id)
            db.add(new_event)
        
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing Stripe webhook {event_id}: {e}")
        return JSONResponse({"error": "processing failed"}, status_code=500)

    return JSONResponse({"received": True})


# ── Root redirect ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root(request: Request, user=Depends(get_current_user_optional)):
    """Landing page — redirect authenticated users to dashboard unless explicitly visiting."""
    # We still redirect to dashboard by default if they are logged in, 
    # but we pass user to the template just in case we ever want to show it.
    # Actually, the requirement suggests showing different buttons on the landing page based on state.
    # If we always redirect, they never see those buttons on the landing page.
    # So maybe we only redirect if they are not just browsing the root?
    # No, I'll stick to what the requirement says: show the correct button.
    # To show the button, they must be on the page.
    return templates.TemplateResponse(request=request, name="landing.html", context={"request": request, "user": user})


# ── Error handlers ────────────────────────────────────────────────────────────

@app.exception_handler(404)
def not_found(request: Request, exc):
    if not _request_expects_html(request):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    return templates.TemplateResponse(
        request=request, name="errors/404.html", context={"request": request}, status_code=404
    )


@app.exception_handler(500)
async def internal_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled 500 error", exc_info=exc)
    return _safe_error_response(request, status_code=500)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Global exception caught", exc_info=exc)
    return _safe_error_response(request, status_code=500)
