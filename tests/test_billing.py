import logging

from app.core.config import settings
from app.models.user import User


class TestBillingRoutes:
    def test_upgrade_page_posts_only_to_billing_route(self, auth_client):
        resp = auth_client.get("/dashboard/upgrade")
        assert resp.status_code == 200
        assert resp.content.count(b'action="/billing/create-checkout-session"') == 2
        assert b'value="basic"' in resp.content
        assert b'value="elite"' in resp.content
        assert b"/dashboard/subscribe" not in resp.content

    def test_checkout_rejects_invalid_plan(self, auth_client, monkeypatch, caplog):
        def should_not_run(*args, **kwargs):
            raise AssertionError("Stripe service should not be called for invalid plans")

        monkeypatch.setattr("app.routers.billing.stripe_service.get_or_create_customer", should_not_run)

        with caplog.at_level(logging.WARNING):
            resp = auth_client.post(
                "/billing/create-checkout-session",
                data={"plan": " enterprise ", "csrf_token": "test"},
                follow_redirects=True,
            )

        assert resp.status_code == 200
        assert b"Selected plan is invalid." in resp.content
        assert any("Invalid checkout plan attempt" in rec.message for rec in caplog.records)

    def test_checkout_missing_config_redirects_safely(self, auth_client, monkeypatch):
        monkeypatch.setattr(settings, "stripe_secret_key", "")
        monkeypatch.setattr(settings, "stripe_price_basic", "price_basic")

        def should_not_run(*args, **kwargs):
            raise AssertionError("Stripe service should not be called without config")

        monkeypatch.setattr("app.routers.billing.stripe_service.get_or_create_customer", should_not_run)

        resp = auth_client.post(
            "/billing/create-checkout-session",
            data={"plan": "basic", "csrf_token": "test"},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"Billing is not configured yet." in resp.content

    def test_checkout_success_redirects_with_deterministic_urls(self, auth_client, monkeypatch):
        monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
        monkeypatch.setattr(settings, "stripe_price_basic", "price_basic")

        captured = {}

        def fake_get_or_create_customer(email, existing_customer_id):
            captured["email"] = email
            captured["customer_id_in"] = existing_customer_id
            return "cus_123"

        def fake_create_checkout_session(**kwargs):
            captured.update(kwargs)
            return "https://checkout.stripe.test/session"

        monkeypatch.setattr("app.routers.billing.stripe_service.get_or_create_customer", fake_get_or_create_customer)
        monkeypatch.setattr("app.routers.billing.stripe_service.create_checkout_session", fake_create_checkout_session)

        resp = auth_client.post(
            "/billing/create-checkout-session",
            data={"plan": "  BASIC  ", "csrf_token": "test"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert resp.headers["location"] == "https://checkout.stripe.test/session"
        assert captured["plan"] == "basic"
        assert captured["customer_id"] == "cus_123"
        assert captured["success_url"].endswith("/dashboard?success=true&plan=basic")
        assert captured["cancel_url"].endswith("/dashboard?canceled=true&plan=basic")

    def test_checkout_handles_stripe_errors_without_raw_500(self, auth_client, monkeypatch, caplog):
        monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
        monkeypatch.setattr(settings, "stripe_price_elite", "price_elite")
        monkeypatch.setattr("app.routers.billing.stripe_service.get_or_create_customer", lambda *args, **kwargs: "cus_123")

        def fail_checkout(**kwargs):
            raise RuntimeError("stripe exploded")

        monkeypatch.setattr("app.routers.billing.stripe_service.create_checkout_session", fail_checkout)

        with caplog.at_level(logging.ERROR):
            resp = auth_client.post(
                "/billing/create-checkout-session",
                data={"plan": "elite", "csrf_token": "test"},
                follow_redirects=True,
            )

        assert resp.status_code == 200
        assert b"Could not start checkout. Please try again." in resp.content
        assert any("Stripe checkout failed" in rec.message for rec in caplog.records)

    def test_billing_success_and_cancel_routes_are_redirect_only(self, auth_client):
        success = auth_client.get("/billing/success?plan=elite", follow_redirects=False)
        cancel = auth_client.get("/billing/cancel?plan=basic", follow_redirects=False)

        assert success.status_code == 303
        assert success.headers["location"] == "/dashboard?success=true&plan=elite"
        assert cancel.status_code == 303
        assert cancel.headers["location"] == "/dashboard?canceled=true&plan=basic"


class TestDashboardCheckoutMessages:
    def test_dashboard_success_redirects_once_and_flashes_for_active_plan(self, auth_client, db):
        user = db.query(User).filter(User.email == "test@example.com").first()
        user.subscription_tier = "basic"
        user.subscription_status = "active"
        db.commit()

        resp = auth_client.get("/dashboard?success=true&plan=basic", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Your Basic plan is active." in resp.content

        canonical = auth_client.get("/dashboard")
        assert canonical.status_code == 200
        assert b"Your Basic plan is active." not in canonical.content

    def test_dashboard_success_pending_flashes_processing_message(self, auth_client):
        resp = auth_client.get("/dashboard?success=true&plan=elite", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Billing is still processing." in resp.content

    def test_dashboard_cancel_redirects_once_without_loop(self, auth_client):
        resp = auth_client.get("/dashboard?canceled=true&plan=elite", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Checkout canceled. No charge was made." in resp.content

        canonical = auth_client.get("/dashboard", follow_redirects=False)
        assert canonical.status_code == 200


class TestLegalPages:
    def test_privacy_page_renders(self, client):
        resp = client.get("/privacy")
        assert resp.status_code == 200
        assert b"Privacy Policy" in resp.content

    def test_terms_page_renders(self, client):
        resp = client.get("/terms")
        assert resp.status_code == 200
        assert b"Terms of Service" in resp.content
