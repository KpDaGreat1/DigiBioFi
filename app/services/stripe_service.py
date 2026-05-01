"""Thin Stripe SDK wrappers used by billing routes and webhook flows."""


def create_checkout_session(
    user_id: int,
    plan: str,
    customer_id: str | None,
    base_url: str,
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> str:
    import stripe
    from app.core.config import settings

    stripe.api_key = settings.stripe_secret_key
    stripe.api_version = settings.stripe_api_version
    price_id = settings.get_stripe_price(plan)

    session = stripe.checkout.Session.create(
        customer=customer_id or None,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url or f"{base_url.rstrip('/')}/billing/success",
        cancel_url=cancel_url or f"{base_url.rstrip('/')}/billing/cancel",
        metadata={"user_id": str(user_id), "plan": plan},
    )
    return session.url


def get_or_create_customer(email: str, existing_customer_id: str | None) -> str:
    """Return existing Stripe customer ID or create a new one."""
    import stripe
    from app.core.config import settings

    stripe.api_key = settings.stripe_secret_key
    stripe.api_version = settings.stripe_api_version

    if existing_customer_id:
        return existing_customer_id

    customer = stripe.Customer.create(email=email)
    return customer.id


def create_billing_portal_session(customer_id: str, return_url: str) -> str:
    """Create a Stripe billing portal session and return its URL."""
    import stripe
    from app.core.config import settings

    stripe.api_key = settings.stripe_secret_key
    stripe.api_version = settings.stripe_api_version
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url
