"""
Application configuration — reads from environment variables / .env file.
All settings are validated by Pydantic at startup.
"""
from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "DigiBioFi"
    app_env: str = "development"
    debug: bool = True
    secret_key: str
    base_url: str = "http://localhost:8000"
    redis_url: str = ""
    # ── Security ─────────────────────────────────────────────────────────────
    # Session / CSRF / Rate limiting
    csrf_secret_key: str = "csrf-secret-key-change-me"
    rate_limit_requests: int = 60
    rate_limit_seconds: int = 60

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str

    # ── JWT ──────────────────────────────────────────────────────────────────
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    password_reset_expire_minutes: int = 30
    email_verification_expire_hours: int = 24

    # ── File uploads ─────────────────────────────────────────────────────────
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 5
    free_daily_profile_view_limit: int = 25

    # ── Admin bootstrap ───────────────────────────────────────────────────────
    admin_email: str
    admin_password: str

    # ── Email (scaffold) ─────────────────────────────────────────────────────
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    emails_from_email: str = "noreply@example.com"
    emails_from_name: str = "DigiBioFi"

    # ── Stripe ───────────────────────────────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Billing tiers
    stripe_price_basic: str = ""
    stripe_price_elite: str = ""

    # ── Signal messaging ─────────────────────────────────────────────────────
    signal_sender_number: str = ""

    # ── Ads ──────────────────────────────────────────────────────────────────
    adsense_client_id: str = ""
    adsense_public_inline_slot: str = ""
    adsense_public_sidebar_slot: str = ""
    adsense_dashboard_slot: str = ""

    def get_stripe_price(self, plan: str) -> str:
        normalized_plan = (plan or "").strip().lower()
        if normalized_plan == "basic":
            return self.stripe_price_basic
        if normalized_plan == "elite":
            return self.stripe_price_elite
        raise ValueError(f"Invalid plan: {plan}")

    # ── CORS ─────────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:8000"

    # ── Validation ───────────────────────────────────────────────────────────
    # Known insecure defaults that must never reach production
    _INSECURE_SECRET_KEYS: ClassVar[frozenset[str]] = frozenset({
        "insecure-default-change-me",
        "digibiofi-dev-secret-key-32-chars-at-least-!!",
    })

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        value = (v or "").strip().lower()
        if not value:
            raise ValueError("APP_ENV must be set via the environment.")
        return value

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """Reject known weak defaults and any key shorter than 32 chars."""
        if len(v) < 32 or v in cls._INSECURE_SECRET_KEYS:
            raise ValueError(
                "SECRET_KEY is too weak. Set a unique SECRET_KEY of at least "
                "32 characters via the environment or .env file."
            )
        return v

    @field_validator("database_url", "admin_email")
    @classmethod
    def validate_required_strings(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name.upper()} must be set via the environment.")
        return v.strip()

    @field_validator("csrf_secret_key")
    @classmethod
    def validate_csrf_secret_key(cls, v: str, info) -> str:
        app_env = (info.data.get("app_env") or "").lower()
        if app_env == "production" and (
            v == "csrf-secret-key-change-me" or len(v) < 32
        ):
            raise ValueError(
                "CSRF_SECRET_KEY is too weak. Must be at least 32 characters long "
                "and not the default value in production."
            )
        return v

    @field_validator("admin_password")
    @classmethod
    def validate_admin_password(cls, v: str) -> str:
        """Ensure admin password is set in environment."""
        if not v or v.strip() == "":
            raise ValueError(
                "ADMIN_PASSWORD must be set via environment variable. "
                "This is a security requirement — never use hardcoded defaults."
            )
        if len(v) < 8:
            raise ValueError("ADMIN_PASSWORD must be at least 8 characters long.")
        return v

    @field_validator("free_daily_profile_view_limit")
    @classmethod
    def validate_free_daily_profile_view_limit(cls, v: int) -> int:
        if v < 1:
            raise ValueError("FREE_DAILY_PROFILE_VIEW_LIMIT must be at least 1.")
        return v

    @field_validator("email_verification_expire_hours")
    @classmethod
    def validate_email_verification_expire_hours(cls, v: int) -> int:
        if v < 1:
            raise ValueError("EMAIL_VERIFICATION_EXPIRE_HOURS must be at least 1.")
        return v

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()


settings = get_settings()
