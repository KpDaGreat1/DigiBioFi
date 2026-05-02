"""Minimal V1 permission helpers for tier-based access checks."""

from app.core.config import settings
from app.core.owner import is_owner_email
from app.models.user import UserRole


def _is_admin(user) -> bool:
    if not user:
        return False
    if getattr(user, "role", "") == UserRole.ADMIN.value:
        return True
    return is_owner_email(getattr(user, "email", None))


def _has_active_paid_access(user) -> bool:
    if not user:
        return False
    if getattr(user, "subscription_status", "") != "active":
        return False
    return getattr(user, "subscription_tier", "") in {"basic", "elite"}


def can_access_analytics(user) -> bool:
    if _is_admin(user):
        return True
    return (
        getattr(user, "subscription_status", "") == "active"
        and getattr(user, "subscription_tier", "") == "elite"
    )


def can_access_elite_features(user) -> bool:
    return can_access_analytics(user)


def can_manage_subscription(user) -> bool:
    if not user or _is_admin(user):
        return False
    return _has_active_paid_access(user) and bool((getattr(user, "stripe_customer_id", "") or "").strip())


def current_plan_label(user) -> str:
    if _is_admin(user):
        return "Admin"
    if getattr(user, "subscription_status", "") != "active":
        return "Free"

    tier = getattr(user, "subscription_tier", "")
    if tier == "elite":
        return "Elite"
    if tier == "basic":
        return "Basic"
    return "Free"


def can_access_portfolio(user) -> bool:
    if _is_admin(user):
        return True
    return _has_active_paid_access(user)


def should_show_ads(user) -> bool:
    if not user or _is_admin(user):
        return False
    return not _has_active_paid_access(user)


def can_view_profile(user, current_count) -> bool:
    if user is None:
        return True
    if _is_admin(user) or _has_active_paid_access(user):
        return True
    return int(current_count or 0) < settings.free_daily_profile_view_limit
