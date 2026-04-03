"""
Tests for registration, login, and logout flows.
"""
from app.core.security import AUTH_COOKIE_NAME


class TestRegistration:
    def test_register_success_redirects(self, client):
        resp = client.post("/register", data={
            "email": "new@example.com",
            "username": "newuser",
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login?registered=1"

    def test_register_duplicate_email(self, client, registered_user):
        resp = client.post("/register", data={
            "email": "test@example.com",    # same email
            "username": "otheruser",
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert resp.status_code == 400
        assert b"already registered" in resp.content or b"already exists" in resp.content

    def test_register_duplicate_username(self, client, registered_user):
        resp = client.post("/register", data={
            "email": "other@example.com",
            "username": "testuser",         # same username
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert resp.status_code == 400

    def test_register_password_mismatch(self, client):
        resp = client.post("/register", data={
            "email": "mismatch@example.com",
            "username": "mismatchuser",
            "password": "TestPass123!",
            "confirm_password": "different",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert resp.status_code == 422

    def test_register_short_password(self, client):
        resp = client.post("/register", data={
            "email": "short@example.com",
            "username": "shortpw",
            "password": "123",
            "confirm_password": "123",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert resp.status_code == 422

    def test_register_invalid_username(self, client):
        resp = client.post("/register", data={
            "email": "special@example.com",
            "username": "user name!",   # spaces/special chars not allowed
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert resp.status_code == 422


class TestLogin:
    def test_login_success_sets_cookie(self, client, registered_user):
        resp = client.post("/login", data={
            "email": "test@example.com",
            "password": "TestPass123!",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert resp.status_code == 303
        assert AUTH_COOKIE_NAME in resp.cookies

    def test_login_email_is_case_insensitive(self, client, registered_user):
        resp = client.post("/login", data={
            "email": "TEST@EXAMPLE.COM",
            "password": "TestPass123!",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_login_wrong_password(self, client, registered_user):
        resp = client.post("/login", data={
            "email": "test@example.com",
            "password": "wrongpassword",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert resp.status_code == 401
        assert b"Invalid" in resp.content

    def test_login_unknown_email(self, client):
        resp = client.post("/login", data={
            "email": "nobody@example.com",
            "password": "TestPass123!",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert resp.status_code == 401

    def test_logout_clears_cookie(self, auth_client):
        resp = auth_client.get("/logout", follow_redirects=False)
        assert resp.status_code == 303
        # Cookie should be cleared (empty value or expired)
        assert AUTH_COOKIE_NAME not in resp.cookies or resp.cookies[AUTH_COOKIE_NAME] == ""


class TestPasswordReset:
    def test_forgot_password_shows_reset_link_in_non_production(self, client, registered_user):
        resp = client.post("/forgot-password", data={
            "email": "test@example.com",
            "csrf_token": "test",
        })
        assert resp.status_code == 200
        assert b"/reset-password?token=" in resp.content

    def test_reset_password_allows_new_login(self, client, db, registered_user):
        from app.models.user import User
        from app.services.auth_service import create_password_reset_token

        user = db.query(User).filter(User.email == "test@example.com").first()
        token = create_password_reset_token(user)

        reset_resp = client.post("/reset-password", data={
            "token": token,
            "new_password": "NewPass123!",
            "confirm_password": "NewPass123!",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert reset_resp.status_code == 303
        assert reset_resp.headers["location"] == "/login"

        old_login = client.post("/login", data={
            "email": "test@example.com",
            "password": "TestPass123!",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert old_login.status_code == 401

        new_login = client.post("/login", data={
            "email": "test@example.com",
            "password": "NewPass123!",
            "csrf_token": "test",
        }, follow_redirects=False)
        assert new_login.status_code == 303
