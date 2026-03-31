"""
File upload service — stream-writes uploads to disk with size enforcement.

Upload directory layout (all under settings.upload_dir):
  profile_images/{user_id}.{ext}
  resumes/{user_id}.pdf
  qr_codes/{slug}.png   ← managed by qr_service
"""
import uuid
from pathlib import Path
import secrets

from fastapi import UploadFile, HTTPException, status

from app.core.config import settings
from app.utils.validators import validate_image_upload, validate_pdf_upload
from app.services.storage import storage


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

    # Randomize filename to prevent enumeration and overwriting
    random_suffix = secrets.token_hex(4)
    filename = f"profile_{user_id}_{random_suffix}.{ext}"
    path = f"profile_images/{filename}"

    # Use storage abstraction
    storage.save(upload.file, path)
    
    # Check size after save (or we could stream, but LocalStorage.save uses shutil.copyfileobj)
    # Actually, the requirement said "enforce file size". 
    # Let's check size before or during save.
    full_path = Path(settings.upload_dir) / path
    if full_path.stat().st_size > settings.max_upload_bytes:
        storage.delete(path)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_upload_size_mb} MB.",
        )

    return storage.get_url(path)


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

    random_suffix = secrets.token_hex(4)
    filename = f"resume_{user_id}_{random_suffix}.pdf"
    path = f"resumes/{filename}"

    storage.save(upload.file, path)
    
    full_path = Path(settings.upload_dir) / path
    if full_path.stat().st_size > settings.max_upload_bytes:
        storage.delete(path)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_upload_size_mb} MB.",
        )

    return storage.get_url(path)
