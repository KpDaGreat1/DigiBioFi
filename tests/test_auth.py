"""
Tests for registration, login, and logout flows.
"""
import pytest
from app.core.security import AUTH_COOKIE_NAME


class TestRegistration:
    def test_register_success_redirects(self, client):
        resp = client.post("/register", data={
            "email": "new@example.com",
            "username": "newuser",
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
        }, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login?registered=1"

    def test_register_duplicate_email(self, client, registered_user):
        resp = client.post("/register", data={
            "email": "test@example.com",    # same email
            "username": "otheruser",
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
        }, follow_redirects=False)
        assert resp.status_code == 400
        assert b"already exists" in resp.content

    def test_register_duplicate_username(self, client, registered_user):
        resp = client.post("/register", data={
            "email": "other@example.com",
            "username": "testuser",         # same username
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
        }, follow_redirects=False)
        assert resp.status_code == 400

    def test_register_password_mismatch(self, client):
        resp = client.post("/register", data={
            "email": "mismatch@example.com",
            "username": "mismatchuser",
            "password": "TestPass123!",
            "confirm_password": "different",
        }, follow_redirects=False)
        assert resp.status_code == 400

    def test_register_short_password(self, client):
        resp = client.post("/register", data={
            "email": "short@example.com",
            "username": "shortpw",
            "password": "123",
            "confirm_password": "123",
        }, follow_redirects=False)
        assert resp.status_code == 400

    def test_register_invalid_username(self, client):
        resp = client.post("/register", data={
            "email": "special@example.com",
            "username": "user name!",   # spaces/special chars not allowed
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
        }, follow_redirects=False)
        assert resp.status_code == 400


class TestLogin:
    def test_login_success_sets_cookie(self, client, registered_user):
        resp = client.post("/login", data={
            "email": "test@example.com",
            "password": "TestPass123!",
        }, follow_redirects=False)
        assert resp.status_code == 303
        assert AUTH_COOKIE_NAME in resp.cookies

    def test_login_wrong_password(self, client, registered_user):
        resp = client.post("/login", data={
            "email": "test@example.com",
            "password": "wrongpassword",
        }, follow_redirects=False)
        assert resp.status_code == 401
        assert b"Invalid" in resp.content

    def test_login_unknown_email(self, client):
        resp = client.post("/login", data={
            "email": "nobody@example.com",
            "password": "TestPass123!",
        }, follow_redirects=False)
        assert resp.status_code == 401

    def test_logout_clears_cookie(self, auth_client):
        resp = auth_client.get("/logout", follow_redirects=False)
        assert resp.status_code == 302
        # Cookie should be cleared (empty value or expired)
        assert AUTH_COOKIE_NAME not in resp.cookies or resp.cookies[AUTH_COOKIE_NAME] == ""
