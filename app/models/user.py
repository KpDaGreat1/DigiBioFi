"""
User model — authentication identity and role.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"
    ELITE = "elite"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER, nullable=False)

    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        Enum(SubscriptionTier), default=SubscriptionTier.FREE, nullable=False
    )
    subscription_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_profile_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_view_reset: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Stripe customer identifier (set on first checkout)
    stripe_customer_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    stripe_subscription_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    @property
    def is_premium(self) -> bool:
        return self.subscription_tier in (
            SubscriptionTier.BASIC,
            SubscriptionTier.PREMIUM,
            SubscriptionTier.ELITE,
        )

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
    profile: Mapped["Profile"] = relationship(  # type: ignore[name-defined]
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"
