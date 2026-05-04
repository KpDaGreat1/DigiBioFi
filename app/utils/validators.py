"""
File upload and input validation helpers.
"""
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import UploadFile, HTTPException, status
from pydantic import ValidationError

from app.core.config import settings

# Allowed MIME types per upload category
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_PDF_TYPES = {"application/pdf"}

# Max file name length to prevent path traversal / long-name attacks
MAX_FILENAME_LEN = 120


def validate_image_upload(file: UploadFile) -> None:
    """Raise HTTPException if the file is not an allowed image type or too large."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image must be JPEG, PNG, or WebP. Got: {file.content_type}",
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
    """
    Pre-reject uploads that declare an oversized Content-Length header.
    The authoritative byte-count check still happens after writing in file_service;
    this is a fast early reject to avoid writing obviously-too-large files.
    """
    try:
        headers = getattr(file, "headers", None)
        if headers:
            content_length = int(headers.get("content-length") or 0)
            if content_length > settings.max_upload_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds maximum size of {settings.max_upload_size_mb} MB.",
                )
    except HTTPException:
        raise
    except Exception:
        pass  # If header check fails for any reason, fall through to post-write check


def safe_filename(original: str) -> str:
    """Return a sanitized filename (no path traversal, no special chars)."""
    name = Path(original).name  # strip any directory component
    # Replace anything outside alphanumerics, dot, dash, underscore
    import re
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:MAX_FILENAME_LEN]


def hash_visitor(ip: str, user_agent: str, current_day: date | None = None) -> str:
    """
    Create a daily-rotating anonymised visitor fingerprint for analytics deduplication.
    The hash is derived from SECRET_KEY + day + IP + user agent so it rotates every UTC day
    and cannot be reversed back into a raw IP address from stored data.
    """
    day = current_day or datetime.now(timezone.utc).date()
    raw = f"{settings.secret_key}|{day.isoformat()}|{ip or 'unknown'}|{user_agent or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def hash_daily_client_token(ip: str, secret_key: str, current_day: date | None = None) -> str:
    """
    Create a daily-rotating anonymized token for a client IP.
    The same IP hashes consistently for one UTC day, then rotates automatically.
    """
    day = current_day or datetime.now(timezone.utc).date()
    raw = f"{secret_key}|{day.isoformat()}|{ip or 'unknown'}"
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


def sanitize_plain_text(value: str) -> str:
    """
    Strip all HTML from plain-text inputs such as contact subjects and messages.
    """
    import bleach

    return bleach.clean(value or "", tags=[], attributes={}, strip=True).strip()


def sanitize_article_html(value: str) -> str:
    """
    Sanitize admin-authored article HTML before it is stored or rendered publicly.
    Allows basic editorial formatting while stripping active content.
    """
    import re
    import bleach

    cleaned = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", value or "")
    cleaned = re.sub(r"(?is)<iframe[^>]*>.*?</iframe>", "", cleaned)

    allowed_tags = [
        "p", "br", "ul", "ol", "li",
        "a", "strong", "em", "b", "i",
        "blockquote", "code", "pre", "hr",
        "h2", "h3", "h4",
    ]
    allowed_attrs = {"a": ["href", "rel", "target"]}
    return bleach.clean(
        cleaned,
        tags=allowed_tags,
        attributes=allowed_attrs,
        protocols=["http", "https", "mailto"],
        strip=True,
    )


def normalize_external_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must start with http:// or https://")

    return value


def normalize_optional_external_url(value: str | None) -> str | None:
    if not value:
        return None

    try:
        return normalize_external_url(value)
    except ValueError:
        return None


_BLOCKED_WORDS: set[str] = {
    "spam", "casino", "viagra", "porn", "xxx", "hack", "phishing",
    "nigger", "faggot", "chink", "spic", "kike",
}


def check_word_filter(text: str) -> bool:
    """Return True if text contains a blocked word, False otherwise."""
    lower = text.lower()
    return any(w in lower for w in _BLOCKED_WORDS)


def format_pydantic_errors(e: ValidationError) -> dict:
    """Format Pydantic errors into a {field: message} dictionary."""
    errors = {}
    for error in e.errors():
        location = error.get("loc") or ()
        if location:
            field = str(location[-1])
        else:
            field = "confirm_password" if "match" in error["msg"].lower() else "general"
        msg = error["msg"]
        # Clean up common Pydantic message prefixes
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        errors[field] = msg
    return errors
