"""
Public-facing routes — profile page, QR download, PDF download, analytics tracking.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response, FileResponse, JSONResponse
from sqlalchemy.orm import Session

from datetime import datetime, timezone, timedelta

from app.core.config import settings
from app.core.templates import templates
from app.core.dependencies import get_db, get_current_user_optional
from app.services import profile_service, qr_service, analytics_service
from app.services.storage import storage
from app.schemas.analytics import TrackEventRequest
from app.utils.validators import hash_visitor

router = APIRouter(tags=["public"])


def _get_client_ip(request: Request) -> str:
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


def _record_view_protected(profile, source, ip, ua, db, user, qr_id=None):
    """Record a page view only if this visitor hasn't viewed in the last 24h."""
    if user and user.id == profile.user_id:
        return  # Don't count owner's own views

    from app.models.profile import ProfileView
    visitor_hash = hash_visitor(ip, ua)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    already_viewed = db.query(ProfileView).filter(
        ProfileView.profile_id == profile.id,
        ProfileView.visitor_hash == visitor_hash,
        ProfileView.created_at >= cutoff,
    ).first()
    if not already_viewed:
        pv = ProfileView(profile_id=profile.id, visitor_hash=visitor_hash)
        db.add(pv)
        db.commit()
        analytics_service.record_page_view(profile, source, ip, ua, db, qr_id=qr_id)


def _ensure_profile_access(profile, user) -> None:
    if not profile.is_public and (not user or user.id != profile.user_id):
        raise HTTPException(status_code=404, detail="Profile not found")


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

    # Normalise source value
    source = src if src in ("qr", "referral") else "direct"

    # Record server-side page view with deduplication (1 view per IP/device per 24h)
    ip = _get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    _record_view_protected(profile, source, ip, ua, db, user, qr_id)

    return templates.TemplateResponse(
        "public/profile.html",
        {
            "request": request,
            "profile": profile,
            "base_url": settings.base_url,
            "user": user,
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
    analytics_service.record_event(profile, event, ip, ua, db)
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


# ── Resume PDF download ───────────────────────────────────────────────────────

@router.get("/resume/download/{slug}")
def download_resume(slug: str, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    profile = profile_service.get_profile_by_slug(slug, db)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    _ensure_profile_access(profile, user)

    if not profile.resume_pdf:
        # Graceful fallback: redirect back to profile with a message
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/p/{slug}?error=no_resume", status_code=status.HTTP_303_SEE_OTHER)

    pdf_path = storage.resolve_url(profile.resume_pdf)
    if not pdf_path or not pdf_path.exists():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/p/{slug}?error=no_resume", status_code=status.HTTP_303_SEE_OTHER)

    # Record analytics event
    ip = _get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    analytics_service.record_event(
        profile,
        TrackEventRequest(event_type="pdf_download", source="direct"),
        ip, ua, db,
    )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{slug}-resume.pdf",
    )
