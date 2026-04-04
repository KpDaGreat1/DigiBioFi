import stripe
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/create-checkout-session")
def create_checkout_session(
    plan: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    stripe.api_key = settings.stripe_secret_key

    if plan == "elite":
        price_id = settings.stripe_price_elite
    elif plan == "basic":
        price_id = settings.stripe_price_basic
    else:
        raise HTTPException(status_code=400, detail="Invalid plan")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price": price_id,
            "quantity": 1,
        }],
        mode="subscription",
        success_url="https://digibiofi.com/dashboard?success=true",
        cancel_url="https://digibiofi.com/dashboard?canceled=true",
    )

    return RedirectResponse(session.url, status_code=303)
