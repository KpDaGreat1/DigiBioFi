"""
Seed clearly labeled example profiles for the public directory.

Usage:
    python scripts/seed_example_profiles.py
    python scripts/seed_example_profiles.py --purge

These profiles are marked as example content through their email domain,
headline, and bio so they never look like real user accounts.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.security import hash_password
from app.db.database import SessionLocal, engine
from app.db.schema import assert_schema_ready
from app.models.profile import Experience, Profile, Project, Skill
from app.models.user import User
from app.utils.slug import unique_slug


_EXAMPLE_EMAIL_DOMAIN = "example.invalid"
_EXAMPLE_PASSWORD = "example-profile-not-for-login"
_EXAMPLE_PROFILES = [
    {
        "email": f"sample-product-designer@{_EXAMPLE_EMAIL_DOMAIN}",
        "username": "sample_product_designer",
        "full_name": "Avery Stone",
        "headline": "Example Profile · Product Designer",
        "bio": (
            "Example Profile\n"
            "Editorial-style product design profile showing how case studies, proof links, "
            "and a concise career narrative can live in one polished public page."
        ),
        "location": "New York, NY",
        "website": "https://example.com/proof/product-designer",
        "skills": [("Product Design", "Design"), ("Figma", "Design"), ("Design Systems", "Design")],
        "experience": {
            "company": "Northstar Studio",
            "title": "Product Designer",
            "location": "New York, NY",
            "start_date": "2022",
            "end_date": "Present",
            "is_current": True,
            "description": "Leads product thinking, interface systems, and launch-ready design documentation across web products.",
        },
        "projects": [
            {
                "name": "Proof Link · Editorial Case Study",
                "description": "Sample case study showing research framing, interface rationale, and final outcomes in a premium portfolio format.",
                "url": "https://example.com/proof/editorial-case-study",
            },
            {
                "name": "Proof Link · Design System Rollout",
                "description": "Sample proof link demonstrating reusable UI components, documentation patterns, and adoption guidelines.",
                "url": "https://example.com/proof/design-system-rollout",
            },
        ],
    },
    {
        "email": f"sample-software-developer@{_EXAMPLE_EMAIL_DOMAIN}",
        "username": "sample_software_developer",
        "full_name": "Jordan Hale",
        "headline": "Example Profile · Software Developer",
        "bio": (
            "Example Profile\n"
            "Technical profile example built around shipped work, architecture thinking, "
            "and proof links that are easier to scan than a static resume."
        ),
        "location": "Remote",
        "website": "https://example.com/proof/software-developer",
        "github": "https://github.com/example/sample-software-developer",
        "skills": [("Python", "Backend"), ("FastAPI", "Backend"), ("PostgreSQL", "Backend")],
        "experience": {
            "company": "Signal Harbor",
            "title": "Software Developer",
            "location": "Remote",
            "start_date": "2021",
            "end_date": "Present",
            "is_current": True,
            "description": "Builds backend systems, public APIs, and production-ready delivery pipelines for customer-facing products.",
        },
        "projects": [
            {
                "name": "Proof Link · API Platform Launch",
                "description": "Sample proof link covering service architecture, deployment decisions, and API performance outcomes.",
                "url": "https://example.com/proof/api-platform-launch",
            },
            {
                "name": "Proof Link · GitHub Delivery Workflow",
                "description": "Sample proof link connecting technical implementation notes with repository structure and release discipline.",
                "url": "https://example.com/proof/github-delivery-workflow",
            },
        ],
    },
    {
        "email": f"sample-freelancer@{_EXAMPLE_EMAIL_DOMAIN}",
        "username": "sample_freelancer",
        "full_name": "Morgan Ellis",
        "headline": "Example Profile · Freelancer",
        "bio": (
            "Example Profile\n"
            "Consulting-focused profile example for independent professionals who need clear offers, "
            "testimonial highlights, and proof links in one place."
        ),
        "location": "Austin, TX",
        "website": "https://example.com/proof/freelancer",
        "skills": [("Client Strategy", "Consulting"), ("Workshops", "Consulting"), ("Content Systems", "Consulting")],
        "experience": {
            "company": "Brightline Media",
            "title": "Independent Consultant",
            "location": "Austin, TX",
            "start_date": "2021",
            "end_date": "Present",
            "is_current": True,
            "description": "Delivers consulting sprints, documentation, and repeatable engagement frameworks for growing teams.",
        },
        "projects": [
            {
                "name": "Proof Link · Client Testimonial Highlights",
                "description": "Sample proof link that groups short testimonial excerpts with project outcomes and engagement scope.",
                "url": "https://example.com/proof/client-testimonial-highlights",
            },
            {
                "name": "Proof Link · Consultation Package",
                "description": "Sample proof link showing service structure, workshop deliverables, and a concise call-to-action for new clients.",
                "url": "https://example.com/proof/consultation-package",
            },
        ],
    },
]


def _create_example_profile(db, payload: dict) -> None:
    user = User(
        email=payload["email"],
        username=payload["username"],
        hashed_password=hash_password(_EXAMPLE_PASSWORD),
        role="user",
        subscription_tier="basic",
        subscription_status="active",
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    db.flush()

    profile = Profile(
        user_id=user.id,
        slug=unique_slug(payload["username"].replace("_", "-"), db),
        full_name=payload["full_name"],
        headline=payload["headline"],
        bio=payload["bio"],
        location=payload["location"],
        website=payload.get("website", ""),
        github=payload.get("github", ""),
        is_public=True,
    )
    db.add(profile)
    db.flush()

    for order, (skill_name, category) in enumerate(payload["skills"]):
        db.add(
            Skill(
                profile_id=profile.id,
                name=skill_name,
                category=category,
                display_order=order,
            )
        )

    experience = payload["experience"]
    db.add(
        Experience(
            profile_id=profile.id,
            company=experience["company"],
            title=experience["title"],
            location=experience["location"],
            start_date=experience["start_date"],
            end_date=experience["end_date"],
            is_current=experience["is_current"],
            description=experience["description"],
            display_order=0,
        )
    )

    for order, project in enumerate(payload["projects"]):
        db.add(
            Project(
                profile_id=profile.id,
                name=project["name"],
                description=project["description"],
                url=project.get("url", ""),
                thumbnail_url="",
                display_order=order,
            )
        )


def seed_example_profiles(purge: bool = False) -> None:
    assert_schema_ready(engine)
    db = SessionLocal()
    try:
        existing_users = db.query(User).filter(User.email.like(f"%@{_EXAMPLE_EMAIL_DOMAIN}")).all()
        if purge:
            for user in existing_users:
                db.delete(user)
            db.commit()
            print(f"Removed {len(existing_users)} example profiles.")
            return

        target_emails = {payload["email"] for payload in _EXAMPLE_PROFILES}
        removed = 0
        for user in existing_users:
            if user.email not in target_emails:
                db.delete(user)
                removed += 1
        if removed:
            db.flush()

        existing_emails = {
            user.email
            for user in db.query(User).filter(User.email.like(f"%@{_EXAMPLE_EMAIL_DOMAIN}")).all()
        }
        created = 0
        for payload in _EXAMPLE_PROFILES:
            if payload["email"] in existing_emails:
                continue
            _create_example_profile(db, payload)
            created += 1

        db.commit()
        print(f"Created {created} example profiles. Removed {removed} stale example profiles.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_example_profiles(purge="--purge" in sys.argv[1:])
