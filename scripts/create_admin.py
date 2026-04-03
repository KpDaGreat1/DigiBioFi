"""
Bootstrap script — creates an admin user from environment variables.

Usage:
    python scripts/create_admin.py

Set ADMIN_EMAIL and ADMIN_PASSWORD in your .env before running.
"""
import sys
import os

# Make app importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import func

from app.core.config import settings
from app.core.owner import apply_owner_access
from app.db.database import SessionLocal, engine
from app.db.schema import assert_schema_ready
from app.models.user import User  # noqa: F401 — registers model
import app.models  # noqa: F401 — registers all models
from app.core.security import hash_password


def main():
    assert_schema_ready(engine)

    db = SessionLocal()
    try:
        existing = (
            db.query(User)
            .filter(func.lower(User.email) == settings.admin_email.lower())
            .first()
        )
        if existing:
            print(f"User '{settings.admin_email}' already exists. Promoting to admin...")
            apply_owner_access(existing)
            db.commit()
            print("Done.")
            return

        # Generate a safe username from email
        username = settings.admin_email.split("@")[0].replace(".", "_").replace("+", "_")[:30]
        # Ensure unique username
        if db.query(User).filter(User.username == username).first():
            username = username[:26] + "_adm"

        user = User(
            email=settings.admin_email.lower(),
            username=username,
            hashed_password=hash_password(settings.admin_password),
            role="admin",
            subscription_tier="elite",
            subscription_status="active",
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        db.flush()

        from app.models.profile import Profile
        from app.utils.slug import unique_slug
        slug = unique_slug(username, db)
        profile = Profile(user_id=user.id, slug=slug)
        db.add(profile)
        db.commit()

        print(f"Admin user created:")
        print(f"  Email: {settings.admin_email}")
        print(f"  Password: (from ADMIN_PASSWORD env var)")
        print(f"  Profile slug: {slug}")
        print(f"\nLog in at: {settings.base_url}/login")

    finally:
        db.close()


if __name__ == "__main__":
    main()
