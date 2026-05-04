"""Schemas for staged AI resume extraction."""

from pydantic import BaseModel, Field, field_validator

from app.utils.validators import normalize_optional_external_url


class ResumeExperience(BaseModel):
    title: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=200)
    start_date: str = Field(default="", max_length=50)
    end_date: str = Field(default="", max_length=50)
    description: str = Field(default="", max_length=1000)


class ResumeEducation(BaseModel):
    school: str = Field(default="", max_length=200)
    degree: str = Field(default="", max_length=200)
    field: str = Field(default="", max_length=200)
    start_date: str = Field(default="", max_length=50)
    end_date: str = Field(default="", max_length=50)
    description: str = Field(default="", max_length=1000)


class ResumeProject(BaseModel):
    name: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=1000)
    url: str = Field(default="", max_length=500)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_optional_external_url(value) or ""


class ResumeInfo(BaseModel):
    full_name: str = Field(default="", max_length=200)
    headline: str = Field(default="", max_length=200)
    bio: str = Field(default="", max_length=1000)
    location: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=50)
    skills: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    experience: list[ResumeExperience] = Field(default_factory=list)
    education: list[ResumeEducation] = Field(default_factory=list)
    projects: list[ResumeProject] = Field(default_factory=list)

    @field_validator("skills", mode="before")
    @classmethod
    def coerce_skills(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("links", mode="before")
    @classmethod
    def coerce_links(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return [normalize_optional_external_url(item) or "" for item in value]

    @field_validator("skills")
    @classmethod
    def normalize_skills(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            cleaned = (item or "").strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(cleaned[:100])
        return normalized[:20]

    @field_validator("links")
    @classmethod
    def normalize_links(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            cleaned = (item or "").strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(cleaned[:500])
        return normalized[:10]
