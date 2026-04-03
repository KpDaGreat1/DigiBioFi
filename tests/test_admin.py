from pathlib import Path

from app.core.config import settings
from app.core.security import hash_password
from app.models.profile import Profile, QRCode
from app.models.user import User


def create_managed_user(db, *, email: str, username: str, is_public: bool = True) -> User:
    user = User(
        email=email,
        username=username,
        hashed_password=hash_password("TestPass123!"),
        role="user",
        subscription_tier="free",
        subscription_status="active",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.flush()
    profile = Profile(user_id=user.id, slug=username, is_public=is_public)
    db.add(profile)
    db.commit()
    db.refresh(user)
    return user


class TestAdminPanel:
    def test_admin_requires_admin_role(self, auth_client):
        resp = auth_client.get("/admin")
        assert resp.status_code == 403

    def test_admin_can_manage_tier_status_and_visibility(self, admin_client, db):
        user = create_managed_user(db, email="member@example.com", username="memberuser")

        tier_resp = admin_client.post(
            f"/admin/users/{user.id}/set-tier",
            data={"tier": "premium", "csrf_token": "test"},
            follow_redirects=False,
        )
        assert tier_resp.status_code == 303

        db.refresh(user)
        assert user.subscription_tier == "premium"
        assert user.subscription_status == "active"

        active_resp = admin_client.post(
            f"/admin/users/{user.id}/toggle-active",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
        assert active_resp.status_code == 303

        db.refresh(user)
        assert user.is_active is False

        visibility_resp = admin_client.post(
            f"/admin/users/{user.id}/toggle-visibility",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
        assert visibility_resp.status_code == 303

        db.refresh(user.profile)
        assert user.profile.is_public is False

    def test_admin_can_delete_user_and_assets(self, admin_client, db, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

        user = create_managed_user(db, email="delete@example.com", username="deleteuser")
        resume_name = f"resume_{user.id}_asset.pdf"
        user.profile.resume_pdf = f"/uploads/resumes/{resume_name}"
        qr_dir = Path(settings.upload_dir) / "qr_codes"
        resume_dir = Path(settings.upload_dir) / "resumes"
        qr_dir.mkdir(parents=True, exist_ok=True)
        resume_dir.mkdir(parents=True, exist_ok=True)
        qr_path = qr_dir / f"{user.profile.slug}.png"
        resume_path = resume_dir / resume_name
        qr_path.write_bytes(b"qr")
        resume_path.write_bytes(b"resume")

        qr_code = QRCode(
            profile_id=user.profile.id,
            image_path=f"qr_codes/{user.profile.slug}.png",
            qr_url="http://example.com/qr",
        )
        db.add(qr_code)
        db.commit()

        resp = admin_client.post(
            f"/admin/users/{user.id}/delete",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert db.query(User).filter(User.id == user.id).first() is None
        assert db.query(Profile).filter(Profile.user_id == user.id).first() is None
        assert not qr_path.exists()
        assert not resume_path.exists()
