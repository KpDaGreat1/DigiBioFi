"""
Tests for analytics event recording and summary.
"""
import pytest
from app.models.analytics import AnalyticsEvent
from app.services.analytics_service import record_page_view, get_summary


class TestAnalyticsEvents:
    def test_page_view_recorded_on_public_profile_visit(self, db, auth_client):
        """Visiting /p/{slug} should record a page_view event."""
        from app.models.user import User
        user = db.query(User).filter(User.email == "test@example.com").first()
        slug = user.profile.slug

        resp = auth_client.get(f"/p/{slug}")
        assert resp.status_code == 200

        events = db.query(AnalyticsEvent).filter(AnalyticsEvent.profile_id == user.profile.id).all()
        assert len(events) >= 1
        assert any(e.event_type == "page_view" for e in events)

    def test_qr_source_recorded(self, db, auth_client):
        """Visiting with ?src=qr should record source as 'qr'."""
        from app.models.user import User
        user = db.query(User).filter(User.email == "test@example.com").first()
        slug = user.profile.slug

        auth_client.get(f"/p/{slug}?src=qr")

        events = db.query(AnalyticsEvent).filter(
            AnalyticsEvent.profile_id == user.profile.id,
            AnalyticsEvent.source == "qr",
        ).all()
        assert len(events) >= 1

    def test_link_click_event_via_api(self, db, auth_client):
        """POST to analytics event endpoint records link_click."""
        from app.models.user import User
        import json
        user = db.query(User).filter(User.email == "test@example.com").first()
        slug = user.profile.slug

        resp = auth_client.post(
            f"/api/analytics/event/{slug}",
            content=json.dumps({"event_type": "link_click", "source": "direct", "link_target": "github"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        events = db.query(AnalyticsEvent).filter(
            AnalyticsEvent.profile_id == user.profile.id,
            AnalyticsEvent.event_type == "link_click",
        ).all()
        assert len(events) == 1
        assert events[0].link_target == "github"

    def test_analytics_summary(self, db, auth_client):
        """Summary should aggregate events correctly."""
        from app.models.user import User
        user = db.query(User).filter(User.email == "test@example.com").first()
        slug = user.profile.slug

        # Record some events directly
        record_page_view(user.profile, "direct", "1.2.3.4", "test-ua", db)
        record_page_view(user.profile, "qr", "5.6.7.8", "test-ua", db)

        summary = get_summary(user.profile.id, db)
        assert summary.total_views == 2
        assert summary.qr_scans == 1

    def test_private_profile_returns_404(self, db, auth_client):
        """Private profiles should return 404 on public page."""
        from app.models.user import User
        user = db.query(User).filter(User.email == "test@example.com").first()
        user.profile.is_public = False
        db.commit()

        resp = auth_client.get(f"/p/{user.profile.slug}")
        assert resp.status_code == 404
