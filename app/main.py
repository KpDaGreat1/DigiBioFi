"""
DigiBioFi — FastAPI application factory.

Run locally:
    uvicorn app.main:app --reload

Production:
    gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4
"""
import logging
from dotenv import load_dotenv
load_dotenv()
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Tuple

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.templates import templates
from app.db.database import engine, Base
from app.routers import auth, dashboard, public, admin, billing
from app.core.dependencies import get_current_user_optional, get_db


# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Application lifespan ──────────────────────────────────────────────────────

def _run_startup_migrations():
    """Add any new columns that don't exist yet (safe for existing SQLite DBs)."""
    from sqlalchemy import text, inspect as sa_inspect
    # Ensure stripe_events table exists
    with engine.connect() as conn:
        insp = sa_inspect(conn)
        if "stripe_events" not in insp.get_table_names():
            conn.execute(text("""
                CREATE TABLE stripe_events (
                    event_id VARCHAR(255) PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_stripe_event_id ON stripe_events(event_id)"))
            conn.commit()
            logger.info("Migration: created stripe_events table")
    
    with engine.connect() as conn:
        inspector = sa_inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("profiles")]
        
        new_cols = [
            ("recruiter_visibility", "BOOLEAN DEFAULT 0"),
            ("freelance_availability", "BOOLEAN DEFAULT 0"),
            ("profile_image_2", "VARCHAR(500) DEFAULT ''"),
            ("profile_image_3", "VARCHAR(500) DEFAULT ''"),
            ("custom_background_url", "VARCHAR(500) DEFAULT ''"),
            ("custom_header_url", "VARCHAR(500) DEFAULT ''"),
        ]
        
        for col_name, col_type in new_cols:
            if col_name not in columns:
                try:
                    conn.execute(text(f"ALTER TABLE profiles ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    logger.info(f"Migration: Added {col_name} to profiles table")
                except Exception as e:
                    logger.error(f"Migration failed for {col_name}: {e}")
    with engine.connect() as conn:
        insp = sa_inspect(conn)
        # educations.certificate_url
        edu_cols = [c["name"] for c in insp.get_columns("educations")]
        if "certificate_url" not in edu_cols:
            conn.execute(text("ALTER TABLE educations ADD COLUMN certificate_url TEXT DEFAULT ''"))
            conn.commit()
            logger.info("Migration: added educations.certificate_url")

        # users additional billing/subscription columns
        user_cols = [c["name"] for c in insp.get_columns("users")]

        if "stripe_customer_id" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT DEFAULT ''"))
            conn.commit()
            logger.info("Migration: added users.stripe_customer_id")
            user_cols = [c["name"] for c in sa_inspect(conn).get_columns("users")]

        if "stripe_subscription_id" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN stripe_subscription_id TEXT DEFAULT ''"))
            conn.commit()
            logger.info("Migration: added users.stripe_subscription_id")
            user_cols = [c["name"] for c in sa_inspect(conn).get_columns("users")]

        if "subscription_status" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN subscription_status TEXT DEFAULT 'inactive'"))
            conn.commit()
            logger.info("Migration: added users.subscription_status")


def _seed_admin_user():
    """Ensure Antawnharris1992@gmail.com has admin role."""
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        from app.models.user import User
        admin_email = "Antawnharris1992@gmail.com"
        user = db.query(User).filter(User.email == admin_email).first()
        if user:
            if user.role != "admin":
                user.role = "admin"
                user.subscription_tier = "elite"
                db.commit()
                logger.info(f"Admin role assigned to {admin_email}")
        else:
            logger.debug(f"Admin seed: user {admin_email} not registered yet")
    except Exception as e:
        logger.warning(f"Admin seed failed: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: create tables (dev only — use Alembic for production).
    Ensure upload directories exist.
    """
    # Import all models so SQLAlchemy knows about them before create_all
    import app.models  # noqa: F401

    if not settings.is_production:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ensured (dev mode).")

    # Run safe column migrations for new fields on existing tables
    try:
        _run_startup_migrations()
    except Exception as e:
        logger.warning(f"Startup migration skipped: {e}")

    # Seed admin user
    _seed_admin_user()

    # Ensure upload subdirectories exist
    for sub in ("profile_images", "qr_codes", "resumes", "certificates"):
        (settings.upload_path / sub).mkdir(parents=True, exist_ok=True)

    logger.info(f"DigiBioFi starting — env={settings.app_env}, base_url={settings.base_url}")
    yield
    logger.info("DigiBioFi shutting down.")


# ── Rate Limiting ─────────────────────────────────────────────────────────────
# Simple in-memory rate limiter: {ip: (timestamp, count)}
# NOTE: This is memory-based and will reset on application restart or multiple
# workers. For a distributed production environment, use Redis-based limiting.
_rate_limits: Dict[str, Tuple[float, int]] = {}

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
    # 1. Rate Limiting (with trusted proxy header support)
    ip = get_client_ip(request)
    if is_rate_limited(ip):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."}
        )

    # 2. CSRF Protection for POST requests
    if request.method == "POST" and settings.app_env != "testing":
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            # We trust the routers to handle CSRF validation for now to avoid
            # double-reading the form body which can be tricky in middleware
            pass

    response = await call_next(request)

    # 3. Security Headers
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    
    # CSP: 'unsafe-inline' is used for Tailwind CDN, Google Fonts, and dynamic JS 
    # elements required for the modern identity dashboard.
    csp = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com https://cdnjs.cloudflare.com https://pagead2.googlesyndication.com; "
        "img-src 'self' data: blob: https://images.unsplash.com https://pagead2.googlesyndication.com; "
        "font-src 'self' https://fonts.gstatic.com https://fonts.googleapis.com; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "frame-src https://googleads.g.doubleclick.net https://tpc.googlesyndication.com;"
    )
    
    # In production, ensure no mixed content by upgrading requests
    if settings.is_production:
        csp += " upgrade-insecure-requests;"
        
    response.headers["Content-Security-Policy"] = csp
    # HSTS — only enforce over HTTPS in production
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

    # 4. Set CSRF cookie if not present
    if not request.cookies.get("csrf_token"):
        from app.core.security import generate_csrf_token, set_csrf_cookie
        token = generate_csrf_token(request)
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
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
app.mount("/qr_codes", StaticFiles(directory=str(qr_path)), name="qr_codes")

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(public.router)
app.include_router(admin.router)
app.include_router(billing.router)


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
            user = _get_user_by_stripe(db, customer_id, metadata.get("user_id"))
            if user:
                user.subscription_tier = "elite"
                user.subscription_status = "active"
                if customer_id and not user.stripe_customer_id:
                    user.stripe_customer_id = customer_id
                if subscription_id:
                    user.stripe_subscription_id = subscription_id
                logger.info(f"User {user.id} upgraded to elite via checkout.session.completed")
            else:
                logger.warning(f"checkout.session.completed: no user found for customer={customer_id}")

        elif event_type == "customer.subscription.updated":
            customer_id = obj.get("customer")
            subscription_id = obj.get("id")
            status = obj.get("status")  # active, past_due, canceled, unpaid, etc.
            user = _get_user_by_stripe(db, customer_id, None)
            if user:
                if subscription_id:
                    user.stripe_subscription_id = subscription_id
                if status == "active":
                    user.subscription_status = "active"
                    user.subscription_tier = "elite"
                elif status in ("past_due", "unpaid"):
                    user.subscription_status = status
                elif status in ("canceled", "incomplete_expired"):
                    # Don't downgrade admin users
                    if user.email != "Antawnharris1992@gmail.com":
                        user.subscription_status = "canceled"
                        user.subscription_tier = "free"
                    else:
                        user.subscription_status = "canceled"
                        # Keep admin as elite regardless of billing status
                        logger.info(f"Admin user {user.id} subscription canceled but elite status retained")
                logger.info(f"User {user.id} subscription updated: status={status}")

        elif event_type == "customer.subscription.deleted":
            customer_id = obj.get("customer")
            user = _get_user_by_stripe(db, customer_id, None)
            if user:
                # Don't downgrade admin users
                if user.email != "Antawnharris1992@gmail.com":
                    user.subscription_status = "canceled"
                    user.subscription_tier = "free"
                    user.stripe_subscription_id = ""
                else:
                    user.subscription_status = "canceled"
                    user.stripe_subscription_id = ""
                    # Keep admin as elite regardless of billing status
                    logger.info(f"Admin user {user.id} subscription deleted but elite status retained")
                logger.info(f"User {user.id} subscription deleted — downgraded to free" if user.email != "Antawnharris1992@gmail.com" else f"User {user.id} is admin, elite status preserved")

        elif event_type == "invoice.payment_failed":
            customer_id = obj.get("customer")
            user = _get_user_by_stripe(db, customer_id, None)
            if user:
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
    return templates.TemplateResponse("landing.html", {"request": request, "user": user})


# ── Error handlers ────────────────────────────────────────────────────────────

@app.exception_handler(404)
def not_found(request: Request, exc):
    return templates.TemplateResponse(
        "errors/404.html", {"request": request}, status_code=404
    )


@app.exception_handler(500)
async def internal_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled 500 error", exc_info=exc)
    return HTMLResponse(content="Something went wrong. Please try again.", status_code=500)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Global exception caught", exc_info=exc)
    return HTMLResponse(content="Something went wrong. Please try again.", status_code=500)
