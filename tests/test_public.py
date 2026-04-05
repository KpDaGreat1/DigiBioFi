"""
Tests for the public profile page rendering and access control.
"""
import pytest
from pathlib import Path

from app.core.config import settings
from app.core.security import hash_password

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

    def test_private_resume_returns_404(self, db, client, registered_user, monkeypatch, tmp_path):
        from app.models.user import User

        monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

        resume_dir = tmp_path / "resumes"
        resume_dir.mkdir(parents=True, exist_ok=True)
        resume_path = resume_dir / "resume_test.pdf"
        resume_path.write_bytes(b"%PDF-1.4\n")

        user = db.query(User).filter(User.email == "test@example.com").first()
        user.profile.is_public = False
        user.profile.resume_pdf = "/uploads/resumes/resume_test.pdf"
        db.commit()

        resp = client.get(f"/resume/download/{user.profile.slug}", follow_redirects=False)
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

    def test_verified_badge_uses_profile_owner_state(self, db, client, registered_user):
        from app.models.user import User

        user = db.query(User).filter(User.email == "test@example.com").first()
        user.is_verified = True
        user.profile.is_public = True
        db.commit()

        resp = client.get(f"/p/{user.profile.slug}")
        assert resp.status_code == 200
        assert b"Verified Pro" in resp.content

    def test_public_profile_ads_render_only_for_free_owner(self, db, client, registered_user, monkeypatch):
        from app.models.user import User

        monkeypatch.setattr(settings, "adsense_client_id", "ca-pub-test")
        monkeypatch.setattr(settings, "adsense_public_inline_slot", "111")
        monkeypatch.setattr(settings, "adsense_public_sidebar_slot", "222")

        user = db.query(User).filter(User.email == "test@example.com").first()
        user.profile.is_public = True
        db.commit()

        free_resp = client.get(f"/p/{user.profile.slug}")
        assert free_resp.status_code == 200
        assert b'data-ad-slot="111"' in free_resp.content
        assert b'data-ad-slot="222"' in free_resp.content

        user.subscription_tier = "elite"
        user.subscription_status = "active"
        db.commit()

        paid_resp = client.get(f"/p/{user.profile.slug}")
        assert paid_resp.status_code == 200
        assert b'data-ad-slot="111"' not in paid_resp.content
        assert b'data-ad-slot="222"' not in paid_resp.content

    def test_public_profile_ads_do_not_render_without_client_id(self, db, client, registered_user, monkeypatch):
        from app.models.user import User

        monkeypatch.setattr(settings, "adsense_client_id", "")
        monkeypatch.setattr(settings, "adsense_public_inline_slot", "111")
        monkeypatch.setattr(settings, "adsense_public_sidebar_slot", "222")

        user = db.query(User).filter(User.email == "test@example.com").first()
        user.profile.is_public = True
        db.commit()

        resp = client.get(f"/p/{user.profile.slug}")
        assert resp.status_code == 200
        assert b"adsbygoogle" not in resp.content

    def test_free_user_hits_daily_profile_view_limit(self, db, auth_client, monkeypatch):
        from app.models.profile import Profile
        from app.models.user import User

        monkeypatch.setattr(settings, "free_daily_profile_view_limit", 1)

        target_user = User(
            email="target@example.com",
            username="targetuser",
            hashed_password=hash_password("TestPass123!"),
            role="user",
            subscription_tier="basic",
            subscription_status="active",
            is_active=True,
            is_verified=False,
        )
        db.add(target_user)
        db.flush()
        db.add(Profile(user_id=target_user.id, slug="targetuser", is_public=True))
        db.commit()

        first_resp = auth_client.get("/p/targetuser", follow_redirects=False)
        second_resp = auth_client.get("/p/targetuser", follow_redirects=False)

        assert first_resp.status_code == 200
        assert second_resp.status_code == 303
        assert second_resp.headers["location"] == "/dashboard/upgrade"

    def test_anonymous_public_profile_throttle_returns_429_page(self, db, client, registered_user, monkeypatch):
        from app.models.user import User

        monkeypatch.setattr("app.routers.public._ANONYMOUS_DAILY_PROFILE_VIEW_LIMIT", 1)
        from app.routers import public as public_router
        public_router._anonymous_profile_views.clear()

        user = db.query(User).filter(User.email == "test@example.com").first()
        user.profile.is_public = True
        db.commit()

        first_resp = client.get(f"/p/{user.profile.slug}")
        second_resp = client.get(f"/p/{user.profile.slug}")

        assert first_resp.status_code == 200
        assert second_resp.status_code == 429
        assert b"Too many requests" in second_resp.content

    def test_free_owner_portfolio_is_hidden_publicly(self, db, client, registered_user):
        from app.models.profile import Project
        from app.models.user import User

        user = db.query(User).filter(User.email == "test@example.com").first()
        user.profile.is_public = True
        db.add(
            Project(
                profile_id=user.profile.id,
                name="Hidden Portfolio Item",
                description="Should not render for free tier",
                url="https://example.com",
                thumbnail_url="",
                display_order=0,
            )
        )
        db.commit()

        resp = client.get(f"/p/{user.profile.slug}")
        assert resp.status_code == 200
        assert b"Hidden Portfolio Item" not in resp.content


class TestDashboardAds:
    def test_dashboard_ad_renders_only_for_free_user(self, db, auth_client, monkeypatch):
        from app.models.user import User

        monkeypatch.setattr(settings, "adsense_client_id", "ca-pub-test")
        monkeypatch.setattr(settings, "adsense_dashboard_slot", "333")

        free_resp = auth_client.get("/dashboard")
        assert free_resp.status_code == 200
        assert b'data-ad-slot="333"' in free_resp.content

        user = db.query(User).filter(User.email == "test@example.com").first()
        user.subscription_tier = "elite"
        user.subscription_status = "active"
        db.commit()

        paid_resp = auth_client.get("/dashboard")
        assert paid_resp.status_code == 200
        assert b'data-ad-slot="333"' not in paid_resp.content


class TestDashboardAnalytics:
    def test_free_dashboard_hides_analytics(self, auth_client):
        resp = auth_client.get("/dashboard")
        assert resp.status_code == 200
        assert b"Recent Visits" not in resp.content
        assert b"Current Plan" in resp.content
        assert b"Upgrade Plan" in resp.content

    def test_elite_dashboard_shows_recent_visit_analytics(self, db, auth_client):
        from datetime import datetime, timezone

        from app.models.analytics import ProfileView
        from app.models.user import User

        user = db.query(User).filter(User.email == "test@example.com").first()
        user.subscription_tier = "elite"
        user.subscription_status = "active"
        db.add(
            ProfileView(
                profile_id=user.profile.id,
                viewer_ip="203.0.113.10",
                user_agent="Mozilla/5.0",
                visitor_hash="hash-one",
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        resp = auth_client.get("/dashboard")
        assert resp.status_code == 200
        assert b"Recent Visits" in resp.content
        assert b"203.0.113.10" in resp.content

    def test_invalid_subscription_status_treated_as_free(self, db, auth_client, monkeypatch):
        from app.models.user import User

        monkeypatch.setattr(settings, "adsense_client_id", "ca-pub-test")
        monkeypatch.setattr(settings, "adsense_dashboard_slot", "333")

        user = db.query(User).filter(User.email == "test@example.com").first()
        user.subscription_tier = "elite"
        user.subscription_status = "paused"
        db.commit()

        resp = auth_client.get("/dashboard")
        assert resp.status_code == 200
        assert b"Recent Visits" not in resp.content
        assert b'data-ad-slot="333"' in resp.content


class TestAnalyticsSafety:
    def test_track_event_returns_ok_when_logging_fails(self, db, client, registered_user, monkeypatch):
        from app.models.user import User

        user = db.query(User).filter(User.email == "test@example.com").first()
        user.profile.is_public = True
        db.commit()

        def fail(*args, **kwargs):
            raise RuntimeError("analytics down")

        monkeypatch.setattr("app.routers.public.analytics_service.record_event", fail)

        resp = client.post(
            f"/api/analytics/event/{user.profile.slug}",
            json={"event_type": "link_click", "source": "direct", "link_target": "website"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
