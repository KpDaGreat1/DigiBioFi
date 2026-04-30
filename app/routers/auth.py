import logging
import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.core.config import settings
from app.core.templates import templates, flash
from app.core.dependencies import get_db, get_current_user_optional, require_csrf
from app.core.security import (
    create_access_token,
    generate_csrf_token,
    set_csrf_cookie,
    set_auth_cookie,
    clear_auth_cookie,
    clear_csrf_cookie,
)
from app.schemas.auth import RegisterRequest, LoginRequest, ForgotPasswordRequest, ResetPasswordRequest
from app.models.user import User
from app.services.auth_service import (
    register_user,
    authenticate_user,
    build_email_verification_url,
    build_password_reset_url,
    create_email_verification_token,
    issue_password_reset,
    reset_password,
    verify_email_token,
    AuthError,
)
from app.services import email_service
from app.utils.validators import format_pydantic_errors

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)
_VERIFICATION_RESEND_COOLDOWN_SECONDS = 60


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _dev_verification_url(request: Request, user) -> str | None:
    if settings.is_production or email_service.is_email_configured():
        return None
    token = create_email_verification_token(user)
    return build_email_verification_url(token, _base_url(request))

# ─────────────────────────────────────────────
# REGISTER
# ─────────────────────────────────────────────

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, current_user=Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(
            "/dashboard" if current_user.is_verified else "/verify-email/pending",
            status_code=302,
        )

    token = generate_csrf_token(request)
    response = templates.TemplateResponse(
        "auth/register.html",
        {"request": request, "csrf_token": token}
    )
    set_csrf_cookie(response, token)
    return response


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    company: str = Form(""),
    csrf_token: str = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    try:
        if company.strip():
            raise AuthError("Invalid registration request.")

        if settings.is_production and not email_service.is_email_configured():
            raise AuthError("Registration is temporarily unavailable while email verification is offline.")

        data = RegisterRequest(
            email=email,
            username=username,
            password=password,
            confirm_password=confirm_password,
        )

        user = register_user(data, db)
        verification_url = build_email_verification_url(
            create_email_verification_token(user),
            _base_url(request),
        )

        if email_service.is_email_configured():
            try:
                email_service.send_verification_email(
                    recipient=user.email,
                    username=user.username,
                    verification_url=verification_url,
                )
            except email_service.EmailDeliveryError:
                flash(
                    request,
                    "Account created, but we could not send the verification email yet. Please resend it below.",
                    "info",
                )
        else:
            logger.info("Development verification URL for %s: %s", user.email, verification_url)

        auth_token = create_access_token(subject=user.id, role=user.role)
        redirect = RedirectResponse("/verify-email/pending", status_code=303)
        set_auth_cookie(redirect, auth_token)
        flash(request, "Account created. Verify your email to unlock your account.", "success")
        return redirect

    except ValidationError as e:
        return templates.TemplateResponse(
            "auth/register.html",
            {
                "request": request,
                "errors": format_pydantic_errors(e),
                "email": email,
                "username": username,
                "csrf_token": generate_csrf_token(request),
            },
            status_code=422,
        )

    except AuthError as e:
        return templates.TemplateResponse(
            "auth/register.html",
            {
                "request": request,
                "errors": {"general": str(e)},
                "email": email,
                "username": username,
                "csrf_token": generate_csrf_token(request),
            },
            status_code=400,
        )

    except Exception:
        return templates.TemplateResponse(
            "auth/register.html",
            {
                "request": request,
                "errors": {"general": "Something went wrong. Try again."},
                "email": email,
                "username": username,
                "csrf_token": generate_csrf_token(request),
            },
            status_code=500,
        )


# ─────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    registered: str = "",
    verified: str = "",
    current_user=Depends(get_current_user_optional),
):
    if current_user:
        return RedirectResponse(
            "/dashboard" if current_user.is_verified else "/verify-email/pending",
            status_code=302,
        )

    if verified == "1":
        flash(request, "Email verified. You can sign in now.", "success")

    token = generate_csrf_token(request)
    response = templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "registered": registered == "1",
            "csrf_token": token,
        },
    )
    set_csrf_cookie(response, token)
    return response


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    try:
        data = LoginRequest(email=email, password=password)
        user = authenticate_user(data, db)
        token = create_access_token(subject=user.id, role=user.role)

        if user.is_verified:
            flash(request, "Welcome back!", "success")
            redirect = RedirectResponse("/dashboard", status_code=303)
        else:
            flash(request, "Please verify your email to unlock your account.", "info")
            redirect = RedirectResponse("/verify-email/pending", status_code=303)
        set_auth_cookie(redirect, token)
        return redirect

    except ValidationError as e:
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "errors": format_pydantic_errors(e),
                "email": email,
                "csrf_token": generate_csrf_token(request),
            },
            status_code=422,
        )

    except AuthError as e:
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "errors": {"general": str(e)},
                "email": email,
                "csrf_token": generate_csrf_token(request),
            },
            status_code=401,
        )


# ─────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    response = RedirectResponse("/login", status_code=303)
    clear_auth_cookie(response)
    clear_csrf_cookie(response)
    response.delete_cookie("digibiofi_session", path="/")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request, current_user=Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(
            "/dashboard" if current_user.is_verified else "/verify-email/pending",
            status_code=302,
        )

    token = generate_csrf_token(request)
    response = templates.TemplateResponse(
        "auth/forgot_password.html",
        {"request": request, "csrf_token": token},
    )
    set_csrf_cookie(response, token)
    return response


@router.post("/forgot-password", response_class=HTMLResponse)
def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    csrf_token: str = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    reset_url = None
    dev_reset_url = None  # Only shown in dev mode without email configured

    try:
        data = ForgotPasswordRequest(email=email)
        token = issue_password_reset(data.email, db)
        if token:
            reset_url = build_password_reset_url(token, _base_url(request))
            if email_service.is_email_configured():
                user = db.query(User).filter(User.email.ilike(data.email)).first()
                if user:
                    email_service.send_password_reset_email(
                        recipient=user.email,
                        username=user.username,
                        reset_url=reset_url,
                    )
            elif not settings.is_production:
                logger.info("Password reset URL for %s: %s", data.email, reset_url)
                dev_reset_url = reset_url
    except ValidationError:
        pass
    except email_service.EmailDeliveryError:
        logger.warning("Password reset email delivery failed for %s", email)

    token = generate_csrf_token(request)
    response = templates.TemplateResponse(
        "auth/forgot_password.html",
        {
            "request": request,
            "csrf_token": token,
            "success": True,
            "reset_url": dev_reset_url,
        },
    )
    set_csrf_cookie(response, token)
    return response


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(
    request: Request,
    token: str = "",
    current_user=Depends(get_current_user_optional),
):
    if current_user:
        return RedirectResponse(
            "/dashboard" if current_user.is_verified else "/verify-email/pending",
            status_code=302,
        )

    csrf_token = generate_csrf_token(request)
    response = templates.TemplateResponse(
        "auth/reset_password.html",
        {
            "request": request,
            "token": token,
            "csrf_token": csrf_token,
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/reset-password", response_class=HTMLResponse)
def reset_password_submit(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    try:
        data = ResetPasswordRequest(
            token=token,
            new_password=new_password,
            confirm_password=confirm_password,
        )
        reset_password(data, db)
        flash(request, "Password updated. You can sign in now.", "success")
        return RedirectResponse("/login", status_code=303)
    except ValidationError as e:
        csrf_token = generate_csrf_token(request)
        response = templates.TemplateResponse(
            "auth/reset_password.html",
            {
                "request": request,
                "token": token,
                "csrf_token": csrf_token,
                "errors": format_pydantic_errors(e),
            },
            status_code=422,
        )
        set_csrf_cookie(response, csrf_token)
        return response
    except AuthError as e:
        csrf_token = generate_csrf_token(request)
        response = templates.TemplateResponse(
            "auth/reset_password.html",
            {
                "request": request,
                "token": token,
                "csrf_token": csrf_token,
                "errors": {"general": str(e)},
            },
            status_code=400,
        )
        set_csrf_cookie(response, csrf_token)
        return response


@router.get("/verify-email/pending", response_class=HTMLResponse)
def verify_email_pending(
    request: Request,
    current_user=Depends(get_current_user_optional),
):
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    if current_user.is_verified:
        return RedirectResponse("/dashboard", status_code=302)

    csrf_token = generate_csrf_token(request)
    response = templates.TemplateResponse(
        "auth/verify_email_pending.html",
        {
            "request": request,
            "user": current_user,
            "csrf_token": csrf_token,
            "email_delivery_configured": email_service.is_email_configured(),
            "verification_url": _dev_verification_url(request, current_user),
        },
    )
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/verify-email/resend")
def resend_verification_email(
    request: Request,
    csrf_token: str = Depends(require_csrf),
    current_user=Depends(get_current_user_optional),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    if current_user.is_verified:
        flash(request, "Your email is already verified.", "info")
        return RedirectResponse("/dashboard", status_code=303)

    last_sent_at = int(request.session.get("verification_email_last_sent_at", 0) or 0)
    now = int(time.time())
    if last_sent_at and now - last_sent_at < _VERIFICATION_RESEND_COOLDOWN_SECONDS:
        flash(request, "Please wait a minute before requesting another verification email.", "info")
        return RedirectResponse("/verify-email/pending", status_code=303)

    verification_url = build_email_verification_url(
        create_email_verification_token(current_user),
        _base_url(request),
    )

    if settings.is_production and not email_service.is_email_configured():
        flash(request, "Verification email delivery is currently unavailable.", "error")
        return RedirectResponse("/verify-email/pending", status_code=303)

    if email_service.is_email_configured():
        try:
            email_service.send_verification_email(
                recipient=current_user.email,
                username=current_user.username,
                verification_url=verification_url,
            )
        except email_service.EmailDeliveryError:
            flash(request, "We could not resend the verification email. Please try again.", "error")
            return RedirectResponse("/verify-email/pending", status_code=303)
        flash(request, "Verification email sent.", "success")
    else:
        logger.info("Development verification URL for %s: %s", current_user.email, verification_url)
        flash(request, "Development verification link refreshed below.", "info")

    request.session["verification_email_last_sent_at"] = now
    return RedirectResponse("/verify-email/pending", status_code=303)


@router.get("/verify-email")
def verify_email(
    request: Request,
    token: str = "",
    db: Session = Depends(get_db),
):
    if not token:
        flash(request, "Verification link is missing.", "error")
        return RedirectResponse("/login", status_code=303)

    try:
        verify_email_token(token, db)
        response = RedirectResponse("/login?verified=1", status_code=303)
        clear_auth_cookie(response)
        clear_csrf_cookie(response)
        response.delete_cookie("digibiofi_session", path="/")
        return response
    except AuthError as exc:
        flash(request, str(exc), "error")
        return RedirectResponse("/login", status_code=303)
