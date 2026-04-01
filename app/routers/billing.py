"""
Billing routes — Stripe checkout success, cancel, and portal flows.

The checkout session itself is created in dashboard.py (/dashboard/subscribe)
because it needs session-level user context. These routes handle the post-checkout
landing pages and the billing portal redirect.
"""
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user, get_db
from app.core.templates import flash, templates
from app.models.user import User

router = APIRouter(prefix="/billing", tags=["billing"])
logger = logging.getLogger(__name__)


@router.get("/success", response_class=HTMLResponse)
def billing_success(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Landing page after a successful Stripe checkout redirect.
    Subscription state is authoritative from the webhook; this page just
    confirms the redirect and shows current tier.
    """
    db.refresh(current_user)
    return templates.TemplateResponse(
        "billing/success.html",
        {"request": request, "user": current_user},
    )


@router.get("/cancel", response_class=HTMLResponse)
def billing_cancel(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """User abandoned the Stripe checkout — no charge was made."""
    return templates.TemplateResponse(
        "billing/cancel.html",
        {"request": request, "user": current_user},
    )


@router.get("/portal")
def billing_portal(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Launch the Stripe Customer Portal for existing subscribers.
    Allows them to update payment method, cancel, or view invoices.
    """
    if not current_user.stripe_customer_id:
        flash(request, "No active subscription found.", "error")
        return RedirectResponse("/dashboard/upgrade", status_code=303)

    if not settings.stripe_secret_key:
        flash(request, "Billing is not configured yet.", "error")
        return RedirectResponse("/dashboard", status_code=303)

    try:
        import stripe  # noqa: PLC0415

        stripe.api_key = settings.stripe_secret_key
        portal_session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=str(request.base_url).rstrip("/") + "/dashboard",
        )
        return RedirectResponse(portal_session.url, status_code=303)
    except Exception as e:
        logger.error(f"Stripe portal error for user {current_user.id}: {e}")
        flash(request, "Could not open billing portal. Please try again.", "error")
        return RedirectResponse("/dashboard", status_code=303)
