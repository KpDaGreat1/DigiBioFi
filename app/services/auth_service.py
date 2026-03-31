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
    """Raised for auth-layer validation failures."""
    pass


def register_user(data: RegisterRequest, db: Session) -> User:
    """
    Create a new user + blank profile.

    Raises AuthError if the email or username is already taken.
    """
    # Check for duplicate email
    if db.query(User).filter(User.email == data.email).first():
        raise AuthError("An account with this email already exists.")

    # Check for duplicate username
    if db.query(User).filter(User.username == data.username).first():
        raise AuthError("This username is already taken.")

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        role="user",
        is_active=True,
        # Email verification scaffold — mark verified=True for MVP
        # (wire up email sending later)
        is_verified=True,
    )
    db.add(user)
    db.flush()  # get user.id before creating Profile

    # Create a blank profile with a unique slug derived from username
    slug = unique_slug(data.username, db)
    profile = Profile(user_id=user.id, slug=slug)
    db.add(profile)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(data: LoginRequest, db: Session) -> str:
    """
    Verify credentials and return a signed JWT access token.

    Raises AuthError on any failure (generic message to avoid enumeration).
    """
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise AuthError("Invalid email or password.")

    if not user.is_active:
        raise AuthError("Your account has been deactivated. Contact support.")

    return create_access_token(subject=user.id, role=user.role)
