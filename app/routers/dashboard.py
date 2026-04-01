"""
Dashboard routes — authenticated user home, account, profile edit, QR, card preview.
"""
import logging
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import ValidationError
import logging

from app.core.dependencies import get_db, get_current_user, require_elite, require_csrf
from app.core.security import generate_csrf_token
from app.core.templates import templates, flash, get_csrf_token
from app.models.user import User
from app.schemas.profile import (
    ProfileUpdate,
    ExperienceCreate, EducationCreate, SkillCreate,
    ProjectCreate, CertificationCreate, AwardCreate, CustomSectionCreate,
)
from app.services import profile_service, qr_service, file_service, analytics_service
from app.utils.validators import format_pydantic_errors

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)


async def _save_certificate(upload: UploadFile, user_id: int) -> str:
    """Save certificate file (JPG/PNG/PDF) to uploads/certificates/."""
    import secrets
    from pathlib import Path
    from app.core.config import settings

    allowed = {"image/jpeg", "image/png", "application/pdf"}
    if upload.content_type not in allowed:
        raise ValueError("Certificate must be JPG, PNG, or PDF")
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}
    ext = ext_map[upload.content_type]
    suffix = secrets.token_hex(4)
    filename = f"cert_{user_id}_{suffix}.{ext}"
    dest = Path(settings.upload_dir) / "certificates" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = await upload.read()
    if len(content) > 5 * 1024 * 1024:
        raise ValueError("Certificate file exceeds 5MB limit")
    dest.write_bytes(content)
    return f"/uploads/certificates/{filename}"


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


@router.get("", response_class=HTMLResponse)
def dashboard_home(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    stats = analytics_service.get_summary(profile.id, db) if profile else None
    
    completion_score = _get_profile_completion_score(profile)

    csrf_token = get_csrf_token(request)

    return templates.TemplateResponse(
        "dashboard/index.html",
        {
            "request": request,
            "user": current_user,
            "profile": profile,
            "stats": stats,
            "completion_score": completion_score,
            "base_url": str(request.base_url).rstrip("/"),
            "csrf_token": csrf_token,
        },
    )


# ── Basic profile info ────────────────────────────────────────────────────────

@router.get("/profile", response_class=HTMLResponse)
def profile_edit_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    
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
        return templates.TemplateResponse(
            "dashboard/profile_edit.html",
            {
                "request": request,
                "user": current_user,
                "profile": profile,
                "errors": format_pydantic_errors(e),
            },
            status_code=422,
        )
    except profile_service.SlugTaken:
        return templates.TemplateResponse(
            "dashboard/profile_edit.html",
            {
                "request": request,
                "user": current_user,
                "profile": profile,
                "errors": {"slug": "That profile URL is already taken."},
            },
            status_code=400,
        )
    except Exception as e:
        logger.error(f"Profile update error for user {current_user.id}: {e}", exc_info=True)
        flash(request, "An error occurred while saving your profile.", "error")
        return templates.TemplateResponse(
            "dashboard/profile_edit.html",
            {"request": request, "user": current_user, "profile": profile},
            status_code=500,
        )


# ── Profile image upload ───────────────────────────────────────────────────────

@router.post("/profile/image", response_class=HTMLResponse)
async def upload_profile_image(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_elite),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    try:
        path = await file_service.save_profile_image(file, current_user.id)
        data = ProfileUpdate(profile_image=path)
        profile_service.update_profile(profile, data, db)
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
    _: None = Depends(require_elite),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    try:
        path = await file_service.save_resume_pdf(file, current_user.id)
        data = ProfileUpdate(resume_pdf=path)
        profile_service.update_profile(profile, data, db)
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
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    try:
        data = ExperienceCreate(
            company=company, title=title, location=location,
            start_date=start_date, end_date=end_date,
            is_current=(is_current == "on"), description=description,
        )
        profile_service.update_experience(exp_id, profile, data, db)
        flash(request, "Experience updated!", "success")
    except ValidationError as e:
        flash(request, "Invalid data. Please check your input.", "error")
    return RedirectResponse("/dashboard/experience", status_code=303)


@router.post("/experience/{exp_id}/delete", response_class=HTMLResponse)
def delete_experience(
    request: Request,
    exp_id: int,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    certificate_url = ""
    if certificate and certificate.filename:
        try:
            certificate_url = await _save_certificate(certificate, current_user.id)
        except Exception as e:
            logger.warning(f"Certificate upload failed: {e}")
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


@router.get("/education/{edu_id}/edit", response_class=HTMLResponse)
def edit_education_page(
    request: Request,
    edu_id: int,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    certificate_url = ""
    if certificate and certificate.filename:
        try:
            certificate_url = await _save_certificate(certificate, current_user.id)
        except Exception as e:
            logger.warning(f"Certificate upload failed: {e}")
    try:
        data = EducationCreate(
            school=school, degree=degree, field=field,
            start_date=start_date, end_date=end_date, description=description,
            certificate_url=certificate_url,
        )
        profile_service.update_education(edu_id, profile, data, db)
        flash(request, "Education updated!", "success")
    except ValidationError as e:
        flash(request, "Invalid data. Please check your input.", "error")
    return RedirectResponse("/dashboard/education", status_code=303)


@router.post("/education/{edu_id}/delete", response_class=HTMLResponse)
def delete_education(
    request: Request,
    edu_id: int,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
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
    csrf_token: str = Depends(require_csrf),
    name: str = Form(...),
    description: str = Form(""),
    url: str = Form(""),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_elite),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    try:
        data = ProjectCreate(name=name, description=description, url=url,
                             display_order=len(profile.projects))
        profile_service.add_project(profile, data, db)
        flash(request, "Project added!", "success")
        return RedirectResponse("/dashboard/projects", status_code=303)
    except ValidationError as e:
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


@router.get("/projects/{proj_id}/edit", response_class=HTMLResponse)
def edit_project_page(
    request: Request,
    proj_id: int,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_elite),
    db: Session = Depends(get_db),
):
    from app.models.profile import Project
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
def edit_project_submit(
    request: Request,
    proj_id: int,
    csrf_token: str = Depends(require_csrf),
    name: str = Form(...),
    description: str = Form(""),
    url: str = Form(""),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_elite),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    try:
        data = ProjectCreate(name=name, description=description, url=url)
        profile_service.update_project(proj_id, profile, data, db)
        flash(request, "Project updated!", "success")
    except ValidationError as e:
        flash(request, "Invalid data. Please check your input.", "error")
    return RedirectResponse("/dashboard/projects", status_code=303)


@router.post("/projects/{proj_id}/delete", response_class=HTMLResponse)
def delete_project(
    request: Request,
    proj_id: int,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_elite),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    profile_service.delete_project(proj_id, profile, db)
    flash(request, "Project removed.", "info")
    return RedirectResponse("/dashboard/projects", status_code=303)


# ── QR Code ───────────────────────────────────────────────────────────────────

@router.get("/qr", response_class=HTMLResponse)
def qr_view(
    request: Request,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_elite),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    # Ensure QR exists (generate on first visit)
    if not profile.qr_code:
        qr_service.generate_qr_for_profile(profile, db)
        db.refresh(profile)
    stats = analytics_service.get_summary(profile.id, db) if profile else None
    return templates.TemplateResponse(
        "dashboard/qr_view.html",
        {
            "request": request,
            "user": current_user,
            "profile": profile,
            "qr_scans": stats.qr_scans if stats else 0,
            "base_url": str(request.base_url).rstrip("/"),
        },
    )


@router.post("/qr/regenerate", response_class=HTMLResponse)
def qr_regenerate(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_elite),
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
    _: None = Depends(require_elite),
    db: Session = Depends(get_db),
):
    profile = _get_profile(current_user, db)
    if profile.profile_image:
        from pathlib import Path
        try:
            old_path = Path(profile.profile_image.lstrip("/"))
            if old_path.exists():
                old_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete old profile image: {e}")
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
    from app.core.config import settings as _settings
    profile = _get_profile(current_user, db)
    stripe_enabled = bool(_settings.stripe_secret_key and _settings.stripe_price_id)
    return templates.TemplateResponse(
        "dashboard/upgrade.html",
        {
            "request": request,
            "user": current_user,
            "profile": profile,
            "stripe_enabled": stripe_enabled,
        },
    )


@router.post("/subscribe", response_class=HTMLResponse)
async def subscribe(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.core.config import settings as _settings
    if not _settings.stripe_secret_key:
        flash(request, "Stripe is not configured yet.", "error")
        return RedirectResponse("/dashboard/upgrade", status_code=303)
    try:
        import stripe
        stripe.api_key = _settings.stripe_secret_key
        customer_id = current_user.stripe_customer_id or None
        if not customer_id:
            customer = stripe.Customer.create(email=current_user.email)
            current_user.stripe_customer_id = customer.id
            db.commit()
            customer_id = customer.id
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": _settings.stripe_price_id, "quantity": 1}],
            mode="subscription",
            success_url=str(request.base_url).rstrip("/") + "/billing/success",
            cancel_url=str(request.base_url).rstrip("/") + "/billing/cancel",
            metadata={"user_id": str(current_user.id)},
        )
        from fastapi.responses import RedirectResponse as RR
        return RR(session.url, status_code=303)
    except ImportError:
        flash(request, "Stripe library not installed.", "error")
        return RedirectResponse("/dashboard/upgrade", status_code=303)
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        flash(request, "Could not start checkout. Please try again.", "error")
        return RedirectResponse("/dashboard/upgrade", status_code=303)


# ── Digital Card Preview ──────────────────────────────────────────────────────

@router.get("/card", response_class=HTMLResponse)
def card_preview(
    request: Request,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_elite),
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
