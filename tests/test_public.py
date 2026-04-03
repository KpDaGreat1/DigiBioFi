"""
Tests for the public profile page rendering and access control.
"""
import pytest


class TestPublicProfile:
    def test_public_profile_renders(self, db, auth_client):
        """A public profile page should return 200 with profile content."""
        # Add some profile data first
        auth_client.post("/dashboard/profile", data={
            "full_name": "Jane Test",
            "headline": "Software Engineer",
            "bio": "I build things.",
            "email": "jane@test.com",
            "phone": "", "location": "NYC",
            "website": "", "twitter": "", "github": "",
            "is_public": "on",
            "slug": "testuser",
            "csrf_token": "test",
        })

        from app.models.user import User
        user = db.query(User).filter(User.email == "test@example.com").first()
        slug = user.profile.slug

        resp = auth_client.get(f"/p/{slug}")
        assert resp.status_code == 200
        assert b"Jane Test" in resp.content
        assert b"Software Engineer" in resp.content

    def test_nonexistent_slug_returns_404(self, client):
        resp = client.get("/p/this-slug-does-not-exist-xyz")
        assert resp.status_code == 404

    def test_private_profile_returns_404(self, db, client, registered_user):
        """Private profiles should not be publicly accessible."""
        from app.models.user import User
        user = db.query(User).filter(User.email == "test@example.com").first()
        user.profile.is_public = False
        db.commit()

        resp = client.get(f"/p/{user.profile.slug}")
        assert resp.status_code == 404

    def test_profile_contains_qr_section(self, db, auth_client):
        """Public profile page should reference the QR code when available."""
        # Generate QR first
        auth_client.get("/dashboard/qr")

        from app.models.user import User
        user = db.query(User).filter(User.email == "test@example.com").first()
        slug = user.profile.slug

        resp = auth_client.get(f"/p/{slug}")
        assert resp.status_code == 200
        # Profile URL should appear (QR footer section)
        assert slug.encode() in resp.content

    def test_unauthenticated_can_view_public_profile(self, db, client, registered_user):
        """Public profiles should be viewable without login."""
        from app.models.user import User
        from app.models.profile import Profile
        # Use a fresh session — registered_user fixture used client fixture
        user = db.query(User).filter(User.email == "test@example.com").first()
        user.profile.is_public = True
        user.profile.full_name = "Public User"
        db.commit()

        resp = client.get(f"/p/{user.profile.slug}")
        assert resp.status_code == 200
        assert b"Public User" in resp.content
