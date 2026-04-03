"""
Admin panel routes — user management, analytics overview, moderation scaffold.

All routes require the authenticated user to have role='admin'.
"""
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.owner import apply_owner_access, is_owner_email
from app.core.dependencies import get_db, require_admin, require_csrf
from app.core.templates import flash, templates
from app.models.analytics import AnalyticsEvent
from app.models.profile import Profile
from app.models.user import User
from app.services.user_service import delete_user_and_assets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_ROLES = {"user", "admin"}
VALID_TIERS = {"free", "basic", "premium", "elite"}


def _users_redirect() -> RedirectResponse:
    return RedirectResponse("/admin/users", status_code=303)


# ── Admin dashboard ───────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def admin_home(
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    total_users = db.query(User).count()
    total_profiles = db.query(Profile).count()
    total_events = db.query(AnalyticsEvent).count()
    active_users = db.query(User).filter(User.is_active.is_(True)).count()
    total_page_views = (
        db.query(AnalyticsEvent)
        .filter(AnalyticsEvent.event_type == "page_view")
        .count()
    )
    total_qr_scans = (
        db.query(AnalyticsEvent)
        .filter(AnalyticsEvent.event_type == "qr_scan")
        .count()
    )
    top_profiles = (
        db.query(
            Profile.slug.label("slug"),
            User.username.label("username"),
            func.count(AnalyticsEvent.id).label("event_count"),
            func.coalesce(
                func.sum(
                    case((AnalyticsEvent.event_type == "page_view", 1), else_=0)
                ),
                0,
            ).label("page_views"),
        )
        .join(User, User.id == Profile.user_id)
        .outerjoin(AnalyticsEvent, AnalyticsEvent.profile_id == Profile.id)
        .group_by(Profile.id, Profile.slug, User.username)
        .order_by(func.count(AnalyticsEvent.id).desc(), Profile.slug.asc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse(
        "admin/index.html",
        {
            "request": request,
            "admin": admin,
            "stats": {
                "total_users": total_users,
                "active_users": active_users,
                "total_profiles": total_profiles,
                "total_events": total_events,
                "total_page_views": total_page_views,
                "total_qr_scans": total_qr_scans,
            },
            "top_profiles": top_profiles,
        },
    )


# ── User list ─────────────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
def admin_users(
    request: Request,
    page: int = 1,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    per_page = 20
    offset = (page - 1) * per_page
    users = (
        db.query(User)
        .options(joinedload(User.profile))
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )
    total = db.query(User).count()
    total_pages = (total + per_page - 1) // per_page

    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "admin": admin,
            "owner_email": settings.admin_email.lower(),
            "users": users,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


# ── Toggle user active state ──────────────────────────────────────────────────

@router.post("/users/{user_id}/toggle-active", response_class=HTMLResponse)
async def toggle_user_active(
    request: Request,
    user_id: int,
    csrf_token: str = Depends(require_csrf),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        flash(request, "User not found.", "error")
        return _users_redirect()

    if user.id == admin.id or is_owner_email(user.email):
        flash(request, "That account cannot be deactivated here.", "error")
        return _users_redirect()

    user.is_active = not user.is_active
    db.commit()
    flash(request, f"{user.email} is now {'active' if user.is_active else 'inactive'}.", "success")
    return _users_redirect()


# ── Change user role ──────────────────────────────────────────────────────────

@router.post("/users/{user_id}/set-role", response_class=HTMLResponse)
async def set_user_role(
    request: Request,
    user_id: int,
    role: str = Form(...),
    csrf_token: str = Depends(require_csrf),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        flash(request, "User not found.", "error")
        return _users_redirect()

    if user.id == admin.id or is_owner_email(user.email):
        logger.warning("Admin %s attempted to change a protected role for user %s", admin.id, user.id)
        flash(request, "That account role is locked.", "error")
        return _users_redirect()

    if role not in VALID_ROLES:
        flash(request, "Invalid role.", "error")
        return _users_redirect()

    user.role = role
    db.commit()
    logger.info("Admin %s changed user %s role to %s", admin.id, user.id, role)
    flash(request, f"{user.email} role set to {role}.", "success")
    return _users_redirect()


@router.post("/users/{user_id}/set-tier", response_class=HTMLResponse)
async def set_user_tier(
    request: Request,
    user_id: int,
    tier: str = Form(...),
    csrf_token: str = Depends(require_csrf),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        flash(request, "User not found.", "error")
        return _users_redirect()

    if tier not in VALID_TIERS:
        flash(request, "Invalid tier.", "error")
        return _users_redirect()

    if is_owner_email(user.email):
        if apply_owner_access(user):
            db.commit()
        flash(request, "Owner access remains locked to elite admin.", "info")
        return _users_redirect()

    user.subscription_tier = tier
    user.subscription_status = "active"
    db.commit()
    flash(request, f"{user.email} tier set to {tier}.", "success")
    return _users_redirect()


@router.post("/users/{user_id}/toggle-visibility", response_class=HTMLResponse)
async def toggle_user_visibility(
    request: Request,
    user_id: int,
    csrf_token: str = Depends(require_csrf),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .options(joinedload(User.profile))
        .filter(User.id == user_id)
        .first()
    )
    if not user or not user.profile:
        flash(request, "Profile not found.", "error")
        return _users_redirect()

    user.profile.is_public = not user.profile.is_public
    db.commit()
    flash(
        request,
        f"{user.email} profile is now {'public' if user.profile.is_public else 'private'}.",
        "success",
    )
    return _users_redirect()


@router.post("/users/{user_id}/delete", response_class=HTMLResponse)
async def delete_user(
    request: Request,
    user_id: int,
    csrf_token: str = Depends(require_csrf),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .options(joinedload(User.profile))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        flash(request, "User not found.", "error")
        return _users_redirect()

    if user.id == admin.id or is_owner_email(user.email):
        flash(request, "That account cannot be deleted here.", "error")
        return _users_redirect()

    email = user.email
    delete_user_and_assets(user, db)
    logger.info("Admin %s deleted user %s", admin.id, email)
    flash(request, f"{email} deleted.", "success")
    return _users_redirect()
