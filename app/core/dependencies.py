from typing import Optional

from fastapi import Depends, HTTPException, Request, Form
from sqlalchemy.orm import Session

from app.core.owner import apply_owner_access, is_owner_email
from app.core.permissions import can_access_elite_features, can_access_portfolio
from app.core.security import AUTH_COOKIE_NAME, decode_access_token, validate_csrf
from app.db.database import SessionLocal  # adjust if your path differs


# ───────────────────────────────
# CSRF PROTECTION
# ───────────────────────────────
async def require_csrf(request: Request, csrf_token: str = Form(...)):
    """
    Dependency to enforce CSRF validation on POST requests.
    Expects 'csrf_token' in the form data.
    """
    validate_csrf(request, csrf_token)
    return csrf_token


# ───────────────────────────────
# DB SESSION
# ───────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ───────────────────────────────
# TOKEN EXTRACTION
# ───────────────────────────────
def _get_token(request: Request) -> Optional[str]:
    return request.cookies.get(AUTH_COOKIE_NAME)


# ───────────────────────────────
# CURRENT USER
# ───────────────────────────────
def get_current_user(request: Request, db: Session = Depends(get_db)):
    from app.models.user import User  # avoid circular import

    token = _get_token(request)

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=401, detail="User invalid")

    if is_owner_email(user.email) and apply_owner_access(user):
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=401, detail="User invalid")

    return user


# ───────────────────────────────
# OPTIONAL USER
# ───────────────────────────────
def get_current_user_optional(request: Request, db: Session = Depends(get_db)):
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None


# ───────────────────────────────
# ADMIN GUARD (THIS FIXES YOUR CRASH)
# ───────────────────────────────
def require_admin(current_user = Depends(get_current_user)):
    from app.models.user import UserRole
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def require_premium(current_user = Depends(get_current_user)):
    from app.models.user import UserRole
    if current_user.role == UserRole.ADMIN:
        return current_user
    if not can_access_portfolio(current_user):
        raise HTTPException(
            status_code=403,
            detail="Premium subscription required for this feature"
        )
    return current_user


def require_elite(current_user = Depends(get_current_user)):
    from app.models.user import UserRole
    if current_user.role == UserRole.ADMIN:
        return current_user
    if not can_access_elite_features(current_user):
        raise HTTPException(
            status_code=403,
            detail="Elite subscription required for this feature"
        )
    return current_user
