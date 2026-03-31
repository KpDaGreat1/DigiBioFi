"""
FastAPI dependency injection helpers.

- get_db        → yields a SQLAlchemy Session
- get_current_user → reads JWT from cookie, returns User or raises 401
- require_admin    → like above, but also requires admin role
"""
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import AUTH_COOKIE_NAME, decode_access_token
from app.db.database import SessionLocal


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    """Yield a database session and close it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Auth ──────────────────────────────────────────────────────────────────────

def _token_from_request(request: Request) -> Optional[str]:
    """Extract JWT from cookie or Authorization header (Bearer)."""
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return token


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return the authenticated User model instance, or raise HTTP 401."""
    from app.models.user import User  # local import avoids circular deps

    token = _token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id: str = payload.get("sub")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
):
    """Like get_current_user but returns None instead of raising on failure."""
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None


def require_admin(current_user=Depends(get_current_user)):
    """Raise 403 if the authenticated user is not an admin."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
