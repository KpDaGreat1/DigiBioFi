"""Billing routes — authoritative checkout, portal, and compatibility redirects."""
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.dependencies import get_current_user, require_csrf
from app.core.owner import is_owner_email
from app.core.templates import flash
from app.models.user import User, SubscriptionTier
from app.services import stripe_service

router = APIRouter(prefix="/billing", tags=["billing"])
logger = logging.getLogger(__name__)
_ALLOWED_PLANS = {SubscriptionTier.BASIC.value, SubscriptionTier.ELITE.value}


def _normalize_plan(plan: str | None) -> str:
    return (plan or "").lower().strip()


def _redirect_with_flash(request: Request, location: str, message: str, category: str = "error"):
    flash(request, message, category)
    return RedirectResponse(location, status_code=303)

@router.post("/create-checkout-session")
def create_checkout_session(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    plan: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    plan = _normalize_plan(plan)

    if is_owner_email(current_user.email):
        return _redirect_with_flash(
            request,
            "/dashboard",
            "Billing is disabled for the owner account.",
            "info",
        )

    if plan not in _ALLOWED_PLANS:
        logger.warning(
            "Invalid checkout plan attempt plan=%r user_id=%s email=%s",
            plan,
            current_user.id,
            current_user.email,
        )
        return _redirect_with_flash(
            request,
            "/dashboard/upgrade",
            "Selected plan is invalid.",
        )

    if not settings.stripe_secret_key:
        logger.error(
            "Stripe checkout blocked: missing STRIPE_SECRET_KEY for user_id=%s email=%s plan=%s",
            current_user.id,
            current_user.email,
            plan,
        )
        return _redirect_with_flash(
            request,
            "/dashboard/upgrade",
            "Billing is not configured yet.",
        )

    price_id = settings.get_stripe_price(plan)
    if not price_id:
        logger.error(
            "Stripe checkout blocked: missing price configuration for user_id=%s email=%s plan=%s",
            current_user.id,
            current_user.email,
            plan,
        )
        return _redirect_with_flash(
            request,
            "/dashboard/upgrade",
            "This plan is not available right now.",
        )

    base_url = str(request.base_url).rstrip("/")
    success_url = f"{base_url}/dashboard?success=true&plan={plan}"
    cancel_url = f"{base_url}/dashboard?canceled=true&plan={plan}"

    try:
        customer_id = stripe_service.get_or_create_customer(
            current_user.email,
            current_user.stripe_customer_id or None,
        )
        checkout_url = stripe_service.create_checkout_session(
            user_id=current_user.id,
            plan=plan,
            customer_id=customer_id,
            base_url=base_url,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return RedirectResponse(checkout_url, status_code=303)
    except Exception:
        logger.exception(
            "Stripe checkout failed for user_id=%s email=%s plan=%s",
            current_user.id,
            current_user.email,
            plan,
        )
        return _redirect_with_flash(
            request,
            "/dashboard/upgrade",
            "Could not start checkout. Please try again.",
        )


@router.get("/success")
def billing_success(
    current_user: User = Depends(get_current_user),
    plan: str | None = None,
):
    normalized_plan = _normalize_plan(plan)
    location = "/dashboard?success=true"
    if normalized_plan in _ALLOWED_PLANS:
        location += f"&plan={normalized_plan}"
    return RedirectResponse(location, status_code=303)


@router.get("/cancel")
def billing_cancel(
    current_user: User = Depends(get_current_user),
    plan: str | None = None,
):
    normalized_plan = _normalize_plan(plan)
    location = "/dashboard?canceled=true"
    if normalized_plan in _ALLOWED_PLANS:
        location += f"&plan={normalized_plan}"
    return RedirectResponse(location, status_code=303)


@router.get("/portal")
def billing_portal(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Launch the Stripe Customer Portal for existing subscribers.
    Allows them to update payment method, cancel, or view invoices.
    """
    if is_owner_email(current_user.email):
        flash(request, "Billing is not required for the owner account.", "info")
        return RedirectResponse("/dashboard", status_code=303)

    if not current_user.stripe_customer_id:
        flash(request, "No active subscription found.", "error")
        return RedirectResponse("/dashboard/upgrade", status_code=303)

    if not settings.stripe_secret_key:
        logger.error(
            "Stripe portal blocked: missing STRIPE_SECRET_KEY for user_id=%s email=%s",
            current_user.id,
            current_user.email,
        )
        flash(request, "Billing is not configured yet.", "error")
        return RedirectResponse("/dashboard", status_code=303)

    try:
        portal_url = stripe_service.create_billing_portal_session(
            current_user.stripe_customer_id,
            str(request.base_url).rstrip("/") + "/dashboard",
        )
        return RedirectResponse(portal_url, status_code=303)
    except Exception:
        logger.exception(
            "Stripe portal error for user_id=%s email=%s",
            current_user.id,
            current_user.email,
        )
        flash(request, "Could not open billing portal. Please try again.", "error")
        return RedirectResponse("/dashboard", status_code=303)
