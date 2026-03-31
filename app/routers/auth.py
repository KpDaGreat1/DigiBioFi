"""
Authentication routes — register, login, logout.

All routes render HTML responses (Jinja2 templates) for the web UI.
A companion API endpoint at /api/v1/auth/* provides JSON responses
for programmatic access.
"""
from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.templates import templates
from app.core.dependencies import get_db, get_current_user_optional
from app.core.security import AUTH_COOKIE_NAME
from app.schemas.auth import RegisterRequest, LoginRequest
from app.services.auth_service import register_user, authenticate_user, AuthError

router = APIRouter(tags=["auth"])

_COOKIE_OPTS = dict(
    httponly=True,
    samesite="lax",
    secure=settings.is_production,
    max_age=3600,
)


# ── Register ──────────────────────────────────────────────────────────────────

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, current_user=Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("auth/register.html", {"request": request})


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    error = None
    try:
        data = RegisterRequest(
            email=email,
            username=username,
            password=password,
            confirm_password=confirm_password,
        )
        register_user(data, db)
        return RedirectResponse("/login?registered=1", status_code=303)
    except AuthError as e:
        error = str(e)
    except Exception as e:
        # Pydantic validation errors come through here
        error = str(e)

    return templates.TemplateResponse(
        "auth/register.html",
        {"request": request, "error": error, "email": email, "username": username},
        status_code=400,
    )


# ── Login ─────────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, registered: str = "", current_user=Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "registered": registered == "1"},
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        data = LoginRequest(email=email, password=password)
        token = authenticate_user(data, db)
    except AuthError as e:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": str(e), "email": email},
            status_code=401,
        )

    redirect = RedirectResponse("/dashboard", status_code=303)
    redirect.set_cookie(AUTH_COOKIE_NAME, token, **_COOKIE_OPTS)
    return redirect


# ── Logout ────────────────────────────────────────────────────────────────────

@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(AUTH_COOKIE_NAME)
    return resp


# ── Forgot password (scaffold) ────────────────────────────────────────────────

@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    return templates.TemplateResponse("auth/forgot_password.html", {"request": request})


@router.post("/forgot-password", response_class=HTMLResponse)
def forgot_password_submit(request: Request, email: str = Form(...)):
    # Scaffold: log the request, return success message regardless (prevents enumeration)
    # TODO: generate reset token, send email
    return templates.TemplateResponse(
        "auth/forgot_password.html",
        {"request": request, "success": True},
    )
