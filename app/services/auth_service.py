"""
Authentication business logic — registration, login, token management.
"""
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.models.profile import Profile
from app.schemas.auth import RegisterRequest, LoginRequest
from app.utils.slug import unique_slug


class AuthError(Exception):
    pass


def register_user(data: RegisterRequest, db: Session) -> User:
    if data.password != data.confirm_password:
        raise AuthError("Passwords do not match.")

    if db.query(User).filter(User.email == data.email).first():
        raise AuthError("Email already registered.")

    if db.query(User).filter(User.username == data.username).first():
        raise AuthError("Username already taken.")

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        role="user",
        is_active=True,
        is_verified=True,
    )

    db.add(user)
    db.flush()

    slug = unique_slug(data.username, db)
    profile = Profile(user_id=user.id, slug=slug)
    db.add(profile)

    db.commit()
    db.refresh(user)
    db.refresh(profile)

    # Generate QR code once at registration so it's immediately available
    try:
        from app.services import qr_service
        qr_service.generate_qr_for_profile(profile, db)
    except Exception:
        pass  # Non-fatal: QR will be generated on first visit if this fails

    return user


def authenticate_user(data: LoginRequest, db: Session) -> str:
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.hashed_password):
        raise AuthError("Invalid email or password.")

    if not user.is_active:
        raise AuthError("Account inactive.")

    return create_access_token(subject=user.id, role=user.role)