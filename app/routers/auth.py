from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import ValidationError
import secrets

from app.core.config import settings
from app.core.templates import templates, flash
from app.core.dependencies import get_db, get_current_user_optional, require_csrf
from app.core.security import (
    AUTH_COOKIE_NAME,
    generate_csrf_token,
    set_csrf_cookie,
    set_auth_cookie,
    clear_auth_cookie,
    clear_csrf_cookie,
    validate_csrf,
)
from app.schemas.auth import RegisterRequest, LoginRequest
from app.services.auth_service import register_user, authenticate_user, AuthError
from app.utils.validators import format_pydantic_errors

router = APIRouter(tags=["auth"])

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
    response = RedirectResponse("/login", status_code=303)
    clear_auth_cookie(response)
    clear_csrf_cookie(response)
    flash(request, "You have been logged out.", "info")
    return response