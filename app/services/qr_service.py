"""
QR code generation service.

Generates a PNG QR code for a profile's public URL and persists it to storage.
The QR code record in the database tracks the image path and the URL it encodes.
"""
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.profile import Profile, QRCode
from app.services.storage import LocalStorage

# QR codes are stored under uploads/qr_codes/ and served at /qr_codes/<slug>.png
# The static mount in main.py maps /qr_codes/ → uploads/qr_codes/
qr_storage = LocalStorage(url_prefix="/uploads")


def generate_qr_for_profile(profile: Profile, db: Session, force: bool = False) -> QRCode:
    """
    Generate (or reuse) a persistent QR code PNG for the profile's public URL.

    - QR is generated once at profile creation (or first demand).
    - Checks for existing record and file before creating new.
    - QR URL always points to the same profile slug.
    - No regeneration unless explicitly triggered.
    """
    # 1. Get or create persistent QR record
    qr_record = db.query(QRCode).filter(QRCode.profile_id == profile.id).first()
    
    # Path is constant based on profile slug
    path = f"qr_codes/{profile.slug}.png"

    if not force and qr_record and qr_record.image_path and qr_storage.exists(path):
        # Already exists and file is there, return it
        return qr_record

    if not qr_record:
        qr_record = QRCode(
            profile_id=profile.id,
            qr_id=uuid.uuid4(),
            image_path=path,
            qr_url="", # will be set below
        )
        db.add(qr_record)
        db.flush()

    # 2. Build the signature URL (must be stable)
    qr_url = f"{settings.base_url}/p/{profile.slug}?src=qr&qr_id={qr_record.qr_id}"
    
    # 3. Generate QR image if it doesn't exist or forced
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=4,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
    )

    # 4. Save to storage
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    qr_storage.save(img_byte_arr, path)

    # 5. Update record
    qr_record.image_path = path
    qr_record.qr_url = qr_url
    qr_record.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(qr_record)
    return qr_record


def get_qr_url(slug: str) -> str | None:
    """Return the public URL for the QR image."""
    path = f"qr_codes/{slug}.png"
    if qr_storage.exists(path):
        return qr_storage.get_url(path)
    return None


def get_qr_bytes(slug: str) -> bytes | None:
    """Read a QR PNG from storage and return raw bytes, or None if not found."""
    path = f"qr_codes/{slug}.png"
    if not qr_storage.exists(path):
        return None

    full_path = Path(settings.upload_dir) / path
    if full_path.exists():
        return full_path.read_bytes()
    return None
