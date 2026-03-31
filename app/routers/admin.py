"""
Admin panel routes — user management, analytics overview, moderation scaffold.

All routes require the authenticated user to have role='admin'.
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_admin
from app.core.templates import templates
from app.models.user import User
from app.models.analytics import AnalyticsEvent
from app.models.profile import Profile

router = APIRouter(prefix="/admin", tags=["admin"])


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
    active_users = db.query(User).filter(User.is_active == True).count()  # noqa: E712

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
            },
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
            "users": users,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


# ── Toggle user active state ──────────────────────────────────────────────────

@router.post("/users/{user_id}/toggle-active", response_class=HTMLResponse)
def toggle_user_active(
    user_id: int,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.id != admin.id:   # admins cannot deactivate themselves
        user.is_active = not user.is_active
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


# ── Change user role ──────────────────────────────────────────────────────────

@router.post("/users/{user_id}/set-role", response_class=HTMLResponse)
def set_user_role(
    user_id: int,
    role: str = Form(...),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user and role in ("user", "admin"):
        user.role = role
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)
