"""
QR code generation service.

Generates a PNG QR code for a profile's public URL and persists it to storage.
The QR code record in the database tracks the image path and the URL it encodes.
"""
import io
import uuid
from datetime import datetime, timezone

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.profile import Profile, QRCode
from app.services.storage import storage


def generate_qr_for_profile(profile: Profile, db: Session) -> QRCode:
    """
    Generate (or regenerate) a QR code PNG for the profile's public URL.

    - Uses a persistent qr_id (UUID).
    - Creates the PNG file in storage.
    - Upserts the QRCode record in the database.
    - Returns the updated QRCode model instance.
    """
    # 1. Get or create persistent QR record
    qr_record = db.query(QRCode).filter(QRCode.profile_id == profile.id).first()
    if not qr_record:
        qr_record = QRCode(
            profile_id=profile.id,
            qr_id=uuid.uuid4(),
            image_path="", # will be set below
            qr_url="", # will be set below
        )
        db.add(qr_record)
        db.flush() # ensure qr_record.qr_id is available if not set yet (though we set it)

    # 2. Build the signature URL
    qr_url = f"{settings.base_url}/p/{profile.slug}?src=qr&qr_id={qr_record.qr_id}"
    
    # 3. Generate QR image
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
    
    path = f"qr_codes/{profile.slug}.png"
    storage.save(img_byte_arr, path)

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
    if storage.exists(path):
        return storage.get_url(path)
    return None


def get_qr_bytes(slug: str) -> bytes | None:
    """Read a QR PNG from storage and return raw bytes, or None if not found."""
    path = f"qr_codes/{slug}.png"
    if not storage.exists(path):
        return None
    # Storage interface should probably have a read() method but we can use open() if local
    # For now, since we know it's LocalStorage in this phase:
    full_path = settings.upload_path / path
    if full_path.exists():
        return full_path.read_bytes()
    return None
