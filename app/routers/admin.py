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
from app.models.message import ContactMessage
from app.models.profile import Profile
from app.models.user import User
from app.services.user_service import delete_user_and_assets
from app.utils.validators import normalize_external_url, sanitize_article_html

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_ROLES = {"user", "admin"}
VALID_TIERS = {"free", "basic", "elite"}
VALID_MESSAGE_STATUSES = {"unread", "read", "resolved"}


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
    unread_messages = (
        db.query(ContactMessage)
        .filter(ContactMessage.status == "unread")
        .count()
    )

    # Tier distribution
    raw_tier_counts = dict(
        db.query(User.subscription_tier, func.count(User.id))
        .group_by(User.subscription_tier)
        .all()
    )
    tier_counts = {
        "free": raw_tier_counts.get("free", 0),
        "basic": raw_tier_counts.get("basic", 0),
        "elite": raw_tier_counts.get("elite", 0),
    }

    # Public vs private profiles
    public_profiles = db.query(Profile).filter(Profile.is_public.is_(True)).count()
    private_profiles = db.query(Profile).filter(Profile.is_public.is_(False)).count()

    # Recent signups
    recent_users = (
        db.query(User)
        .order_by(User.created_at.desc())
        .limit(7)
        .all()
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
                "unread_messages": unread_messages,
                "tier_counts": tier_counts,
                "public_profiles": public_profiles,
                "private_profiles": private_profiles,
            },
            "recent_users": recent_users,
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
    logger.info("Admin %s deleted user_id=%s", admin.id, user_id)
    flash(request, f"{email} deleted.", "success")
    return _users_redirect()


# ── Contact Messages ──────────────────────────────────────────────────────────

@router.get("/messages", response_class=HTMLResponse)
def admin_messages(
    request: Request,
    status: str = "",
    page: int = 1,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models.message import ContactMessage

    per_page = 20
    offset = (page - 1) * per_page

    query = db.query(ContactMessage)
    if status and status in VALID_MESSAGE_STATUSES:
        query = query.filter(ContactMessage.status == status)

    total = query.count()
    messages = (
        query.order_by(ContactMessage.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Unread count for badge
    unread_count = db.query(ContactMessage).filter(ContactMessage.status == "unread").count()

    return templates.TemplateResponse(
        "admin/messages.html",
        {
            "request": request,
            "admin": admin,
            "messages": messages,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "current_status_filter": status,
            "unread_count": unread_count,
        },
    )


@router.get("/messages/{msg_id}", response_class=HTMLResponse)
def admin_message_detail(
    request: Request,
    msg_id: int,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models.message import ContactMessage

    msg = db.query(ContactMessage).filter(ContactMessage.id == msg_id).first()
    if not msg:
        flash(request, "Message not found.", "error")
        return RedirectResponse("/admin/messages", status_code=303)

    # Auto-mark as read when admin opens it
    if msg.status == "unread":
        msg.status = "read"
        db.commit()

    return templates.TemplateResponse(
        "admin/message_detail.html",
        {
            "request": request,
            "admin": admin,
            "msg": msg,
        },
    )


@router.post("/messages/{msg_id}/set-status", response_class=HTMLResponse)
async def set_message_status(
    request: Request,
    msg_id: int,
    status: str = Form(...),
    csrf_token: str = Depends(require_csrf),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models.message import ContactMessage

    if status not in VALID_MESSAGE_STATUSES:
        flash(request, "Invalid status.", "error")
        return RedirectResponse(f"/admin/messages/{msg_id}", status_code=303)

    msg = db.query(ContactMessage).filter(ContactMessage.id == msg_id).first()
    if not msg:
        flash(request, "Message not found.", "error")
        return RedirectResponse("/admin/messages", status_code=303)

    msg.status = status
    db.commit()
    flash(request, f"Message marked as {status}.", "success")
    return RedirectResponse(f"/admin/messages/{msg_id}", status_code=303)


@router.post("/messages/{msg_id}/delete", response_class=HTMLResponse)
async def delete_message(
    request: Request,
    msg_id: int,
    csrf_token: str = Depends(require_csrf),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models.message import ContactMessage

    msg = db.query(ContactMessage).filter(ContactMessage.id == msg_id).first()
    if not msg:
        flash(request, "Message not found.", "error")
        return RedirectResponse("/admin/messages", status_code=303)

    db.delete(msg)
    db.commit()
    flash(request, "Message deleted.", "success")
    return RedirectResponse("/admin/messages", status_code=303)


# ── Articles ──────────────────────────────────────────────────────────────────

def _article_redirect(article_id: int | None = None) -> RedirectResponse:
    if article_id:
        return RedirectResponse(f"/admin/articles/{article_id}/edit", status_code=303)
    return RedirectResponse("/admin/articles", status_code=303)


def _slugify(text: str) -> str:
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:280].strip("-")


def _unique_article_slug(base: str, db: Session, exclude_id: int | None = None) -> str:
    from app.models.article import Article
    slug = _slugify(base)
    candidate = slug
    suffix = 1
    while True:
        q = db.query(Article).filter(Article.slug == candidate)
        if exclude_id:
            q = q.filter(Article.id != exclude_id)
        if not q.first():
            return candidate
        candidate = f"{slug}-{suffix}"
        suffix += 1


@router.get("/articles", response_class=HTMLResponse)
def admin_articles(
    request: Request,
    page: int = 1,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models.article import Article

    per_page = 20
    offset = (page - 1) * per_page
    total = db.query(Article).count()
    articles = (
        db.query(Article)
        .order_by(Article.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )
    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(
        "admin/articles.html",
        {
            "request": request,
            "admin": admin,
            "articles": articles,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


@router.get("/articles/new", response_class=HTMLResponse)
@router.get("/articles/create", response_class=HTMLResponse)
def admin_article_new(
    request: Request,
    admin=Depends(require_admin),
):
    return templates.TemplateResponse(
        "admin/article_form.html",
        {"request": request, "admin": admin, "article": None, "errors": {}},
    )


@router.post("/articles/new", response_class=HTMLResponse)
@router.post("/articles/create", response_class=HTMLResponse)
async def admin_article_create(
    request: Request,
    title: str = Form(""),
    slug: str = Form(default=""),
    summary: str = Form(default=""),
    content_html: str = Form(default=""),
    category: str = Form(default=""),
    tags: str = Form(default=""),
    hero_image: str = Form(default=""),
    video_url: str = Form(default=""),
    is_published: str = Form(default="off"),
    csrf_token: str = Depends(require_csrf),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models.article import Article

    title = title.strip()[:300]
    summary = summary.strip()[:500]
    content_html = sanitize_article_html(content_html.strip())
    category = category.strip()[:100]
    tags = tags.strip()[:300]
    hero_image = hero_image.strip()[:500]
    video_url = video_url.strip()[:500]

    errors: dict[str, str] = {}
    if not title:
        errors["title"] = "Title is required."
    if not content_html:
        errors["content_html"] = "Content is required."
    if hero_image:
        try:
            hero_image = normalize_external_url(hero_image)
        except ValueError:
            errors["hero_image"] = "Hero image URL must start with http:// or https://"
    if video_url:
        try:
            video_url = normalize_external_url(video_url)
        except ValueError:
            errors["video_url"] = "Video URL must start with http:// or https://"

    if errors:
        return templates.TemplateResponse(
            "admin/article_form.html",
            {
                "request": request,
                "admin": admin,
                "article": None,
                "errors": errors,
                "form": {
                    "title": title, "slug": slug, "summary": summary,
                    "content_html": content_html, "category": category,
                    "tags": tags, "hero_image": hero_image,
                    "video_url": video_url,
                    "is_published": is_published == "on",
                },
            },
            status_code=422,
        )

    final_slug = _unique_article_slug(slug or title, db)

    article = Article(
        title=title,
        slug=final_slug,
        summary=summary,
        content_html=content_html,
        category=category,
        tags=tags,
        hero_image=hero_image or None,
        video_url=video_url or None,
        is_published=(is_published == "on"),
        author_id=admin.id,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    flash(request, "Article created.", "success")
    return RedirectResponse(f"/admin/articles/{article.id}/edit", status_code=303)


@router.get("/articles/{article_id}/edit", response_class=HTMLResponse)
def admin_article_edit(
    request: Request,
    article_id: int,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models.article import Article

    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        flash(request, "Article not found.", "error")
        return RedirectResponse("/admin/articles", status_code=303)

    return templates.TemplateResponse(
        "admin/article_form.html",
        {"request": request, "admin": admin, "article": article, "errors": {}},
    )


@router.post("/articles/{article_id}/edit", response_class=HTMLResponse)
async def admin_article_update(
    request: Request,
    article_id: int,
    title: str = Form(""),
    slug: str = Form(default=""),
    summary: str = Form(default=""),
    content_html: str = Form(default=""),
    category: str = Form(default=""),
    tags: str = Form(default=""),
    hero_image: str = Form(default=""),
    video_url: str = Form(default=""),
    is_published: str = Form(default="off"),
    csrf_token: str = Depends(require_csrf),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models.article import Article

    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        flash(request, "Article not found.", "error")
        return RedirectResponse("/admin/articles", status_code=303)

    title = title.strip()[:300]
    summary = summary.strip()[:500]
    content_html = sanitize_article_html(content_html.strip())
    category = category.strip()[:100]
    tags = tags.strip()[:300]
    hero_image = hero_image.strip()[:500]
    video_url = video_url.strip()[:500]

    errors: dict[str, str] = {}
    if not title:
        errors["title"] = "Title is required."
    if not content_html:
        errors["content_html"] = "Content is required."
    if hero_image:
        try:
            hero_image = normalize_external_url(hero_image)
        except ValueError:
            errors["hero_image"] = "Hero image URL must start with http:// or https://"
    if video_url:
        try:
            video_url = normalize_external_url(video_url)
        except ValueError:
            errors["video_url"] = "Video URL must start with http:// or https://"

    if errors:
        return templates.TemplateResponse(
            "admin/article_form.html",
            {
                "request": request,
                "admin": admin,
                "article": article,
                "errors": errors,
                "form": {
                    "title": title,
                    "slug": slug,
                    "summary": summary,
                    "content_html": content_html,
                    "category": category,
                    "tags": tags,
                    "hero_image": hero_image,
                    "video_url": video_url,
                    "is_published": is_published == "on",
                },
            },
            status_code=422,
        )

    new_slug = slug.strip()[:300] or _slugify(title)
    if new_slug != article.slug:
        new_slug = _unique_article_slug(new_slug, db, exclude_id=article.id)

    article.title = title
    article.slug = new_slug
    article.summary = summary
    article.content_html = content_html
    article.category = category
    article.tags = tags
    article.hero_image = hero_image or None
    article.video_url = video_url or None
    article.is_published = (is_published == "on")
    db.commit()
    flash(request, "Article updated.", "success")
    return RedirectResponse(f"/admin/articles/{article.id}/edit", status_code=303)


@router.post("/articles/{article_id}/delete", response_class=HTMLResponse)
async def admin_article_delete(
    request: Request,
    article_id: int,
    csrf_token: str = Depends(require_csrf),
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models.article import Article

    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        flash(request, "Article not found.", "error")
        return RedirectResponse("/admin/articles", status_code=303)

    db.delete(article)
    db.commit()
    flash(request, "Article deleted.", "success")
    return RedirectResponse("/admin/articles", status_code=303)
