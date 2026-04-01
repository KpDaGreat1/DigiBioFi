"""
Profile CRUD service — create, read, update profile and all sub-sections.
"""
from typing import Optional, List
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.profile import (
    Profile, Experience, Education, Skill,
    Project, Certification, Award, CustomSection,
)
from app.schemas.profile import (
    ProfileUpdate,
    ExperienceCreate, EducationCreate, SkillCreate,
    ProjectCreate, CertificationCreate, AwardCreate, CustomSectionCreate,
)
from app.utils.slug import unique_slug
from app.utils.validators import sanitize_text


class ProfileNotFound(Exception):
    pass


class SlugTaken(Exception):
    pass


# ── Profile ───────────────────────────────────────────────────────────────────

def get_profile_by_user(user_id: int, db: Session) -> Profile:
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    if not profile:
        raise ProfileNotFound(f"No profile found for user_id={user_id}")
    return profile


def get_profile_by_slug(slug: str, db: Session) -> Profile | None:
    return db.query(Profile).filter(Profile.slug == slug).first()


def update_profile(profile: Profile, data: ProfileUpdate, db: Session) -> Profile:
    """Apply ProfileUpdate fields to the given profile instance."""
    update_data = data.model_dump(exclude_unset=True)

    # Handle slug change — must remain unique
    if "slug" in update_data and update_data["slug"] != profile.slug:
        slug = update_data["slug"]
        conflict = db.query(Profile).filter(
            Profile.slug == slug, Profile.id != profile.id
        ).first()
        if conflict:
            raise SlugTaken(f"The slug '{slug}' is already taken.")
        profile.slug = slug
        update_data.pop("slug")

    # Sanitize user-supplied free-text fields
    for text_field in ("bio", "headline"):
        if text_field in update_data:
            update_data[text_field] = sanitize_text(update_data[text_field])

    for key, value in update_data.items():
        if hasattr(profile, key):
            setattr(profile, key, value)

    db.commit()
    db.refresh(profile)
    return profile


# ── Experience ────────────────────────────────────────────────────────────────

def add_experience(profile: Profile, data: ExperienceCreate, db: Session) -> Experience:
    exp = Experience(profile_id=profile.id, **data.model_dump())
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def update_experience(exp_id: int, profile: Profile, data: ExperienceCreate, db: Session) -> Experience:
    exp = db.query(Experience).filter(
        Experience.id == exp_id, Experience.profile_id == profile.id
    ).first()
    if not exp:
        raise ProfileNotFound(f"Experience {exp_id} not found")
    for k, v in data.model_dump().items():
        setattr(exp, k, v)
    db.commit()
    db.refresh(exp)
    return exp


def delete_experience(exp_id: int, profile: Profile, db: Session) -> None:
    exp = db.query(Experience).filter(
        Experience.id == exp_id, Experience.profile_id == profile.id
    ).first()
    if exp:
        db.delete(exp)
        db.commit()


# ── Education ─────────────────────────────────────────────────────────────────

def add_education(profile: Profile, data: EducationCreate, db: Session) -> Education:
    edu = Education(profile_id=profile.id, **data.model_dump())
    db.add(edu)
    db.commit()
    db.refresh(edu)
    return edu


def update_education(edu_id: int, profile: Profile, data: EducationCreate, db: Session) -> Education:
    edu = db.query(Education).filter(
        Education.id == edu_id, Education.profile_id == profile.id
    ).first()
    if not edu:
        raise ProfileNotFound(f"Education {edu_id} not found")
    for k, v in data.model_dump().items():
        setattr(edu, k, v)
    db.commit()
    db.refresh(edu)
    return edu


def delete_education(edu_id: int, profile: Profile, db: Session) -> None:
    edu = db.query(Education).filter(
        Education.id == edu_id, Education.profile_id == profile.id
    ).first()
    if edu:
        db.delete(edu)
        db.commit()


# ── Skills ────────────────────────────────────────────────────────────────────

def update_skill(skill_id: int, profile: Profile, data: SkillCreate, db: Session) -> Optional[Skill]:
    skill = db.query(Skill).filter(Skill.id == skill_id, Skill.profile_id == profile.id).first()
    if not skill:
        return None
    for field, value in data.model_dump().items():
        setattr(skill, field, value)
    db.commit()
    db.refresh(skill)
    return skill


def delete_skill(skill_id: int, profile: Profile, db: Session) -> bool:
    skill = db.query(Skill).filter(Skill.id == skill_id, Skill.profile_id == profile.id).first()
    if skill:
        db.delete(skill)
        db.commit()
        return True
    return False


def replace_skills(profile: Profile, skills: list[SkillCreate], db: Session) -> list[Skill]:
    """Delete all existing skills and replace with the provided list. Defensive: no empty/null/dupes."""
    from sqlalchemy.exc import SQLAlchemyError
    import logging
    logger = logging.getLogger(__name__)
    db.query(Skill).filter(Skill.profile_id == profile.id).delete()
    cleaned = []
    seen = set()
    for i, s in enumerate(skills):
        name = s.name.strip()
        category = s.category.strip() if s.category else ""
        key = (name.lower(), category.lower())
        if not name or key in seen:
            continue
        seen.add(key)
        cleaned.append(Skill(profile_id=profile.id, name=name, category=category, display_order=len(cleaned)))
    try:
        db.add_all(cleaned)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Skill save error for profile {profile.id}: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to save skills. Please try again.")
    return cleaned


# ── Projects ──────────────────────────────────────────────────────────────────

def add_project(profile: Profile, data: ProjectCreate, db: Session) -> Project:
    proj = Project(profile_id=profile.id, **data.model_dump())
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


def update_project(proj_id: int, profile: Profile, data: ProjectCreate, db: Session) -> Project:
    proj = db.query(Project).filter(
        Project.id == proj_id, Project.profile_id == profile.id
    ).first()
    if not proj:
        raise ProfileNotFound(f"Project {proj_id} not found")
    for k, v in data.model_dump().items():
        setattr(proj, k, v)
    db.commit()
    db.refresh(proj)
    return proj


def delete_project(proj_id: int, profile: Profile, db: Session) -> None:
    proj = db.query(Project).filter(
        Project.id == proj_id, Project.profile_id == profile.id
    ).first()
    if proj:
        db.delete(proj)
        db.commit()


# ── Certifications ────────────────────────────────────────────────────────────

def add_certification(profile: Profile, data: CertificationCreate, db: Session) -> Certification:
    cert = Certification(profile_id=profile.id, **data.model_dump())
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


def delete_certification(cert_id: int, profile: Profile, db: Session) -> None:
    cert = db.query(Certification).filter(
        Certification.id == cert_id, Certification.profile_id == profile.id
    ).first()
    if cert:
        db.delete(cert)
        db.commit()


# ── Awards ────────────────────────────────────────────────────────────────────

def add_award(profile: Profile, data: AwardCreate, db: Session) -> Award:
    award = Award(profile_id=profile.id, **data.model_dump())
    db.add(award)
    db.commit()
    db.refresh(award)
    return award


def delete_award(award_id: int, profile: Profile, db: Session) -> None:
    award = db.query(Award).filter(
        Award.id == award_id, Award.profile_id == profile.id
    ).first()
    if award:
        db.delete(award)
        db.commit()


# ── Custom Sections ───────────────────────────────────────────────────────────

def add_custom_section(profile: Profile, data: CustomSectionCreate, db: Session) -> CustomSection:
    section = CustomSection(profile_id=profile.id, **data.model_dump())
    db.add(section)
    db.commit()
    db.refresh(section)
    return section


def delete_custom_section(section_id: int, profile: Profile, db: Session) -> None:
    section = db.query(CustomSection).filter(
        CustomSection.id == section_id, CustomSection.profile_id == profile.id
    ).first()
    if section:
        db.delete(section)
        db.commit()
