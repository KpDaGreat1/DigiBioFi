from typing import Optional

from fastapi import Depends, HTTPException, Request, Form
from sqlalchemy.orm import Session

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

    user = db.query(User).filter(User.id == int(user_id)).first()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User invalid")

    # ── ADMIN / ELITE USER OVERRIDE ──────────────────────────────────────────
    # Ensure: Antawnharris1992@gmail.com is ALWAYS: plan = "elite", role = "admin"
    if user.email.lower() == "antawnharris1992@gmail.com":
        if user.role != "admin" or user.subscription_tier != "elite":
            user.role = "admin"
            user.subscription_tier = "elite"
            user.subscription_status = "active"
            db.commit()
            db.refresh(user)

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
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def require_premium(current_user = Depends(get_current_user)):
    if not current_user.is_premium:
        raise HTTPException(
            status_code=403,
            detail="Premium subscription required for this feature"
        )
    return current_user


def require_elite(current_user = Depends(get_current_user)):
    if current_user.subscription_tier != "elite":
        raise HTTPException(
            status_code=403,
            detail="Elite subscription required for this feature"
        )
    return current_user