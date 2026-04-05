"""
Dashboard routes — authenticated user home, account, profile edit, QR, card preview.
"""
import logging
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.core.config import settings
from app.core.dependencies import get_db, get_current_user, require_csrf
from app.core.permissions import (
    can_access_analytics,
    can_access_elite_features,
    can_access_portfolio,
    can_manage_subscription,
    current_plan_label,
    should_show_ads,
)
from app.core.templates import templates, flash, get_csrf_token
from app.models.user import User
from app.schemas.profile import (
    ProfileUpdate,
    ExperienceCreate, EducationCreate, SkillCreate,
    ProjectCreate, CertificationCreate, AwardCreate, CustomSectionCreate,
)
from app.services import profile_service, qr_service, file_service, analytics_service
from app.services.storage import storage
from app.utils.validators import format_pydantic_errors

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)


def _normalize_plan(plan: str | None) -> str:
    return (plan or "").lower().strip()


def _query_flag_enabled(value: str | None) -> bool:
    return (value or "").lower() == "true"


def _get_profile(user: User, db: Session):
    """Convenience: return profile or redirect to dashboard if missing."""
    from app.services.profile_service import get_profile_by_user, ProfileNotFound
    try:
        return get_profile_by_user(user.id, db)
    except ProfileNotFound:
        return None


# ── Dashboard home ────────────────────────────────────────────────────────────

def _get_profile_completion_score(profile) -> int:
    """
    Calculate profile completion percentage.
    Only core identity fields count.
    Optional fields (photo, phone, social links) do not block 100%.
    """
    if not profile:
        return 0

    # Core identity fields required for 100%
    core_fields = {
        "full_name": 20,
        "headline": 20,
        "bio": 20,
        "email": 10,
        "location": 10,
    }
 
    # Collection fields (at least one item required)
    collections = {
        "experiences": 10,
        "skills": 10,
    }

    score = 0
    for field, weight in core_fields.items():
        if getattr(profile, field, None):
            score += weight

    for attr, weight in collections.items():
        try:
            items = getattr(profile, attr, [])
            if items and len(items) > 0:
                score += weight
        except Exception:
            continue

    return min(score, 100)


def _delete_upload_url(url: str) -> None:
    if not url:
        return
    try:
        storage.delete_url(url)
    except Exception as exc:
        logger.warning("Failed to delete upload %s: %s", url, exc)


def _require_portfolio_access(request: Request, current_user: User):
    if can_access_portfolio(current_user):
        return None
    flash(request, "Portfolio access requires an active Basic or Elite plan.", "info")
    return RedirectResponse("/dashboard/upgrade", status_code=303)


@router.get("", response_class=HTMLResponse)
def dashboard_home(
    request: Request,
    success: str | None = None,
    canceled: str | None = None,
    plan: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if success is not None or canceled is not None or plan is not None:
        normalized_plan = _normalize_plan(plan)
        db.refresh(current_user)

        if _query_flag_enabled(success):
            if (
                normalized_plan in {"basic", "elite"}
                and current_user.subscription_status == "active"
                and current_user.subscription_tier == normalized_plan
            ):
                flash(
                    request,
                    f"Your {normalized_plan.capitalize()} plan is active.",
                    "success",
                )
            else:
                flash(
                    request,
                    "Your checkout completed. Billing is still processing.",
                    "info",
                )
        elif _query_flag_enabled(canceled):
            flash(request, "Checkout canceled. No charge was made.", "info")

        return RedirectResponse("/dashboard", status_code=303)

    profile = _get_profile(current_user, db)
    show_dashboard_analytics = can_access_analytics(current_user)
    stats = analytics_service.get_summary(profile.id, db) if profile and show_dashboard_analytics else None
    analytics_overview = (
        analytics_service.get_profile_view_overview(profile.id, db)
        if profile and show_dashboard_analytics
        else None
    )
    completion_score = _get_profile_completion_score(profile)
    csrf_token = get_csrf_token(request)
    dashboard_ad_client_id = settings.adsense_client_id.strip()
    dashboard_ad_slot = settings.adsense_dashboard_slot.strip()
    show_dashboard_ad = (
        should_show_ads(current_user)
        and bool(dashboard_ad_client_id and dashboard_ad_slot)
    )
    plan_label = current_plan_label(current_user)

    return templates.TemplateResponse(
        "dashboard/index.html",
        {
            "request": request,
            "user": current_user,
            "profile": profile,
            "stats": stats,
            "analytics_overview": analytics_overview,
            "show_dashboard_analytics": show_dashboard_analytics,
            "completion_score": completion_score,
            "base_url": str(request.base_url).rstrip("/"),
            "csrf_token": csrf_token,
            "current_plan_label": plan_label,
            "show_upgrade_callout": plan_label == "Free" and current_user.role != "admin",
            "show_manage_subscription": can_manage_subscription(current_user),
            "show_dashboard_ad": show_dashboard_ad,
            "dashboard_ad_client_id": dashboard_ad_client_id,
            "dashboard_ad_slot": dashboard_ad_slot,
        },
    )


# ── Basic profile info ────────────────────────────────────────────────────────

@router.get("/profile", response_class=HTMLResponse)
def profile_edit_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    return templates.TemplateResponse(
        "dashboard/profile_edit.html",
        {"request": request, "user": current_user, "profile": profile},
    )


@router.post("/profile", response_class=HTMLResponse)
async def profile_edit_submit(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    full_name: str = Form(""),
    headline: str = Form(""),
    bio: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    location: str = Form(""),
    website: str = Form(""),
    twitter: str = Form(""),
    github: str = Form(""),
    telegram: str = Form(""),
    slug: str = Form(""),
    is_public: str = Form("off"),
    recruiter_visibility: str = Form("off"),
    freelance_availability: str = Form("off"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)

    def _render_edit_with_errors(errors: dict, status_code: int):
        """Return the edit form with submitted values still populated."""
        # Update profile fields in-memory so the template reflects what the user typed.
        # db.commit() is never called here, so these changes are discarded after the response.
        if profile:
            profile.full_name = full_name
            profile.headline = headline
            profile.bio = bio
            profile.email = email
            profile.phone = phone
            profile.location = location
            profile.website = website
            profile.twitter = twitter
            profile.github = github
            profile.telegram = telegram
            profile.slug = slug or profile.slug
            profile.is_public = (is_public == "on")
            profile.recruiter_visibility = (recruiter_visibility == "on")
            profile.freelance_availability = (freelance_availability == "on")
        return templates.TemplateResponse(
            "dashboard/profile_edit.html",
            {"request": request, "user": current_user, "profile": profile, "errors": errors},
            status_code=status_code,
        )

    try:
        data = ProfileUpdate(
            full_name=full_name,
            headline=headline,
            bio=bio,
            email=email,
            phone=phone,
            location=location,
            website=website,
            twitter=twitter,
            github=github,
            telegram=telegram,
            slug=slug or None,
            is_public=(is_public == "on"),
            recruiter_visibility=(recruiter_visibility == "on"),
            freelance_availability=(freelance_availability == "on"),
        )
        profile_service.update_profile(profile, data, db)
        flash(request, "Profile updated successfully!", "success")
        return RedirectResponse("/dashboard/profile", status_code=303)

    except ValidationError as e:
        return _render_edit_with_errors(format_pydantic_errors(e), 422)
    except profile_service.SlugTaken:
        return _render_edit_with_errors({"slug": "That profile URL is already taken."}, 400)
    except Exception as e:
        logger.error(f"Profile update error for user {current_user.id}: {e}", exc_info=True)
        flash(request, "An error occurred while saving your profile.", "error")
        return _render_edit_with_errors({}, 500)


# ── Profile image upload ───────────────────────────────────────────────────────

@router.post("/profile/image", response_class=HTMLResponse)
async def upload_profile_image(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    old_profile_image = profile.profile_image
    try:
        path = await file_service.save_profile_image(file, current_user.id)
        data = ProfileUpdate(profile_image=path)
        profile_service.update_profile(profile, data, db)
        if old_profile_image and old_profile_image != path:
            _delete_upload_url(old_profile_image)
        flash(request, "Profile image updated!", "success")
    except Exception as e:
        logger.error(f"Image upload error for user {current_user.id}: {e}", exc_info=True)
        flash(request, "Failed to upload image.", "error")
        return templates.TemplateResponse(
            "dashboard/profile_edit.html",
            {"request": request, "user": current_user, "profile": profile},
            status_code=400,
        )
    return RedirectResponse("/dashboard/profile", status_code=303)


# ── Resume PDF upload ──────────────────────────────────────────────────────────

@router.post("/profile/resume", response_class=HTMLResponse)
async def upload_resume(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    old_resume = profile.resume_pdf
    try:
        path = await file_service.save_resume_pdf(file, current_user.id)
        data = ProfileUpdate(resume_pdf=path)
        profile_service.update_profile(profile, data, db)
        if old_resume and old_resume != path:
            _delete_upload_url(old_resume)
        flash(request, "Resume uploaded successfully!", "success")
    except Exception as e:
        logger.error(f"Resume upload error for user {current_user.id}: {e}", exc_info=True)
        flash(request, "Failed to upload resume.", "error")
        return templates.TemplateResponse(
            "dashboard/profile_edit.html",
            {"request": request, "user": current_user, "profile": profile},
            status_code=400,
        )
    return RedirectResponse("/dashboard/profile", status_code=303)


# ── Experience ────────────────────────────────────────────────────────────────

@router.get("/experience", response_class=HTMLResponse)
def experience_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    return templates.TemplateResponse(
        "dashboard/experience.html",
        {"request": request, "user": current_user, "profile": profile},
    )


@router.post("/experience/add", response_class=HTMLResponse)
def add_experience(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    company: str = Form(...),
    title: str = Form(...),
    location: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    is_current: str = Form("off"),
    description: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    try:
        data = ExperienceCreate(
            company=company, title=title, location=location,
            start_date=start_date, end_date=end_date,
            is_current=(is_current == "on"), description=description,
            display_order=len(profile.experiences),
        )
        profile_service.add_experience(profile, data, db)
        flash(request, "Experience added!", "success")
        return RedirectResponse("/dashboard/experience", status_code=303)
    except ValidationError as e:
        return templates.TemplateResponse(
            "dashboard/experience.html",
            {
                "request": request,
                "user": current_user,
                "profile": profile,
                "errors": format_pydantic_errors(e),
            },
            status_code=422,
        )


@router.get("/experience/{exp_id}/edit", response_class=HTMLResponse)
def edit_experience_page(
    request: Request,
    exp_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.profile import Experience
    profile = _get_profile(current_user, db)
    exp = db.query(Experience).filter(
        Experience.id == exp_id, Experience.profile_id == profile.id
    ).first()
    if not exp:
        flash(request, "Experience not found.", "error")
        return RedirectResponse("/dashboard/experience", status_code=303)
    return templates.TemplateResponse(
        "dashboard/experience.html",
        {"request": request, "user": current_user, "profile": profile, "edit_exp": exp},
    )


@router.post("/experience/{exp_id}/edit", response_class=HTMLResponse)
def edit_experience_submit(
    request: Request,
    exp_id: int,
    csrf_token: str = Depends(require_csrf),
    company: str = Form(...),
    title: str = Form(...),
    location: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    is_current: str = Form("off"),
    description: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from types import SimpleNamespace
    profile = _get_profile(current_user, db)
    try:
        data = ExperienceCreate(
            company=company, title=title, location=location,
            start_date=start_date, end_date=end_date,
            is_current=(is_current == "on"), description=description,
        )
        profile_service.update_experience(exp_id, profile, data, db)
        flash(request, "Experience updated!", "success")
        return RedirectResponse("/dashboard/experience", status_code=303)
    except ValidationError as e:
        # Return the edit form with submitted values and field-level errors
        edit_exp = SimpleNamespace(
            id=exp_id, company=company, title=title, location=location,
            start_date=start_date, end_date=end_date,
            is_current=(is_current == "on"), description=description,
        )
        return templates.TemplateResponse(
            "dashboard/experience.html",
            {
                "request": request,
                "user": current_user,
                "profile": profile,
                "edit_exp": edit_exp,
                "errors": format_pydantic_errors(e),
            },
            status_code=422,
        )


@router.post("/experience/{exp_id}/delete", response_class=HTMLResponse)
def delete_experience(
    request: Request,
    exp_id: int,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    profile_service.delete_experience(exp_id, profile, db)
    flash(request, "Experience removed.", "info")
    return RedirectResponse("/dashboard/experience", status_code=303)


# ── Education ─────────────────────────────────────────────────────────────────

@router.get("/education", response_class=HTMLResponse)
def education_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    return templates.TemplateResponse(
        "dashboard/education.html",
        {"request": request, "user": current_user, "profile": profile},
    )


@router.post("/education/add", response_class=HTMLResponse)
async def add_education(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    school: str = Form(...),
    degree: str = Form(""),
    field: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    description: str = Form(""),
    certificate: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    certificate_url = ""
    uploaded_certificate_url = ""
    if certificate and certificate.filename:
        try:
            uploaded_certificate_url = await file_service.save_certificate_file(certificate, current_user.id)
            certificate_url = uploaded_certificate_url
        except HTTPException as exc:
            return templates.TemplateResponse(
                "dashboard/education.html",
                {
                    "request": request,
                    "user": current_user,
                    "profile": profile,
                    "errors": {"certificate": exc.detail},
                },
                status_code=exc.status_code,
            )
    try:
        data = EducationCreate(
            school=school, degree=degree, field=field,
            start_date=start_date, end_date=end_date, description=description,
            certificate_url=certificate_url,
            display_order=len(profile.educations),
        )
        profile_service.add_education(profile, data, db)
        flash(request, "Education added!", "success")
        return RedirectResponse("/dashboard/education", status_code=303)
    except ValidationError as e:
        if uploaded_certificate_url:
            _delete_upload_url(uploaded_certificate_url)
        return templates.TemplateResponse(
            "dashboard/education.html",
            {
                "request": request,
                "user": current_user,
                "profile": profile,
                "errors": format_pydantic_errors(e),
            },
            status_code=422,
        )
    except Exception:
        if uploaded_certificate_url:
            _delete_upload_url(uploaded_certificate_url)
        raise


@router.get("/education/{edu_id}/edit", response_class=HTMLResponse)
def edit_education_page(
    request: Request,
    edu_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.profile import Education
    profile = _get_profile(current_user, db)
    edu = db.query(Education).filter(
        Education.id == edu_id, Education.profile_id == profile.id
    ).first()
    if not edu:
        flash(request, "Education not found.", "error")
        return RedirectResponse("/dashboard/education", status_code=303)
    return templates.TemplateResponse(
        "dashboard/education.html",
        {"request": request, "user": current_user, "profile": profile, "edit_edu": edu},
    )


@router.post("/education/{edu_id}/edit", response_class=HTMLResponse)
async def edit_education_submit(
    request: Request,
    edu_id: int,
    csrf_token: str = Depends(require_csrf),
    school: str = Form(...),
    degree: str = Form(""),
    field: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    description: str = Form(""),
    certificate: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    try:
        from app.models.profile import Education
        edu = db.query(Education).filter(
            Education.id == edu_id, Education.profile_id == profile.id
        ).first()
        if not edu:
            flash(request, "Education not found.", "error")
            return RedirectResponse("/dashboard/education", status_code=303)

        uploaded_certificate_url = ""
        new_certificate_url = edu.certificate_url
        if certificate and certificate.filename:
            try:
                uploaded_certificate_url = await file_service.save_certificate_file(certificate, current_user.id)
                new_certificate_url = uploaded_certificate_url
            except HTTPException as exc:
                return templates.TemplateResponse(
                    "dashboard/education.html",
                    {
                        "request": request,
                        "user": current_user,
                        "profile": profile,
                        "edit_edu": edu,
                        "errors": {"certificate": exc.detail},
                    },
                    status_code=exc.status_code,
                )

        data = EducationCreate(
            school=school, degree=degree, field=field,
            start_date=start_date, end_date=end_date, description=description,
            certificate_url=new_certificate_url,
        )
        old_certificate_url = edu.certificate_url
        profile_service.update_education(edu_id, profile, data, db)
        if uploaded_certificate_url and old_certificate_url and old_certificate_url != uploaded_certificate_url:
            _delete_upload_url(old_certificate_url)
        flash(request, "Education updated!", "success")
    except ValidationError as e:
        if "uploaded_certificate_url" in locals() and uploaded_certificate_url:
            _delete_upload_url(uploaded_certificate_url)
        flash(request, "Invalid data. Please check your input.", "error")
    except Exception as e:
        if "uploaded_certificate_url" in locals() and uploaded_certificate_url:
            _delete_upload_url(uploaded_certificate_url)
        logger.error(f"Error updating education: {e}")
        flash(request, "An error occurred while updating education.", "error")
    return RedirectResponse("/dashboard/education", status_code=303)


@router.post("/education/{edu_id}/remove-certificate", response_class=HTMLResponse)
async def remove_education_certificate(
    request: Request,
    edu_id: int,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.profile import Education
    profile = _get_profile(current_user, db)
    edu = db.query(Education).filter(
        Education.id == edu_id, Education.profile_id == profile.id
    ).first()
    
    if edu and edu.certificate_url:
        _delete_upload_url(edu.certificate_url)
        edu.certificate_url = ""
        db.commit()
        flash(request, "Certificate removed.", "success")
    
    return RedirectResponse(f"/dashboard/education/{edu_id}/edit", status_code=303)


@router.post("/education/{edu_id}/delete", response_class=HTMLResponse)
def delete_education(
    request: Request,
    edu_id: int,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    profile_service.delete_education(edu_id, profile, db)
    flash(request, "Education removed.", "info")
    return RedirectResponse("/dashboard/education", status_code=303)


# ── Skills ────────────────────────────────────────────────────────────────────

@router.get("/skills", response_class=HTMLResponse)
def skills_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    return templates.TemplateResponse(
        "dashboard/skills.html",
        {"request": request, "user": current_user, "profile": profile, "csrf_token": get_csrf_token(request)},
    )


@router.post("/skills", response_class=HTMLResponse)
def save_skills(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    skills_raw: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    skill_objs = []
    for raw in skills_raw.split("\n"):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split("|", 1)
        name = parts[0].strip()
        category = parts[1].strip() if len(parts) > 1 else ""
        if name:
            skill_objs.append(SkillCreate(name=name, category=category))
    try:
        profile_service.replace_skills(profile, skill_objs, db)
        flash(request, "Skills updated!", "success")
    except HTTPException as e:
        flash(request, e.detail, "error")
    return RedirectResponse("/dashboard/skills", status_code=303)


@router.post("/skills/{skill_id}/edit", response_class=HTMLResponse)
def edit_skill(
    request: Request,
    skill_id: int,
    csrf_token: str = Depends(require_csrf),
    name: str = Form(...),
    category: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)

    data = SkillCreate(name=name, category=category)
    skill = profile_service.update_skill(skill_id, profile, data, db)

    if not skill:
        flash(request, "Skill not found.", "error")
    else:
        flash(request, "Skill updated!", "success")

    return RedirectResponse("/dashboard/skills", status_code=303)


@router.post("/skills/{skill_id}/delete", response_class=HTMLResponse)
def delete_skill(
    request: Request,
    skill_id: int,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)

    success = profile_service.delete_skill(skill_id, profile, db)
    if success:
        flash(request, "Skill removed.", "success")
    else:
        flash(request, "Skill not found.", "error")

    return RedirectResponse("/dashboard/skills", status_code=303)


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("/projects", response_class=HTMLResponse)
def projects_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    access_redirect = _require_portfolio_access(request, current_user)
    if access_redirect:
        return access_redirect
    profile = _get_profile(current_user, db)
    return templates.TemplateResponse(
        "dashboard/projects.html",
        {"request": request, "user": current_user, "profile": profile},
    )


async def _get_project_thumbnail(url: str) -> str:
    """Return a thumbnail URL for known video platforms; empty string otherwise."""
    if not url:
        return ""

    import re
    import httpx

    # 1. YouTube — derive thumbnail from video ID (no HTTP request needed)
    yt_match = re.search(
        r"(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^\"&?\/\s]{11})",
        url,
    )
    if yt_match:
        return f"https://img.youtube.com/vi/{yt_match.group(1)}/maxresdefault.jpg"

    # 2. Vimeo — official JSON API (safe, no HTML parsing)
    vimeo_match = re.search(r"vimeo\.com\/(?:.*\/)?([0-9]+)", url)
    if vimeo_match:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://vimeo.com/api/v2/video/{vimeo_match.group(1)}.json",
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data[0].get("thumbnail_large", "")
        except Exception:
            pass

    return ""


@router.post("/projects/add", response_class=HTMLResponse)
async def add_project(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    name: str = Form(...),
    description: str = Form(""),
    url: str = Form(""),
    thumbnail: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    access_redirect = _require_portfolio_access(request, current_user)
    if access_redirect:
        return access_redirect
    profile = _get_profile(current_user, db)
    thumbnail_url = ""
    uploaded_thumbnail_url = ""
    
    # Priority A: Uploaded image
    if thumbnail and thumbnail.filename:
        try:
            uploaded_thumbnail_url = await file_service.save_project_thumbnail(thumbnail, current_user.id)
            thumbnail_url = uploaded_thumbnail_url
        except Exception as e:
            logger.warning(f"Project thumbnail upload failed: {e}")
            flash(request, f"Thumbnail upload failed: {str(e)}", "error")
    
    # Priority B & C: Video URL or Open Graph (only if no upload)
    if not thumbnail_url and url:
        thumbnail_url = await _get_project_thumbnail(url)
        
    try:
        data = ProjectCreate(
            name=name, description=description, url=url,
            thumbnail_url=thumbnail_url,
            display_order=len(profile.projects),
        )
        profile_service.add_project(profile, data, db)
        flash(request, "Project added!", "success")
        return RedirectResponse("/dashboard/projects", status_code=303)
    except ValidationError as e:
        if uploaded_thumbnail_url:
            _delete_upload_url(uploaded_thumbnail_url)
        return templates.TemplateResponse(
            "dashboard/projects.html",
            {
                "request": request,
                "user": current_user,
                "profile": profile,
                "errors": format_pydantic_errors(e),
            },
            status_code=422,
        )
    except Exception:
        if uploaded_thumbnail_url:
            _delete_upload_url(uploaded_thumbnail_url)
        raise


@router.get("/projects/{proj_id}/edit", response_class=HTMLResponse)
def edit_project_page(
    request: Request,
    proj_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.profile import Project
    access_redirect = _require_portfolio_access(request, current_user)
    if access_redirect:
        return access_redirect
    profile = _get_profile(current_user, db)
    proj = db.query(Project).filter(
        Project.id == proj_id, Project.profile_id == profile.id
    ).first()
    if not proj:
        flash(request, "Project not found.", "error")
        return RedirectResponse("/dashboard/projects", status_code=303)
    return templates.TemplateResponse(
        "dashboard/projects.html",
        {"request": request, "user": current_user, "profile": profile, "edit_proj": proj},
    )


@router.post("/projects/{proj_id}/edit", response_class=HTMLResponse)
async def edit_project_submit(
    request: Request,
    proj_id: int,
    csrf_token: str = Depends(require_csrf),
    name: str = Form(...),
    description: str = Form(""),
    url: str = Form(""),
    thumbnail: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.profile import Project
    access_redirect = _require_portfolio_access(request, current_user)
    if access_redirect:
        return access_redirect
    profile = _get_profile(current_user, db)
    proj = db.query(Project).filter(
        Project.id == proj_id, Project.profile_id == profile.id
    ).first()
    if not proj:
        flash(request, "Project not found.", "error")
        return RedirectResponse("/dashboard/projects", status_code=303)

    thumbnail_url = proj.thumbnail_url
    
    # Priority A: New upload
    if thumbnail and thumbnail.filename:
        try:
            thumbnail_url = await file_service.save_project_thumbnail(thumbnail, current_user.id)
        except Exception as e:
            logger.warning(f"Project thumbnail upload failed: {e}")
            flash(request, f"Upload failed: {str(e)}", "error")
    
    # Priority B & C: Only refresh if no current thumbnail or it was an auto-generated one
    elif not thumbnail_url or not thumbnail_url.startswith("/uploads/"):
         refreshed_thumb = await _get_project_thumbnail(url)
         if refreshed_thumb:
             thumbnail_url = refreshed_thumb

    try:
        data = ProjectCreate(
            name=name, description=description, url=url,
            thumbnail_url=thumbnail_url,
        )
        old_thumbnail_url = proj.thumbnail_url
        profile_service.update_project(proj_id, profile, data, db)
        if thumbnail and thumbnail.filename and old_thumbnail_url and old_thumbnail_url != thumbnail_url:
            _delete_upload_url(old_thumbnail_url)
        flash(request, "Project updated!", "success")
    except ValidationError as e:
        if thumbnail and thumbnail.filename and thumbnail_url and thumbnail_url != proj.thumbnail_url:
            _delete_upload_url(thumbnail_url)
        flash(request, "Invalid data. Please check your input.", "error")
    return RedirectResponse("/dashboard/projects", status_code=303)


@router.post("/projects/{proj_id}/remove-thumbnail", response_class=HTMLResponse)
async def remove_project_thumbnail(
    request: Request,
    proj_id: int,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.profile import Project
    access_redirect = _require_portfolio_access(request, current_user)
    if access_redirect:
        return access_redirect
    profile = _get_profile(current_user, db)
    proj = db.query(Project).filter(
        Project.id == proj_id, Project.profile_id == profile.id
    ).first()
    
    if proj and proj.thumbnail_url:
        _delete_upload_url(proj.thumbnail_url)
        proj.thumbnail_url = ""
        db.commit()
        flash(request, "Thumbnail removed.", "success")
    
    return RedirectResponse(f"/dashboard/projects/{proj_id}/edit", status_code=303)


@router.post("/projects/{proj_id}/delete", response_class=HTMLResponse)
def delete_project(
    request: Request,
    proj_id: int,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    access_redirect = _require_portfolio_access(request, current_user)
    if access_redirect:
        return access_redirect
    profile = _get_profile(current_user, db)
    profile_service.delete_project(proj_id, profile, db)
    flash(request, "Project removed.", "info")
    return RedirectResponse("/dashboard/projects", status_code=303)


# ── QR Code ───────────────────────────────────────────────────────────────────

@router.get("/qr", response_class=HTMLResponse)
def qr_view(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    # Ensure QR exists (generate on first visit)
    if not profile.qr_code:
        qr_service.generate_qr_for_profile(profile, db)
        db.refresh(profile)
    show_qr_analytics = can_access_analytics(current_user)
    stats = analytics_service.get_summary(profile.id, db) if profile and show_qr_analytics else None
    return templates.TemplateResponse(
        "dashboard/qr_view.html",
        {
            "request": request,
            "user": current_user,
            "profile": profile,
            "show_qr_analytics": show_qr_analytics,
            "qr_scans": stats.qr_scans if stats else 0,
            "base_url": str(request.base_url).rstrip("/"),
        },
    )


@router.post("/qr/regenerate", response_class=HTMLResponse)
def qr_regenerate(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    qr_service.generate_qr_for_profile(profile, db, force=True)
    flash(request, "QR Identity successfully regenerated!", "success")
    return RedirectResponse("/dashboard/qr?regenerated=1", status_code=303)


# ── Profile image delete ──────────────────────────────────────────────────────

@router.post("/profile/image/delete", response_class=HTMLResponse)
def delete_profile_image(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    if profile.profile_image:
        _delete_upload_url(profile.profile_image)
        data = ProfileUpdate(profile_image="")
        profile_service.update_profile(profile, data, db)
        flash(request, "Profile photo removed.", "info")
    return RedirectResponse("/dashboard/profile", status_code=303)


# ── Upgrade to Elite ──────────────────────────────────────────────────────────

@router.get("/upgrade", response_class=HTMLResponse)
def upgrade_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    basic_checkout_enabled = bool(settings.stripe_secret_key and settings.stripe_price_basic)
    elite_checkout_enabled = bool(settings.stripe_secret_key and settings.get_stripe_price("elite"))

    return templates.TemplateResponse(
        "dashboard/upgrade.html",
        {
            "request": request,
            "user": current_user,
            "profile": profile,
            "basic_checkout_enabled": basic_checkout_enabled,
            "elite_checkout_enabled": elite_checkout_enabled,
        },
    )


# ── Digital Card Preview ──────────────────────────────────────────────────────

@router.get("/card", response_class=HTMLResponse)
def card_preview(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    if profile and not profile.qr_code:
        qr_service.generate_qr_for_profile(profile, db)
        db.refresh(profile)
    return templates.TemplateResponse(
        "dashboard/card_preview.html",
        {"request": request, "user": current_user, "profile": profile},
    )


# ── Elite Customization Uploads ───────────────────────────────────────────────

def _require_elite_tier(current_user: User) -> None:
    """Raise 403 if user does not have an active elite subscription."""
    if not can_access_elite_features(current_user):
        raise HTTPException(status_code=403, detail="Elite subscription required")


@router.post("/profile/elite/header", response_class=HTMLResponse)
async def upload_elite_header(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_elite_tier(current_user)
    profile = _get_profile(current_user, db)
    try:
        path = await file_service.save_profile_image(file, current_user.id)
        from app.schemas.profile import ProfileUpdate
        profile_service.update_profile(profile, ProfileUpdate(custom_header_url=path), db)
        flash(request, "Custom header updated!", "success")
    except Exception as e:
        logger.error(f"Header upload error: {e}", exc_info=True)
        flash(request, "Failed to upload header image.", "error")
    return RedirectResponse("/dashboard/profile", status_code=303)


@router.post("/profile/elite/background", response_class=HTMLResponse)
async def upload_elite_background(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_elite_tier(current_user)
    profile = _get_profile(current_user, db)
    try:
        path = await file_service.save_profile_image(file, current_user.id)
        from app.schemas.profile import ProfileUpdate
        profile_service.update_profile(profile, ProfileUpdate(custom_background_url=path), db)
        flash(request, "Custom background updated!", "success")
    except Exception as e:
        logger.error(f"Background upload error: {e}", exc_info=True)
        flash(request, "Failed to upload background image.", "error")
    return RedirectResponse("/dashboard/profile", status_code=303)


@router.post("/profile/elite/image2", response_class=HTMLResponse)
async def upload_elite_image2(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_elite_tier(current_user)
    profile = _get_profile(current_user, db)
    try:
        path = await file_service.save_profile_image(file, current_user.id)
        from app.schemas.profile import ProfileUpdate
        profile_service.update_profile(profile, ProfileUpdate(profile_image_2=path), db)
        flash(request, "Additional photo uploaded!", "success")
    except Exception as e:
        logger.error(f"Image2 upload error: {e}", exc_info=True)
        flash(request, "Failed to upload image.", "error")
    return RedirectResponse("/dashboard/profile", status_code=303)


@router.post("/profile/elite/image3", response_class=HTMLResponse)
async def upload_elite_image3(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_elite_tier(current_user)
    profile = _get_profile(current_user, db)
    try:
        path = await file_service.save_profile_image(file, current_user.id)
        from app.schemas.profile import ProfileUpdate
        profile_service.update_profile(profile, ProfileUpdate(profile_image_3=path), db)
        flash(request, "Additional photo uploaded!", "success")
    except Exception as e:
        logger.error(f"Image3 upload error: {e}", exc_info=True)
        flash(request, "Failed to upload image.", "error")
    return RedirectResponse("/dashboard/profile", status_code=303)
