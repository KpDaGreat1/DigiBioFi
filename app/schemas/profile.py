"""
Pydantic schemas for Profile and all sub-section models.
"""
from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional


# ── Sub-section schemas ───────────────────────────────────────────────────────

class ExperienceCreate(BaseModel):
    company: str = Field(..., min_length=1, max_length=200)
    title: str = Field(..., min_length=1, max_length=200)
    location: str = Field(default="", max_length=200)
    start_date: str = Field(default="", max_length=50)
    end_date: str = Field(default="", max_length=50)
    is_current: bool = False
    description: str = Field(default="", max_length=1000)
    display_order: int = 0


class ExperienceRead(ExperienceCreate):
    id: int
    profile_id: int
    model_config = {"from_attributes": True}


class EducationCreate(BaseModel):
    school: str = Field(..., min_length=1, max_length=200)
    degree: str = Field(default="", max_length=200)
    field: str = Field(default="", max_length=200)
    start_date: str = Field(default="", max_length=50)
    end_date: str = Field(default="", max_length=50)
    description: str = Field(default="", max_length=1000)
    certificate_url: str = Field(default="", max_length=500)
    display_order: int = 0


class EducationRead(EducationCreate):
    id: int
    profile_id: int
    model_config = {"from_attributes": True}


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: str = Field(default="", max_length=100)
    display_order: int = 0


class SkillRead(SkillCreate):
    id: int
    profile_id: int
    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    url: str = Field(default="", max_length=500)
    thumbnail_url: str = Field(default="", max_length=500)
    display_order: int = 0


class ProjectRead(ProjectCreate):
    id: int
    profile_id: int
    model_config = {"from_attributes": True}


class CertificationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    issuer: str = Field(default="", max_length=200)
    date: str = Field(default="", max_length=50)
    credential_id: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=500)
    display_order: int = 0


class CertificationRead(CertificationCreate):
    id: int
    profile_id: int
    model_config = {"from_attributes": True}


class AwardCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    issuer: str = Field(default="", max_length=200)
    date: str = Field(default="", max_length=50)
    description: str = Field(default="", max_length=3000)
    display_order: int = 0


class AwardRead(AwardCreate):
    id: int
    profile_id: int
    model_config = {"from_attributes": True}


class CustomSectionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(default="", max_length=5000)
    display_order: int = 0


class CustomSectionRead(CustomSectionCreate):
    id: int
    profile_id: int
    model_config = {"from_attributes": True}


# ── Profile schemas ───────────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    """Fields the user can update via the dashboard form."""
    full_name: Optional[str] = Field(default=None, max_length=200)
    headline: Optional[str] = Field(default=None, max_length=200)
    bio: Optional[str] = Field(default=None, max_length=1000)
    email: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=20)
    location: Optional[str] = Field(default=None, max_length=200)
    website: Optional[str] = Field(default=None, max_length=500)
    twitter: Optional[str] = Field(default=None, max_length=500)
    github: Optional[str] = Field(default=None, max_length=500)
    telegram: Optional[str] = Field(default=None, max_length=500)
    is_public: Optional[bool] = None
    recruiter_visibility: Optional[bool] = None
    freelance_availability: Optional[bool] = None
    slug: Optional[str] = None
    profile_image: Optional[str] = None
    resume_pdf: Optional[str] = None
    # Elite customization fields
    profile_image_2: Optional[str] = None
    profile_image_3: Optional[str] = None
    custom_background_url: Optional[str] = None
    custom_header_url: Optional[str] = None

    @field_validator("slug")
    @classmethod
    def slug_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re
        v = v.strip().lower()
        if not re.match(r"^[a-z0-9-]{3,50}$", v):
            raise ValueError("Slug must be 3–50 chars, lowercase letters, numbers, and hyphens only")
        return v


class ProfileRead(BaseModel):
    id: int
    user_id: int
    slug: str
    full_name: str
    headline: str
    bio: str
    email: str
    phone: str
    location: str
    website: str
    twitter: str
    github: str
    telegram: str
    profile_image: str
    resume_pdf: str
    is_public: bool
    experiences: list[ExperienceRead] = []
    educations: list[EducationRead] = []
    skills: list[SkillRead] = []
    projects: list[ProjectRead] = []
    certifications: list[CertificationRead] = []
    awards: list[AwardRead] = []
    custom_sections: list[CustomSectionRead] = []

    model_config = {"from_attributes": True}
