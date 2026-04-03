"""
File upload service — stream-writes uploads to disk with size enforcement.

Upload directory layout (all under settings.upload_dir):
  profile_images/{user_id}.{ext}
  resumes/{user_id}.pdf
  qr_codes/{slug}.png   ← managed by qr_service
"""
from pathlib import Path
import secrets

from fastapi import UploadFile, HTTPException, status
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.utils.validators import validate_image_upload, validate_pdf_upload
from app.services.storage import storage


def _verify_image_content(upload: UploadFile, *, expected_formats: set[str]) -> None:
    try:
        upload.file.seek(0)
        image = Image.open(upload.file)
        image_format = (image.format or "").upper()
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a valid image.",
        ) from exc
    finally:
        upload.file.seek(0)

    if image_format not in expected_formats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image content does not match the declared file type.",
        )


def _verify_pdf_content(upload: UploadFile) -> None:
    try:
        upload.file.seek(0)
        signature = upload.file.read(5)
    finally:
        upload.file.seek(0)

    if signature != b"%PDF-":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a valid PDF.",
        )


def _enforce_saved_size(path: str) -> None:
    full_path = Path(settings.upload_dir) / path
    if full_path.stat().st_size > settings.max_upload_bytes:
        storage.delete(path)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_upload_size_mb} MB.",
        )


async def save_profile_image(upload: UploadFile, user_id: int) -> str:
    """
    Validate and save a profile image with a randomized filename.
    """
    validate_image_upload(upload)

    # Strict MIME validation
    ext_map = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    ext = ext_map.get(upload.content_type)
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image type. Use JPG, PNG, or WEBP."
        )

    _verify_image_content(
        upload,
        expected_formats={
            "image/jpeg": {"JPEG"},
            "image/png": {"PNG"},
            "image/webp": {"WEBP"},
        }[upload.content_type],
    )

    # Randomize filename to prevent enumeration and overwriting
    random_suffix = secrets.token_hex(4)
    filename = f"profile_{user_id}_{random_suffix}.{ext}"
    path = f"profile_images/{filename}"

    # Use storage abstraction
    upload.file.seek(0)
    saved_path = storage.save(upload.file, path)
    _enforce_saved_size(saved_path)

    return storage.get_url(saved_path)


async def save_resume_pdf(upload: UploadFile, user_id: int) -> str:
    """
    Validate and save a resume PDF with a randomized filename.
    """
    validate_pdf_upload(upload)
    
    if upload.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed for resumes."
        )

    _verify_pdf_content(upload)

    random_suffix = secrets.token_hex(4)
    filename = f"resume_{user_id}_{random_suffix}.pdf"
    path = f"resumes/{filename}"

    upload.file.seek(0)
    saved_path = storage.save(upload.file, path)
    _enforce_saved_size(saved_path)

    return storage.get_url(saved_path)


async def save_project_thumbnail(upload: UploadFile, user_id: int) -> str:
    """
    Validate and save a project thumbnail.
    """
    validate_image_upload(upload)

    ext_map = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    ext = ext_map.get(upload.content_type)
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image type. Use JPG, PNG, or WEBP."
        )

    _verify_image_content(
        upload,
        expected_formats={
            "image/jpeg": {"JPEG"},
            "image/png": {"PNG"},
            "image/webp": {"WEBP"},
        }[upload.content_type],
    )

    random_suffix = secrets.token_hex(4)
    filename = f"project_{user_id}_{random_suffix}.{ext}"
    path = f"project_thumbnails/{filename}"

    upload.file.seek(0)
    saved_path = storage.save(upload.file, path)
    _enforce_saved_size(saved_path)

    return storage.get_url(saved_path)


async def save_certificate_file(upload: UploadFile, user_id: int) -> str:
    if upload.content_type == "application/pdf":
        validate_pdf_upload(upload)
        _verify_pdf_content(upload)
        ext = "pdf"
    elif upload.content_type in {"image/jpeg", "image/png"}:
        validate_image_upload(upload)
        _verify_image_content(
            upload,
            expected_formats={
                "image/jpeg": {"JPEG"},
                "image/png": {"PNG"},
            }[upload.content_type],
        )
        ext = "jpg" if upload.content_type == "image/jpeg" else "png"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Certificate must be JPG, PNG, or PDF.",
        )

    random_suffix = secrets.token_hex(4)
    filename = f"cert_{user_id}_{random_suffix}.{ext}"
    path = f"certificates/{filename}"

    upload.file.seek(0)
    saved_path = storage.save(upload.file, path)
    _enforce_saved_size(saved_path)

    return storage.get_url(saved_path)
