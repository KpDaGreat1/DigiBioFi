"""
Slug generation and uniqueness helpers.
"""
import random
import string

from slugify import slugify
from sqlalchemy.orm import Session


def generate_slug(name: str) -> str:
    """Turn a display name into a URL-safe slug (e.g. 'John Doe' → 'john-doe')."""
    return slugify(name, max_length=50, separator="-", lowercase=True) or "user"


def unique_slug(base: str, db: Session, exclude_profile_id: int | None = None) -> str:
    """
    Return a slug that doesn't already exist in the profiles table.

    If `base` is taken, append a random 4-char suffix until unique.
    Pass `exclude_profile_id` when updating an existing profile so we
    don't collide with ourselves.
    """
    from app.models.profile import Profile  # local import to avoid circular deps

    slug = slugify(base, max_length=46, separator="-", lowercase=True) or "user"

    while True:
        query = db.query(Profile).filter(Profile.slug == slug)
        if exclude_profile_id:
            query = query.filter(Profile.id != exclude_profile_id)

        if not query.first():
            return slug

        # Append a random 4-char alphanumeric suffix
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        slug = f"{slug[:46]}-{suffix}"
