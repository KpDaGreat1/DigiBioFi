"""
Security utilities — password hashing, JWT creation/verification,
and cookie helpers.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib
import hmac
import secrets

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Response, Request, HTTPException

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

AUTH_COOKIE_NAME = "access_token"
CSRF_COOKIE_NAME = "csrf_token"


# ── Passwords ─────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(_bcrypt_safe_password(plain))


def verify_password(plain: str, hashed: str) -> bool:
    normalized = _bcrypt_safe_password(plain)
    if normalized != plain:
        return pwd_context.verify(normalized, hashed)
    return pwd_context.verify(plain, hashed)


def _bcrypt_safe_password(plain: str) -> str:
    raw = plain.encode("utf-8")
    if len(raw) <= 72:
        return plain
    digest = hashlib.sha256(raw).hexdigest()
    return f"sha256:{digest}"


# ── JWT ───────────────────────────────────────────────────

def create_access_token(
    subject: str | int,
    role: str = "user",
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )

    payload = {
        "sub": str(subject),
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None


# ── Auth Cookies ─────────────────────────────────────────

def set_auth_cookie(response: Response, token: str):
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.use_secure_cookies,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


def clear_auth_cookie(response: Response):
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")


def clear_csrf_cookie(response: Response):
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")


# ── CSRF ────────────────────────────────────────────────

def generate_csrf_token(request: Request) -> str:
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if token:
        return token

    token = getattr(request.state, "csrf_token", None)
    if not token:
        token = secrets.token_urlsafe(32)
        request.state.csrf_token = token
    return token


def set_csrf_cookie(response: Response, token: str):
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,  # IMPORTANT
        secure=settings.use_secure_cookies,
        samesite="lax",
        max_age=60 * 60 * 8,
        path="/",
    )


def validate_csrf(request: Request, form_token: str):
    # Skip CSRF validation in testing
    if request.app.state.environment == "testing":
        return
    
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)

    if not cookie_token:
        raise HTTPException(status_code=403, detail="Session expired")

    # Use constant-time comparison to prevent timing attacks
    if not form_token or not hmac.compare_digest(form_token, cookie_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
