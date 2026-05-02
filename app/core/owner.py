from app.core.config import settings
from app.models.user import UserRole


def is_owner_email(email: str | None) -> bool:
    if not email:
        return False
    return email.strip().lower() == settings.admin_email.strip().lower()


def apply_owner_access(user) -> bool:
    changed = False

    if user.role != UserRole.ADMIN.value:
        user.role = UserRole.ADMIN.value
        changed = True
    if user.subscription_tier != "elite":
        user.subscription_tier = "elite"
        changed = True
    if user.subscription_status != "active":
        user.subscription_status = "active"
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True

    if not user.is_verified:
        user.is_verified = True
        changed = True

    if user.stripe_customer_id:
        user.stripe_customer_id = ""
        changed = True
    if user.stripe_subscription_id:
        user.stripe_subscription_id = ""
        changed = True

    return changed
