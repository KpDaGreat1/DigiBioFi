"""
DigiBioFi — FastAPI application factory.

Run locally:
    uvicorn app.main:app --reload

Production:
    gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4
"""
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Tuple

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature

from app.core.config import settings
from app.core.templates import templates, get_csrf_token, csrf_serializer
from app.db.database import engine, Base
from app.routers import auth, dashboard, public, admin

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Application lifespan ──────────────────────────────────────────────────────

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

    # Ensure upload subdirectories exist
    for sub in ("profile_images", "qr_codes", "resumes"):
        (settings.upload_path / sub).mkdir(parents=True, exist_ok=True)

    logger.info(f"DigiBioFi starting — env={settings.app_env}, base_url={settings.base_url}")
    yield
    logger.info("DigiBioFi shutting down.")


# ── Rate Limiting ─────────────────────────────────────────────────────────────
# Simple in-memory rate limiter: {ip: (timestamp, count)}
_rate_limits: Dict[str, Tuple[float, int]] = {}

def is_rate_limited(ip: str) -> bool:
    if settings.app_env == "testing":
        return False
    now = time.time()
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

# ── Middleware ────────────────────────────────────────────────────────────────

@app.middleware("http")
async def security_and_rate_limit_middleware(request: Request, call_next):
    # 1. Rate Limiting
    ip = request.client.host if request.client else "unknown"
    if is_rate_limited(ip):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."}
        )

    # 2. CSRF Protection for POST requests
    # Skip for certain paths (e.g., API if used by mobile) or if content-type is not form
    if request.method == "POST" and settings.app_env != "testing":
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            # Check CSRF token
            form_data = await request.form()
            csrf_token = form_data.get("csrf_token")
            cookie_token = request.cookies.get("csrf_token")

            if not csrf_token or not cookie_token or csrf_token != cookie_token:
                return HTMLResponse(
                    status_code=403,
                    content="CSRF token missing or invalid."
                )
            try:
                csrf_serializer.loads(csrf_token)
            except BadSignature:
                return HTMLResponse(
                    status_code=403,
                    content="CSRF token invalid."
                )

    response = await call_next(request)

    # 3. Security Headers
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: https://images.unsplash.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self';"
    )

    # 4. Set CSRF cookie if not present or rotated
    if not request.cookies.get("csrf_token") or request.method == "POST":
        token = csrf_serializer.dumps(time.time())
        response.set_cookie(
            key="csrf_token",
            value=token,
            httponly=True,
            samesite="lax",
            secure=settings.is_production,
        )

    return response

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
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(public.router)
app.include_router(admin.router)


# ── Root redirect ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    """Landing page — redirect authenticated users to dashboard."""
    token = request.cookies.get("access_token")
    if token:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("landing.html", {"request": request})


# ── Error handlers ────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception", exc_info=exc)
    return templates.TemplateResponse(
        "errors/500.html", {"request": request}, status_code=500
    )


@app.exception_handler(404)
def not_found(request: Request, exc):
    return templates.TemplateResponse(
        "errors/404.html", {"request": request}, status_code=404
    )


@app.exception_handler(500)
def server_error(request: Request, exc):
    logger.exception("Unhandled server error", exc_info=exc)
    return templates.TemplateResponse(
        "errors/500.html", {"request": request}, status_code=500
    )
