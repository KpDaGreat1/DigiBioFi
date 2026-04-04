"""
Authentication business logic — registration, login, token management.
"""
import logging
from datetime import datetime, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password, create_access_token
from app.core.config import settings
from app.models.user import User
from app.models.profile import Profile
from app.schemas.auth import RegisterRequest, LoginRequest, ResetPasswordRequest
from app.utils.slug import unique_slug

logger = logging.getLogger(__name__)
PASSWORD_RESET_SALT = "password-reset"


class AuthError(Exception):
    pass


def _password_reset_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key)


def _utc_timestamp(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return int(value.timestamp())


def register_user(data: RegisterRequest, db: Session) -> User:
    if data.password != data.confirm_password:
        raise AuthError("Passwords do not match.")

    email = data.email.lower()

    if db.query(User).filter(func.lower(User.email) == email).first():
        raise AuthError("Email already registered.")

    if db.query(User).filter(User.username == data.username).first():
        raise AuthError("Username already taken.")

    user = User(
        email=email,
        username=data.username,
        hashed_password=hash_password(data.password),
        role="user",
        is_active=True,
        is_verified=False,
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
    user = db.query(User).filter(func.lower(User.email) == data.email.lower()).first()

    if not user or not verify_password(data.password, user.hashed_password):
        raise AuthError("Invalid email or password.")

    if not user.is_active:
        raise AuthError("Account inactive.")

    return create_access_token(subject=user.id, role=user.role)


def create_password_reset_token(user: User) -> str:
    stamp = _utc_timestamp(user.updated_at)
    return _password_reset_serializer().dumps(
        {"uid": user.id, "stamp": stamp},
        salt=PASSWORD_RESET_SALT,
    )


def issue_password_reset(email: str, db: Session) -> str | None:
    user = db.query(User).filter(func.lower(User.email) == email.lower()).first()
    if not user or not user.is_active:
        return None

    token = create_password_reset_token(user)
    logger.info("Password reset token issued for user_id=%s", user.id)
    return token


def reset_password(data: ResetPasswordRequest, db: Session) -> User:
    try:
        payload = _password_reset_serializer().loads(
            data.token,
            salt=PASSWORD_RESET_SALT,
            max_age=settings.password_reset_expire_minutes * 60,
        )
    except SignatureExpired as exc:
        raise AuthError("Reset link expired.") from exc
    except BadSignature as exc:
        raise AuthError("Invalid reset link.") from exc

    user = db.query(User).filter(User.id == int(payload["uid"])).first()
    if not user or not user.is_active:
        raise AuthError("Invalid reset link.")

    current_stamp = _utc_timestamp(user.updated_at)
    if current_stamp != payload.get("stamp"):
        raise AuthError("Reset link expired.")

    user.hashed_password = hash_password(data.new_password)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user
