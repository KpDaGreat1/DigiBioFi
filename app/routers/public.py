"""
Public-facing routes — profile page, QR download, PDF download, analytics tracking.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response, FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.templates import templates
from app.core.dependencies import get_db
from app.services import profile_service, qr_service, analytics_service
from app.schemas.analytics import TrackEventRequest

router = APIRouter(tags=["public"])


# ── Public profile page ───────────────────────────────────────────────────────

@router.get("/p/{slug}", response_class=HTMLResponse)
def public_profile(
    slug: str,
    request: Request,
    src: str = "direct",       # ?src=qr  or  ?src=referral
    qr_id: str | None = None,  # optional qr_id from QR scan
    db: Session = Depends(get_db),
):
    profile = profile_service.get_profile_by_slug(slug, db)
    if not profile or not profile.is_public:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Normalise source value
    source = src if src in ("qr", "referral") else "direct"

    # Record server-side page view
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    analytics_service.record_page_view(profile, source, ip, ua, db, qr_id=qr_id)

    return templates.TemplateResponse(
        "public/profile.html",
        {
            "request": request,
            "profile": profile,
            "base_url": settings.base_url,
        },
    )


# ── Analytics event ingestion (called by JS on the public page) ───────────────

@router.post("/api/analytics/event/{slug}")
def track_event(
    slug: str,
    event: TrackEventRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    profile = profile_service.get_profile_by_slug(slug, db)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    ip = request.client.host if request.client else "unknown"
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
def download_resume(slug: str, request: Request, db: Session = Depends(get_db)):
    profile = profile_service.get_profile_by_slug(slug, db)
    if not profile or not profile.is_public:
        raise HTTPException(status_code=404, detail="Profile not found")

    if not profile.resume_pdf:
        raise HTTPException(status_code=404, detail="No resume uploaded")

    # Record analytics event
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    analytics_service.record_event(
        profile,
        TrackEventRequest(event_type="pdf_download", source="direct"),
        ip, ua, db,
    )

    from pathlib import Path
    pdf_path = Path(profile.resume_pdf)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{slug}-resume.pdf",
    )
