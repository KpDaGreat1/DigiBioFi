"""
Tests for QR code generation and download.
"""
import pytest
from pathlib import Path
from unittest.mock import patch


class TestQRGeneration:
    def test_qr_generated_on_dashboard_qr_page(self, db, auth_client):
        """Visiting /dashboard/qr should generate a QR record."""
        resp = auth_client.get("/dashboard/qr")
        assert resp.status_code == 200

        from app.models.user import User
        from app.models.profile import QRCode
        user = db.query(User).filter(User.email == "test@example.com").first()
        qr = db.query(QRCode).filter(QRCode.profile_id == user.profile.id).first()
        assert qr is not None
        assert user.profile.slug in qr.qr_url

    def test_qr_image_file_created(self, db, auth_client):
        """QR PNG record should be created and image path stored in DB."""
        from app.models.user import User
        from app.models.profile import QRCode

        auth_client.get("/dashboard/qr")

        user = db.query(User).filter(User.email == "test@example.com").first()
        qr = db.query(QRCode).filter(QRCode.profile_id == user.profile.id).first()
        assert qr is not None
        assert qr.image_path.endswith(".png")
        assert user.profile.slug in qr.image_path

    def test_qr_regenerate(self, db, auth_client):
        """Regenerate endpoint should return redirect."""
        # First generate
        auth_client.get("/dashboard/qr")

        resp = auth_client.post("/dashboard/qr/regenerate", data={"csrf_token": "test"}, follow_redirects=False)
        assert resp.status_code == 303
        assert "regenerated=1" in resp.headers["location"]

    def test_qr_download_returns_png_bytes(self, db, auth_client):
        """Download endpoint should return PNG content."""
        from app.services.qr_service import get_qr_bytes

        # Generate QR for profile
        auth_client.get("/dashboard/qr")

        from app.models.user import User
        user = db.query(User).filter(User.email == "test@example.com").first()
        slug = user.profile.slug

        # Mock the file read so we don't need an actual file on disk
        with patch("app.routers.public.qr_service.get_qr_bytes", return_value=b"FAKEPNG"):
            resp = auth_client.get(f"/qr/download/{slug}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
