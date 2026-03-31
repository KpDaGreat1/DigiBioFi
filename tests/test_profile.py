"""
Tests for profile creation, update, slug logic, and section CRUD.
"""
import pytest
from app.models.profile import Profile
from app.services.profile_service import update_profile, SlugTaken
from app.schemas.profile import ProfileUpdate, ExperienceCreate


class TestProfileCreation:
    def test_profile_created_on_registration(self, db, client):
        """A blank profile should be auto-created during registration."""
        from app.models.user import User
        client.post("/register", data={
            "email": "profile@example.com",
            "username": "profileuser",
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
        })
        user = db.query(User).filter(User.email == "profile@example.com").first()
        assert user is not None
        assert user.profile is not None
        assert user.profile.slug == "profileuser"

    def test_slug_is_unique(self, db, client):
        """Two users with the same-ish username should get distinct slugs."""
        for i in range(3):
            client.post("/register", data={
                "email": f"user{i}@example.com",
                "username": f"dupuser{i}",
                "password": "TestPass123!",
                "confirm_password": "TestPass123!",
            })
        from app.models.profile import Profile
        slugs = [p.slug for p in db.query(Profile).all()]
        assert len(slugs) == len(set(slugs)), "Slugs must be unique"


class TestProfileUpdate:
    def test_update_basic_fields(self, db, auth_client):
        resp = auth_client.post("/dashboard/profile", data={
            "full_name": "Jane Doe",
            "headline": "Engineer",
            "bio": "Hello world",
            "email": "jane@example.com",
            "phone": "555-1234",
            "location": "NYC",
            "website": "",
            "linkedin": "",
            "twitter": "",
            "github": "",
            "slug": "testuser",
            "is_public": "on",
        }, follow_redirects=False)
        assert resp.status_code == 303

        # Reload from DB
        from app.models.user import User
        user = db.query(User).filter(User.email == "test@example.com").first()
        db.refresh(user.profile)
        assert user.profile.full_name == "Jane Doe"
        assert user.profile.headline == "Engineer"

    def test_slug_collision_rejected(self, db, client):
        """Trying to claim an already-taken slug should error."""
        # Create two users
        client.post("/register", data={
            "email": "u1@example.com", "username": "userslug1",
            "password": "TestPass123!", "confirm_password": "TestPass123!",
        })
        client.post("/register", data={
            "email": "u2@example.com", "username": "userslug2",
            "password": "TestPass123!", "confirm_password": "TestPass123!",
        })
        # Log in as user2 and try to steal user1's slug
        client.post("/login", data={"email": "u2@example.com", "password": "TestPass123!"})
        resp = client.post("/dashboard/profile", data={
            "full_name": "User Two",
            "slug": "userslug1",   # taken by user1
            "is_public": "on",
            "headline": "", "bio": "", "email": "", "phone": "",
            "location": "", "website": "", "linkedin": "", "twitter": "", "github": "",
        }, follow_redirects=False)
        assert resp.status_code == 400


class TestExperience:
    def test_add_experience(self, db, auth_client):
        resp = auth_client.post("/dashboard/experience/add", data={
            "company": "Acme Corp",
            "title": "Engineer",
            "location": "Remote",
            "start_date": "Jan 2022",
            "end_date": "",
            "is_current": "on",
            "description": "Built cool things.",
        }, follow_redirects=False)
        assert resp.status_code == 303

        from app.models.user import User
        from app.models.profile import Experience
        user = db.query(User).filter(User.email == "test@example.com").first()
        exps = db.query(Experience).filter(Experience.profile_id == user.profile.id).all()
        assert len(exps) == 1
        assert exps[0].company == "Acme Corp"

    def test_delete_experience(self, db, auth_client):
        # Add first
        auth_client.post("/dashboard/experience/add", data={
            "company": "To Delete", "title": "Dev", "location": "",
            "start_date": "2020", "end_date": "2021", "description": "",
        })
        from app.models.user import User
        from app.models.profile import Experience
        user = db.query(User).filter(User.email == "test@example.com").first()
        exp = db.query(Experience).filter(Experience.profile_id == user.profile.id).first()

        resp = auth_client.post(f"/dashboard/experience/{exp.id}/delete", follow_redirects=False)
        assert resp.status_code == 303
        assert db.query(Experience).filter(Experience.id == exp.id).first() is None
