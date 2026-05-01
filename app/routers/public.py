"""
Public-facing routes — profile page, QR download, PDF download, analytics tracking.
"""
import logging
from threading import Lock
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response, FileResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from datetime import date, datetime, timezone, timedelta

from app.core.config import settings
from app.core.permissions import can_access_portfolio, can_view_profile, should_show_ads
from app.core.templates import templates, flash
from app.core.dependencies import get_db, get_current_user_optional
from app.services import profile_service, qr_service, analytics_service
from app.services.storage import storage
from app.schemas.analytics import TrackEventRequest
from app.utils.validators import hash_daily_client_token, hash_visitor, sanitize_text

router = APIRouter(tags=["public"])
logger = logging.getLogger(__name__)
_ANONYMOUS_DAILY_PROFILE_VIEW_LIMIT = 100
_anonymous_profile_views: dict[str, tuple[date, int]] = {}
_anonymous_profile_views_lock = Lock()
_EXAMPLE_PROFILE_EMAIL_DOMAIN = "@example.invalid"


def _is_example_profile(profile) -> bool:
    user = getattr(profile, "user", None)
    email = (getattr(user, "email", "") or "").lower()
    username = (getattr(user, "username", "") or "").lower()
    headline = (getattr(profile, "headline", "") or "").lower()
    return (
        email.endswith(_EXAMPLE_PROFILE_EMAIL_DOMAIN)
        or username.startswith("sample_")
        or headline.startswith("example profile")
        or headline.startswith("sample profile")
    )


def _get_client_ip(request: Request) -> str:
    state_ip = getattr(request.state, "client_ip", None)
    if state_ip:
        return state_ip

    if not settings.use_proxy_headers:
        if request.client:
            return request.client.host
        return "unknown"

    """
    Extract the real client IP, honoring trusted proxy headers.
    Essential for VPS deployments behind nginx or Cloudflare.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


def _get_daily_ip_hash(request: Request, ip: str) -> str:
    token = getattr(request.state, "daily_ip_hash", None)
    if token:
        return token
    return hash_daily_client_token(ip, settings.secret_key)


def _record_view_protected(profile, source, ip, ip_token, ua, db, user, qr_id=None):
    """Record a page view only if this visitor hasn't viewed in the last 24h."""
    if user and user.id == profile.user_id:
        return  # Don't count owner's own views

    from app.models.profile import ProfileView
    now = datetime.now(timezone.utc)
    visitor_hash = hash_visitor(ip or "unknown", ua or "")
    cutoff = now - timedelta(hours=24)
    rapid_cutoff = now - timedelta(seconds=60)

    try:
        if ip_token:
            recent_same_ip = db.query(ProfileView).filter(
                ProfileView.profile_id == profile.id,
                ProfileView.viewer_ip == ip_token,
                ProfileView.created_at >= rapid_cutoff,
            ).first()
            if recent_same_ip:
                return

        already_viewed = db.query(ProfileView).filter(
            ProfileView.profile_id == profile.id,
            ProfileView.visitor_hash == visitor_hash,
            ProfileView.created_at >= cutoff,
        ).first()
        if already_viewed:
            return

        pv = ProfileView(
            profile_id=profile.id,
            viewer_ip=(ip_token or "")[:64],
            user_agent=(ua or "")[:500],
            visitor_hash=visitor_hash,
        )
        db.add(pv)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Profile view logging failed for slug=%s", profile.slug)
        return

    try:
        analytics_service.record_page_view(profile, source, ip or "unknown", ua or "", db, qr_id=qr_id)
    except Exception:
        logger.exception("Analytics page_view record failed for slug=%s", profile.slug)


def _ensure_profile_access(profile, user) -> None:
    if not profile.is_public and (not user or user.id != profile.user_id):
        raise HTTPException(status_code=404, detail="Profile not found")


def _same_calendar_day(value: datetime | None, now: datetime) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        return value.date() == now.date()
    return value.astimezone(timezone.utc).date() == now.date()


def _current_daily_view_count(user, now: datetime) -> int:
    current_count = int(getattr(user, "daily_profile_views", 0) or 0)
    if not _same_calendar_day(getattr(user, "last_view_reset", None), now):
        user.daily_profile_views = 0
        user.last_view_reset = now
        current_count = 0
    return current_count


def _consume_daily_profile_view(user, db: Session, now: datetime) -> bool:
    current_count = _current_daily_view_count(user, now)
    if not can_view_profile(user, current_count):
        return False
    user.daily_profile_views = current_count + 1
    user.last_view_reset = now
    db.commit()
    return True


def _allow_anonymous_profile_view(ip_token: str, now: datetime) -> bool:
    key = (ip_token or "unknown")[:64]
    today = now.date()

    with _anonymous_profile_views_lock:
        day, count = _anonymous_profile_views.get(key, (today, 0))
        if day != today:
            count = 0
        if count >= _ANONYMOUS_DAILY_PROFILE_VIEW_LIMIT:
            _anonymous_profile_views[key] = (today, count)
            return False
        _anonymous_profile_views[key] = (today, count + 1)
    return True


# ── Public profile page ───────────────────────────────────────────────────────

@router.get("/p/{slug}", response_class=HTMLResponse)
def public_profile(
    slug: str,
    request: Request,
    src: str = "direct",       # ?src=qr  or  ?src=referral
    qr_id: str | None = None,  # optional qr_id from QR scan
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    profile = profile_service.get_profile_by_slug(slug, db)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    _ensure_profile_access(profile, user)
    now = datetime.now(timezone.utc)
    ip = _get_client_ip(request)
    ip_token = _get_daily_ip_hash(request, ip)
    ua = request.headers.get("user-agent", "")

    if user is None and not _allow_anonymous_profile_view(ip_token, now):
        logger.warning("Anonymous public profile throttle exceeded slug=%s", slug)
        return templates.TemplateResponse(
            "errors/429.html",
            {"request": request},
            status_code=429,
        )

    if user and user.id != profile.user_id:
        if not _consume_daily_profile_view(user, db, now):
            flash(
                request,
                "Free accounts have a daily public profile view limit. Upgrade for unlimited access.",
                "info",
            )
            return RedirectResponse("/dashboard/upgrade", status_code=303)

    # Normalise source value
    source = src if src in ("qr", "referral") else "direct"

    # Record server-side page view with deduplication (1 view per IP/device per 24h)
    logger.info("Public profile view logged slug=%s source=%s", slug, source)
    _record_view_protected(profile, source, ip, ip_token, ua, db, user, qr_id)
    adsense_client_id = settings.adsense_client_id.strip()
    public_inline_ad_slot = settings.adsense_public_inline_slot.strip()
    public_sidebar_ad_slot = settings.adsense_public_sidebar_slot.strip()
    show_ads = should_show_ads(profile.user)
    is_example_profile = _is_example_profile(profile)

    return templates.TemplateResponse(
        "public/profile.html",
        {
            "request": request,
            "profile": profile,
            "safe_profile_bio": sanitize_text(profile.bio or ""),
            "base_url": settings.base_url,
            "user": user,
            "show_public_inline_ad": show_ads and bool(adsense_client_id and public_inline_ad_slot),
            "show_public_sidebar_ad": show_ads and bool(adsense_client_id and public_sidebar_ad_slot),
            "show_public_portfolio": can_access_portfolio(profile.user),
            "adsense_client_id": adsense_client_id,
            "public_inline_ad_slot": public_inline_ad_slot,
            "public_sidebar_ad_slot": public_sidebar_ad_slot,
            "is_example_profile": is_example_profile,
        },
    )


# ── Analytics event ingestion (called by JS on the public page) ───────────────

@router.post("/api/analytics/event/{slug}")
def track_event(
    slug: str,
    event: TrackEventRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    profile = profile_service.get_profile_by_slug(slug, db)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    _ensure_profile_access(profile, user)

    ip = _get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    try:
        analytics_service.record_event(profile, event, ip, ua, db)
    except Exception:
        logger.exception("Analytics event logging failed for slug=%s", slug)
    return JSONResponse({"ok": True})


# ── QR code download ──────────────────────────────────────────────────────────

@router.get("/qr/download/{slug}")
def download_qr(slug: str, db: Session = Depends(get_db)):
    profile = profile_service.get_profile_by_slug(slug, db)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    qr_bytes = qr_service.get_qr_bytes(slug)
    if not qr_bytes:
        # Generate on demand if missing
        qr_service.generate_qr_for_profile(profile, db)
        qr_bytes = qr_service.get_qr_bytes(slug)

    return Response(
        content=qr_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{slug}-qr.png"'},
    )


@router.get("/api/qr/{slug}")
def inline_qr(slug: str, db: Session = Depends(get_db)):
    profile = profile_service.get_profile_by_slug(slug, db)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    qr_bytes = qr_service.get_qr_bytes(slug)
    if not qr_bytes:
        qr_service.generate_qr_for_profile(profile, db)
        qr_bytes = qr_service.get_qr_bytes(slug)

    return Response(content=qr_bytes, media_type="image/png")


# ── Resume PDF download ───────────────────────────────────────────────────────

@router.get("/resume/download/{slug}")
def download_resume(slug: str, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    profile = profile_service.get_profile_by_slug(slug, db)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    _ensure_profile_access(profile, user)

    if not profile.resume_pdf:
        flash(request, "Resume not available for this profile.", "info")
        return RedirectResponse(url=f"/p/{slug}?error=no_resume", status_code=status.HTTP_303_SEE_OTHER)

    pdf_path = storage.resolve_url(profile.resume_pdf)
    if not pdf_path or not pdf_path.exists():
        flash(request, "Resume not available for this profile.", "info")
        return RedirectResponse(url=f"/p/{slug}?error=no_resume", status_code=status.HTTP_303_SEE_OTHER)

    # Record analytics event
    ip = _get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    try:
        analytics_service.record_event(
            profile,
            TrackEventRequest(event_type="pdf_download", source="direct"),
            ip, ua, db,
        )
    except Exception:
        logger.exception("Resume download analytics failed for slug=%s", slug)

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{slug}-resume.pdf",
    )
