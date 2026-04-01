"""
Profile and all sub-section models.

One Profile belongs to one User (1:1).
All section tables (Experience, Education, etc.) belong to a Profile (1:N).
"""
from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UUID, desc
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Public URL identifier — unique, lowercase, URL-safe
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)

    # ── Core fields ───────────────────────────────────────────────────────────
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    headline: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    bio: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Contact
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    location: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    # Social / web
    website: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    twitter: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    github: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    telegram: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    # Uploaded assets (stored as relative paths)
    profile_image: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    resume_pdf: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    # Visibility
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recruiter_visibility: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    freelance_availability: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Elite Customization
    profile_image_2: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    profile_image_3: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    custom_background_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    custom_header_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="profile")  # type: ignore

    experiences: Mapped[list["Experience"]] = relationship(
        "Experience", back_populates="profile", cascade="all, delete-orphan",
        order_by="desc(Experience.is_current), desc(Experience.start_date)",
    )
    educations: Mapped[list["Education"]] = relationship(
        "Education", back_populates="profile", cascade="all, delete-orphan",
        order_by="Education.display_order",
    )
    skills: Mapped[list["Skill"]] = relationship(
        "Skill", back_populates="profile", cascade="all, delete-orphan",
        order_by="Skill.display_order",
    )
    projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="profile", cascade="all, delete-orphan",
        order_by="Project.display_order",
    )
    certifications: Mapped[list["Certification"]] = relationship(
        "Certification", back_populates="profile", cascade="all, delete-orphan",
        order_by="Certification.display_order",
    )
    awards: Mapped[list["Award"]] = relationship(
        "Award", back_populates="profile", cascade="all, delete-orphan",
        order_by="Award.display_order",
    )
    custom_sections: Mapped[list["CustomSection"]] = relationship(
        "CustomSection", back_populates="profile", cascade="all, delete-orphan",
        order_by="CustomSection.display_order",
    )
    qr_code: Mapped["QRCode"] = relationship(
        "QRCode", back_populates="profile", uselist=False, cascade="all, delete-orphan"
    )
    analytics_events: Mapped[list["AnalyticsEvent"]] = relationship(  # type: ignore
        "AnalyticsEvent", back_populates="profile", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Profile slug={self.slug!r} user_id={self.user_id}>"


class Experience(Base):
    __tablename__ = "experiences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    start_date: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    end_date: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="experiences")


class Education(Base):
    __tablename__ = "educations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    school: Mapped[str] = mapped_column(String(200), nullable=False)
    degree: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    field: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    start_date: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    end_date: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    certificate_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="educations")


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="skills")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="projects")


class Certification(Base):
    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    date: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    credential_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="certifications")


class Award(Base):
    __tablename__ = "awards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    date: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="awards")


class CustomSection(Base):
    __tablename__ = "custom_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="custom_sections")


class QRCode(Base):
    __tablename__ = "qr_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    qr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=uuid.uuid4, unique=True, index=True, nullable=False
    )
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    qr_url: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    profile: Mapped["Profile"] = relationship("Profile", back_populates="qr_code")


class ProfileView(Base):
    """Tracks unique profile views per IP/device per 24h to prevent refresh abuse."""
    __tablename__ = "profile_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    visitor_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
