"""
Import all models here so that Alembic autogenerate can discover them.
"""
from app.models.user import User          # noqa: F401
from app.models.profile import (         # noqa: F401
    Profile,
    Experience,
    Education,
    Skill,
    Project,
    Certification,
    Award,
    CustomSection,
    QRCode,
    ProfileView,
)
from app.models.analytics import AnalyticsEvent  # noqa: F401
from app.models.stripe import StripeEvent  # noqa: F401
