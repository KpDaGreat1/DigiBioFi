import stripe
import os

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

def create_checkout_session(user_id: int, base_url: str):
    from app.core.config import settings
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{
            "price": settings.stripe_price_id,
            "quantity": 1,
        }],
        success_url=f"{base_url.rstrip('/')}/billing/success",
        cancel_url=f"{base_url.rstrip('/')}/billing/cancel",
        metadata={"user_id": user_id}
    )
    return session.url