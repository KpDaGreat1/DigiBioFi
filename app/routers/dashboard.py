"""
Dashboard routes — authenticated user home, account, profile edit, QR, card preview.
"""
import logging
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, get_current_user
from app.core.templates import templates
from app.models.user import User
from app.schemas.profile import (
    ProfileUpdate,
    ExperienceCreate, EducationCreate, SkillCreate,
    ProjectCreate, CertificationCreate, AwardCreate, CustomSectionCreate,
)
from app.services import profile_service, qr_service, file_service, analytics_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)


def _get_profile(user: User, db: Session):
    """Convenience: return profile or redirect to dashboard if missing."""
    from app.services.profile_service import get_profile_by_user, ProfileNotFound
    try:
        return get_profile_by_user(user.id, db)
    except ProfileNotFound:
        return None


# ── Dashboard home ────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def dashboard_home(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    stats = analytics_service.get_summary(profile.id, db) if profile else None
    return templates.TemplateResponse(
        "dashboard/index.html",
        {
            "request": request,
            "user": current_user,
            "profile": profile,
            "stats": stats,
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
def profile_edit_submit(
    request: Request,
    full_name: str = Form(""),
    headline: str = Form(""),
    bio: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    location: str = Form(""),
    website: str = Form(""),
    linkedin: str = Form(""),
    twitter: str = Form(""),
    github: str = Form(""),
    slug: str = Form(""),
    is_public: str = Form("off"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    error = None
    try:
        data = ProfileUpdate(
            full_name=full_name,
            headline=headline,
            bio=bio,
            email=email,
            phone=phone,
            location=location,
            website=website,
            linkedin=linkedin,
            twitter=twitter,
            github=github,
            slug=slug or None,
            is_public=(is_public == "on"),
        )
        profile_service.update_profile(profile, data, db)
        return RedirectResponse("/dashboard/profile?saved=1", status_code=303)
    except profile_service.SlugTaken as e:
        logger.warning(f"User {current_user.id} attempted to use taken slug: {e}")
        error = "That profile URL is already taken. Please choose another."
    except Exception as e:
        logger.error(f"Profile update error for user {current_user.id}: {e}", exc_info=True)
        error = "An error occurred while saving your profile. Please try again."

    return templates.TemplateResponse(
        "dashboard/profile_edit.html",
        {"request": request, "user": current_user, "profile": profile, "error": error},
        status_code=400,
    )


# ── Profile image upload ───────────────────────────────────────────────────────

@router.post("/profile/image", response_class=HTMLResponse)
async def upload_profile_image(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    try:
        path = await file_service.save_profile_image(file, current_user.id)
        data = ProfileUpdate(profile_image=path)
        profile_service.update_profile(profile, data, db)
    except Exception as e:
        logger.error(f"Image upload error for user {current_user.id}: {e}", exc_info=True)
        return templates.TemplateResponse(
            "dashboard/profile_edit.html",
            {"request": request, "user": current_user, "profile": profile, "image_error": "Failed to upload image. Please check the file and try again."},
            status_code=400,
        )
    return RedirectResponse("/dashboard/profile?saved=1", status_code=303)


# ── Resume PDF upload ──────────────────────────────────────────────────────────

@router.post("/profile/resume", response_class=HTMLResponse)
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    try:
        path = await file_service.save_resume_pdf(file, current_user.id)
        data = ProfileUpdate(resume_pdf=path)
        profile_service.update_profile(profile, data, db)
    except Exception as e:
        logger.error(f"Resume upload error for user {current_user.id}: {e}", exc_info=True)
        return templates.TemplateResponse(
            "dashboard/profile_edit.html",
            {"request": request, "user": current_user, "profile": profile, "resume_error": "Failed to upload resume. Please check the file is a valid PDF and try again."},
            status_code=400,
        )
    return RedirectResponse("/dashboard/profile?saved=1", status_code=303)


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
    data = ExperienceCreate(
        company=company, title=title, location=location,
        start_date=start_date, end_date=end_date,
        is_current=(is_current == "on"), description=description,
        display_order=len(profile.experiences),
    )
    profile_service.add_experience(profile, data, db)
    return RedirectResponse("/dashboard/experience?saved=1", status_code=303)


@router.post("/experience/{exp_id}/delete", response_class=HTMLResponse)
def delete_experience(
    exp_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    profile_service.delete_experience(exp_id, profile, db)
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
def add_education(
    request: Request,
    school: str = Form(...),
    degree: str = Form(""),
    field: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    description: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    data = EducationCreate(
        school=school, degree=degree, field=field,
        start_date=start_date, end_date=end_date, description=description,
        display_order=len(profile.educations),
    )
    profile_service.add_education(profile, data, db)
    return RedirectResponse("/dashboard/education?saved=1", status_code=303)


@router.post("/education/{edu_id}/delete", response_class=HTMLResponse)
def delete_education(
    edu_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    profile_service.delete_education(edu_id, profile, db)
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
        {"request": request, "user": current_user, "profile": profile},
    )


@router.post("/skills", response_class=HTMLResponse)
def save_skills(
    request: Request,
    skills_raw: str = Form(""),      # comma-separated list of "name|category" pairs
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
    profile_service.replace_skills(profile, skill_objs, db)
    return RedirectResponse("/dashboard/skills?saved=1", status_code=303)


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("/projects", response_class=HTMLResponse)
def projects_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    return templates.TemplateResponse(
        "dashboard/projects.html",
        {"request": request, "user": current_user, "profile": profile},
    )


@router.post("/projects/add", response_class=HTMLResponse)
def add_project(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    url: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    data = ProjectCreate(name=name, description=description, url=url,
                         display_order=len(profile.projects))
    profile_service.add_project(profile, data, db)
    return RedirectResponse("/dashboard/projects?saved=1", status_code=303)


@router.post("/projects/{proj_id}/delete", response_class=HTMLResponse)
def delete_project(
    proj_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    profile_service.delete_project(proj_id, profile, db)
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
    return templates.TemplateResponse(
        "dashboard/qr_view.html",
        {"request": request, "user": current_user, "profile": profile},
    )


@router.post("/qr/regenerate", response_class=HTMLResponse)
def qr_regenerate(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    qr_service.generate_qr_for_profile(profile, db)
    return RedirectResponse("/dashboard/qr?regenerated=1", status_code=303)


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
