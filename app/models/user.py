"""
User model — authentication identity and role.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.profile import Profile


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    address: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    # Role: "user" | "admin"
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)

    # Subscription tier: "free" | "basic" | "elite"
    subscription_tier: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    subscription_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_profile_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_view_reset: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resume_ai_requests_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resume_ai_last_request_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Stripe customer identifier (set on first checkout)
    stripe_customer_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    stripe_subscription_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")


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

    # One-to-one relationship with Profile
    profile: Mapped[Profile] = relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"
