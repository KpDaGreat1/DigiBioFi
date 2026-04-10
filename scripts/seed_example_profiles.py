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

from app.db.database import SessionLocal, engine
from app.db.schema import assert_schema_ready
from app.core.security import hash_password
from app.models.profile import Experience, Profile, Project, Skill
from app.models.user import User
from app.utils.slug import unique_slug


_EXAMPLE_EMAIL_DOMAIN = "example.invalid"
_EXAMPLE_PASSWORD = "example-profile-not-for-login"
_EXAMPLE_PROFILES = [
    {
        "email": f"sample-frontend@{_EXAMPLE_EMAIL_DOMAIN}",
        "username": "sample_frontend",
        "full_name": "Avery Stone",
        "headline": "Example Profile · Frontend Developer",
        "bio": "Example Profile\nFrontend-focused portfolio example showing a polished public profile with clear skills, projects, and contact structure.",
        "location": "Remote",
        "skills": [("React", "Frontend"), ("TypeScript", "Frontend"), ("Design Systems", "UI")],
        "experience": {
            "company": "Northstar Studio",
            "title": "Frontend Developer",
            "location": "Remote",
            "start_date": "2023",
            "end_date": "Present",
            "is_current": True,
            "description": "Builds marketing sites and product interfaces with an emphasis on reusable UI components and performance.",
        },
        "projects": [
            {
                "name": "Design System Starter",
                "description": "Example project card showing a reusable component library and documentation workflow.",
            }
        ],
    },
    {
        "email": f"sample-product@{_EXAMPLE_EMAIL_DOMAIN}",
        "username": "sample_product",
        "full_name": "Jordan Hale",
        "headline": "Example Profile · Product Manager",
        "bio": "Example Profile\nProduct strategy example focused on roadmap planning, cross-functional communication, and launch execution.",
        "location": "Chicago, IL",
        "skills": [("Product Strategy", "Product"), ("Research", "Product"), ("Roadmapping", "Product")],
        "experience": {
            "company": "Signal Harbor",
            "title": "Product Manager",
            "location": "Chicago, IL",
            "start_date": "2022",
            "end_date": "Present",
            "is_current": True,
            "description": "Leads product discovery, prioritization, and launch planning for customer-facing web products.",
        },
        "projects": [
            {
                "name": "Launch Planning Hub",
                "description": "Example project summarizing stakeholder alignment, research notes, and go-to-market planning.",
            }
        ],
    },
    {
        "email": f"sample-marketing@{_EXAMPLE_EMAIL_DOMAIN}",
        "username": "sample_marketing",
        "full_name": "Morgan Ellis",
        "headline": "Example Profile · Marketing Analyst",
        "bio": "Example Profile\nMarketing analytics example built to show reporting clarity, campaign thinking, and portfolio-ready case studies.",
        "location": "Austin, TX",
        "skills": [("Analytics", "Marketing"), ("Content Strategy", "Marketing"), ("SEO", "Marketing")],
        "experience": {
            "company": "Brightline Media",
            "title": "Marketing Analyst",
            "location": "Austin, TX",
            "start_date": "2021",
            "end_date": "Present",
            "is_current": True,
            "description": "Measures campaign performance, content trends, and conversion opportunities across owned channels.",
        },
        "projects": [
            {
                "name": "Quarterly Content Review",
                "description": "Example portfolio card highlighting campaign analysis, reporting structure, and editorial recommendations.",
            }
        ],
    },
    {
        "email": f"sample-designer@{_EXAMPLE_EMAIL_DOMAIN}",
        "username": "sample_designer",
        "full_name": "Riley Brooks",
        "headline": "Example Profile · Product Designer",
        "bio": "Example Profile\nDesign portfolio example that shows how layout, projects, and concise summaries can work together on a public profile.",
        "location": "Seattle, WA",
        "skills": [("Figma", "Design"), ("UX Research", "Design"), ("Interaction Design", "Design")],
        "experience": {
            "company": "Atlas Labs",
            "title": "Product Designer",
            "location": "Seattle, WA",
            "start_date": "2020",
            "end_date": "Present",
            "is_current": True,
            "description": "Designs user journeys, prototypes, and polished interface systems for web-based products.",
        },
        "projects": [
            {
                "name": "Mobile Onboarding Refresh",
                "description": "Example project showing research-backed UX improvements and a stronger onboarding experience.",
            }
        ],
    },
    {
        "email": f"sample-data@{_EXAMPLE_EMAIL_DOMAIN}",
        "username": "sample_data",
        "full_name": "Casey Nguyen",
        "headline": "Example Profile · Data Analyst",
        "bio": "Example Profile\nAnalytics profile example for dashboards, reporting work, and business-facing data storytelling.",
        "location": "New York, NY",
        "skills": [("SQL", "Data"), ("Python", "Data"), ("Dashboards", "Data")],
        "experience": {
            "company": "Summit Insights",
            "title": "Data Analyst",
            "location": "New York, NY",
            "start_date": "2022",
            "end_date": "Present",
            "is_current": True,
            "description": "Builds reporting workflows and business dashboards that help teams make faster operating decisions.",
        },
        "projects": [
            {
                "name": "Executive KPI Dashboard",
                "description": "Example project demonstrating SQL reporting, KPI definitions, and dashboard documentation.",
            }
        ],
    },
    {
        "email": f"sample-consultant@{_EXAMPLE_EMAIL_DOMAIN}",
        "username": "sample_consultant",
        "full_name": "Taylor Reed",
        "headline": "Example Profile · Operations Consultant",
        "bio": "Example Profile\nConsulting profile example built for professionals who need a clear summary, service focus, and project proof.",
        "location": "Remote",
        "skills": [("Operations", "Consulting"), ("Process Design", "Consulting"), ("Client Delivery", "Consulting")],
        "experience": {
            "company": "Fieldstone Advisory",
            "title": "Operations Consultant",
            "location": "Remote",
            "start_date": "2019",
            "end_date": "Present",
            "is_current": True,
            "description": "Helps teams improve delivery systems, internal workflows, and operating clarity across service businesses.",
        },
        "projects": [
            {
                "name": "Client Operations Playbook",
                "description": "Example project showing process mapping, documentation, and structured improvement recommendations.",
            }
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
                url="",
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

        existing_emails = {user.email for user in existing_users}
        created = 0
        for payload in _EXAMPLE_PROFILES:
            if payload["email"] in existing_emails:
                continue
            _create_example_profile(db, payload)
            created += 1

        db.commit()
        print(f"Created {created} example profiles.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_example_profiles(purge="--purge" in sys.argv[1:])
