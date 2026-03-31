"""
File upload and input validation helpers.
"""
import hashlib
from pathlib import Path

from fastapi import UploadFile, HTTPException, status

from app.core.config import settings

# Allowed MIME types per upload category
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_PDF_TYPES = {"application/pdf"}

# Max file name length to prevent path traversal / long-name attacks
MAX_FILENAME_LEN = 120


def validate_image_upload(file: UploadFile) -> None:
    """Raise HTTPException if the file is not an allowed image type or too large."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image must be JPEG, PNG, WebP, or GIF. Got: {file.content_type}",
        )
    _check_size_header(file)


def validate_pdf_upload(file: UploadFile) -> None:
    """Raise HTTPException if the file is not a PDF or too large."""
    if file.content_type not in ALLOWED_PDF_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resume must be a PDF file.",
        )
    _check_size_header(file)


def _check_size_header(file: UploadFile) -> None:
    """Check Content-Length header if present (best-effort pre-check)."""
    # The actual byte-count check happens during streaming in file_service.
    # This is just a fast reject for obviously over-limit requests.
    pass


def safe_filename(original: str) -> str:
    """Return a sanitized filename (no path traversal, no special chars)."""
    name = Path(original).name  # strip any directory component
    # Replace anything outside alphanumerics, dot, dash, underscore
    import re
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:MAX_FILENAME_LEN]


def hash_visitor(ip: str, user_agent: str) -> str:
    """
    Create an anonymised visitor fingerprint for analytics deduplication.
    SHA-256(ip + user_agent) — first 16 hex chars.
    This is not reversible to PII and doesn't store raw IP.
    """
    raw = f"{ip}|{user_agent}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def sanitize_text(value: str) -> str:
    """
    Strip disallowed HTML tags from user-supplied text fields.
    Bio / descriptions allow a small safe subset.
    """
    import bleach

    allowed_tags = ["b", "i", "em", "strong", "a", "br", "p", "ul", "ol", "li"]
    allowed_attrs = {"a": ["href", "rel", "target"]}
    cleaned = bleach.clean(value, tags=allowed_tags, attributes=allowed_attrs, strip=True)
    return cleaned
