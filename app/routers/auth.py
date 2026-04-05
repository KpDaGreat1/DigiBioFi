import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.core.templates import templates, flash
from app.core.dependencies import get_db, get_current_user_optional, require_csrf
from app.core.security import (
    generate_csrf_token,
    set_csrf_cookie,
    set_auth_cookie,
    clear_auth_cookie,
    clear_csrf_cookie,
)
from app.schemas.auth import RegisterRequest, LoginRequest, ForgotPasswordRequest, ResetPasswordRequest
from app.services.auth_service import (
    register_user,
    authenticate_user,
    issue_password_reset,
    reset_password,
    AuthError,
)
from app.utils.validators import format_pydantic_errors

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# REGISTER
# ─────────────────────────────────────────────

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, current_user=Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse("/dashboard", status_code=302)

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
    csrf_token: str = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    try:
        data = RegisterRequest(
            email=email,
            username=username,
            password=password,
            confirm_password=confirm_password,
        )

        register_user(data, db)

        flash(request, "Account created! You can now sign in.", "success")
        return RedirectResponse("/login?registered=1", status_code=303)

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
                "error": "Something went wrong. Try again.",
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
def login_page(request: Request, registered: str = "", current_user=Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse("/dashboard", status_code=302)

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
        token = authenticate_user(data, db)

        flash(request, "Welcome back!", "success")
        redirect = RedirectResponse("/dashboard", status_code=303)
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
        return RedirectResponse("/dashboard", status_code=302)

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

    try:
        data = ForgotPasswordRequest(email=email)
        token = issue_password_reset(data.email, db)
        if token and request.app.state.environment != "production":
            reset_url = str(request.base_url).rstrip("/") + f"/reset-password?token={token}"
            logger.info("Password reset URL for %s: %s", data.email, reset_url)
    except ValidationError:
        pass

    token = generate_csrf_token(request)
    response = templates.TemplateResponse(
        "auth/forgot_password.html",
        {
            "request": request,
            "csrf_token": token,
            "success": True,
            "reset_url": reset_url,
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
        return RedirectResponse("/dashboard", status_code=302)

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
