"""
Stripe helper functions — used by dashboard.py subscribe route and webhook.

Note: The checkout session creation is handled inline in dashboard.py to keep
user session context. These helpers are provided for testability and reuse.
"""
import logging

logger = logging.getLogger(__name__)


def create_checkout_session(user_id: int, plan: str, customer_id: str | None, base_url: str) -> str:
    """
    Create a Stripe checkout session for the given plan and return the session URL.

    plan must be 'basic', 'premium', or 'elite'.
    """
    import stripe
    from app.core.config import settings

    stripe.api_key = settings.stripe_secret_key
    price_id = settings.get_stripe_price(plan)

    session = stripe.checkout.Session.create(
        customer=customer_id or None,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{base_url.rstrip('/')}/billing/success",
        cancel_url=f"{base_url.rstrip('/')}/billing/cancel",
        metadata={"user_id": str(user_id), "plan": plan},
    )
    return session.url


def get_or_create_customer(email: str, existing_customer_id: str | None) -> str:
    """Return existing Stripe customer ID or create a new one."""
    import stripe
    from app.core.config import settings

    stripe.api_key = settings.stripe_secret_key

    if existing_customer_id:
        return existing_customer_id

    customer = stripe.Customer.create(email=email)
    return customer.id
