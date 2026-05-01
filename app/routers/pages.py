"""
Public content pages — educational, tool, explore, news, contact.
All routes are publicly accessible (no auth required).
"""
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, selectinload

from app.core.dependencies import get_db, get_current_user_optional, require_csrf
from app.core.templates import templates, flash
from app.utils.urls import external_base_url
from app.utils.validators import (
    normalize_optional_external_url,
    sanitize_article_html,
    sanitize_plain_text,
)

router = APIRouter(tags=["pages"])
logger = logging.getLogger(__name__)
_EXAMPLE_PROFILE_EMAIL_DOMAIN = "@example.invalid"
_DEMO_PROFILE_TARGET_COUNT = 2
_DEMO_PROFILES = [
    {
        "name": "Northstar Product Studio",
        "headline": "Sample Profile · Product Designer / Portfolio Creator",
        "location": "Remote",
        "skills": ["Product Design", "Case Studies", "Design Systems"],
        "summary": "Demo profile showing how a designer can present proof of work, polished case studies, and a clear professional narrative.",
        "label": "Sample Profile",
    },
    {
        "name": "Harbor Stack Labs",
        "headline": "Sample Profile · Software Developer / Project Builder",
        "location": "Remote",
        "skills": ["Python", "FastAPI", "Project Delivery"],
        "summary": "Demo profile focused on shipped projects, technical depth, and a cleaner alternative to a static resume or one-page link list.",
        "label": "Sample Profile",
    },
]


def _is_example_profile(profile) -> bool:
    user = getattr(profile, "user", None)
    email = (getattr(user, "email", "") or "").lower()
    username = (getattr(user, "username", "") or "").lower()
    headline = (getattr(profile, "headline", "") or "").lower()
    return (
        email.endswith(_EXAMPLE_PROFILE_EMAIL_DOMAIN)
        or username.startswith("sample_")
        or headline.startswith("example profile")
        or headline.startswith("sample profile")
    )


# ── What is DigiBioFi ─────────────────────────────────────────────────────────

@router.get("/what-is-digibiofi", response_class=HTMLResponse)
def what_is_page(
    request: Request,
    user=Depends(get_current_user_optional),
):
    return templates.TemplateResponse(
        "pages/what_is.html",
        {"request": request, "user": user, "base_url": external_base_url(request)},
    )


# ── Explore public profiles ───────────────────────────────────────────────────

@router.get("/explore", response_class=HTMLResponse)
def explore_page(
    request: Request,
    page: int = 1,
    q: str = "",
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    from app.models.profile import Profile
    from app.models.user import User

    per_page = 24
    offset = (page - 1) * per_page

    query = (
        db.query(Profile)
        .options(selectinload(Profile.skills), selectinload(Profile.user))
        .join(User, User.id == Profile.user_id)
        .filter(
            Profile.is_public.is_(True),
            User.is_active.is_(True),
        )
    )

    if q and q.strip():
        search = f"%{q.strip().lower()}%"
        from sqlalchemy import func
        query = query.filter(
            func.lower(Profile.full_name).like(search)
            | func.lower(Profile.headline).like(search)
        )

    total = query.count()
    profiles = (
        query.order_by(Profile.updated_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )
    example_profile_slugs = {profile.slug for profile in profiles if _is_example_profile(profile)}
    real_profiles = [profile for profile in profiles if profile.slug not in example_profile_slugs]
    demo_profiles = []
    if not q.strip() and len(example_profile_slugs) < _DEMO_PROFILE_TARGET_COUNT:
        missing_examples = max(0, _DEMO_PROFILE_TARGET_COUNT - len(example_profile_slugs))
        demo_profiles = list(_DEMO_PROFILES[:missing_examples])

    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(
        "pages/explore.html",
        {
            "request": request,
            "user": user,
            "profiles": profiles,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "q": q,
            "base_url": external_base_url(request),
            "example_profile_slugs": example_profile_slugs,
            "example_profile_count": len(example_profile_slugs),
            "demo_profiles": demo_profiles,
            "real_profile_count": len(real_profiles),
        },
    )


# ── Job Matcher tool ──────────────────────────────────────────────────────────

# Deterministic skill → career mapping
_SKILL_MAP: dict[str, list[str]] = {
    # Tech
    "python": ["Software Developer", "Data Analyst", "Backend Engineer", "Automation Engineer"],
    "javascript": ["Frontend Developer", "Full-Stack Developer", "Web Developer"],
    "typescript": ["Frontend Developer", "Full-Stack Developer", "React Developer"],
    "react": ["Frontend Developer", "UI Engineer", "Web Developer"],
    "java": ["Software Engineer", "Android Developer", "Backend Developer"],
    "sql": ["Data Analyst", "Database Administrator", "Business Intelligence Analyst"],
    "data": ["Data Analyst", "Data Scientist", "Business Analyst", "Research Analyst"],
    "machine learning": ["ML Engineer", "Data Scientist", "AI Researcher"],
    "ai": ["AI Engineer", "Machine Learning Engineer", "Data Scientist"],
    "cloud": ["Cloud Engineer", "DevOps Engineer", "Solutions Architect"],
    "aws": ["Cloud Engineer", "DevOps Engineer", "Cloud Architect"],
    "devops": ["DevOps Engineer", "Platform Engineer", "Site Reliability Engineer"],
    "security": ["Cybersecurity Analyst", "Penetration Tester", "Security Engineer"],
    "networking": ["Network Engineer", "Systems Administrator", "IT Support Specialist"],
    "mobile": ["Mobile Developer", "iOS Developer", "Android Developer"],
    # Design
    "design": ["UX/UI Designer", "Graphic Designer", "Product Designer"],
    "figma": ["UX/UI Designer", "Product Designer", "Web Designer"],
    "photoshop": ["Graphic Designer", "Photo Editor", "Digital Artist"],
    "illustrator": ["Graphic Designer", "Brand Designer", "Illustrator"],
    "ux": ["UX Designer", "Product Designer", "UX Researcher"],
    "ui": ["UI Designer", "Frontend Developer", "Web Designer"],
    "video": ["Video Editor", "Motion Designer", "Content Producer"],
    "photography": ["Photographer", "Photo Editor", "Visual Content Creator"],
    # Writing / Communication
    "writing": ["Content Writer", "Copywriter", "Technical Writer", "Editor"],
    "copywriting": ["Copywriter", "Marketing Specialist", "Content Strategist"],
    "editing": ["Editor", "Proofreader", "Content Manager"],
    "journalism": ["Journalist", "Reporter", "Content Writer", "Editor"],
    "communication": ["PR Specialist", "Communications Manager", "Content Strategist"],
    "social media": ["Social Media Manager", "Digital Marketing Specialist", "Content Creator"],
    "seo": ["SEO Specialist", "Content Strategist", "Digital Marketing Manager"],
    # Business / Management
    "management": ["Project Manager", "Operations Manager", "Team Lead", "General Manager"],
    "project management": ["Project Manager", "Program Manager", "Scrum Master"],
    "agile": ["Scrum Master", "Agile Coach", "Project Manager"],
    "leadership": ["Team Lead", "Manager", "Director", "Executive"],
    "strategy": ["Business Strategist", "Management Consultant", "Product Manager"],
    "sales": ["Sales Representative", "Account Executive", "Business Development Manager"],
    "marketing": ["Marketing Manager", "Digital Marketer", "Growth Hacker"],
    "consulting": ["Management Consultant", "Business Analyst", "Strategy Consultant"],
    "entrepreneurship": ["Startup Founder", "Business Development Manager", "CEO"],
    # Finance
    "finance": ["Financial Analyst", "Investment Analyst", "CFO", "Controller"],
    "accounting": ["Accountant", "CPA", "Auditor", "Financial Controller"],
    "investing": ["Investment Analyst", "Portfolio Manager", "Financial Advisor"],
    "economics": ["Economist", "Financial Analyst", "Policy Analyst"],
    # Education
    "teaching": ["Teacher", "Corporate Trainer", "Curriculum Developer", "Tutor"],
    "training": ["Corporate Trainer", "Learning & Development Specialist", "Coach"],
    "coaching": ["Life Coach", "Executive Coach", "Personal Trainer", "Business Coach"],
    # Healthcare
    "nursing": ["Registered Nurse", "Healthcare Administrator", "Nurse Practitioner"],
    "medicine": ["Physician", "Medical Researcher", "Healthcare Administrator"],
    "healthcare": ["Healthcare Administrator", "Medical Assistant", "Patient Coordinator"],
    "therapy": ["Therapist", "Counselor", "Social Worker"],
    "fitness": ["Personal Trainer", "Fitness Coach", "Health Coach", "Wellness Specialist"],
    "nutrition": ["Nutritionist", "Dietitian", "Health Coach"],
    # Trades / Creative
    "cooking": ["Chef", "Pastry Chef", "Catering Manager", "Food Blogger"],
    "music": ["Music Producer", "Session Musician", "Music Teacher", "Sound Engineer"],
    "art": ["Visual Artist", "Art Director", "Illustrator", "Gallery Manager"],
    "architecture": ["Architect", "Interior Designer", "Urban Planner"],
    "engineering": ["Civil Engineer", "Mechanical Engineer", "Structural Engineer"],
    "real estate": ["Real Estate Agent", "Property Manager", "Real Estate Analyst"],
    "legal": ["Paralegal", "Legal Assistant", "Compliance Officer"],
    "research": ["Research Analyst", "Academic Researcher", "Market Researcher"],
    "customer service": ["Customer Success Manager", "Support Specialist", "Client Relations Manager"],
    "logistics": ["Logistics Coordinator", "Supply Chain Manager", "Operations Manager"],
    "hr": ["HR Specialist", "Talent Acquisition Manager", "People Operations Manager"],
    "recruiting": ["Talent Acquisition Specialist", "Recruiter", "HR Business Partner"],
    "language": ["Translator", "Interpreter", "Language Teacher", "Localization Specialist"],
    "event": ["Event Planner", "Event Coordinator", "Conference Manager"],
}

_FREELANCE_MAP: dict[str, list[str]] = {
    "python": ["Freelance Backend Developer", "Automation Consultant", "Python Tutoring"],
    "javascript": ["Freelance Web Developer", "React Consultant"],
    "design": ["Freelance Graphic Designer", "Brand Identity Consultant", "Logo Design"],
    "writing": ["Freelance Writer", "Ghost Writer", "Blog Content Creator"],
    "copywriting": ["Freelance Copywriter", "Email Marketing Specialist"],
    "seo": ["Freelance SEO Consultant", "Content Strategy Consultant"],
    "social media": ["Social Media Consultant", "Freelance Content Creator"],
    "video": ["Freelance Video Editor", "YouTube Content Creator"],
    "photography": ["Freelance Photographer", "Stock Photography"],
    "coaching": ["Online Coach", "Course Creator", "Consulting Practice"],
    "marketing": ["Freelance Marketing Consultant", "Growth Advisor"],
    "data": ["Freelance Data Analyst", "BI Consultant"],
    "teaching": ["Online Tutor", "Course Creator on Udemy/Skillshare"],
    "consulting": ["Independent Consultant", "Fractional Executive"],
    "music": ["Session Musician", "Online Music Lessons"],
    "fitness": ["Online Personal Trainer", "Fitness Coach on App/YouTube"],
    "cooking": ["Private Chef", "Food Blog / YouTube Channel"],
}


def _match_careers(skills: str, interests: str, traits: list[str]) -> dict:
    """Deterministic career matching — no external APIs."""
    all_text = f"{skills} {interests}".lower()
    words = [w.strip(".,;:!?") for w in all_text.split()]

    matched_careers: dict[str, int] = {}
    matched_freelance: dict[str, int] = {}

    # Direct keyword matches
    for keyword, careers in _SKILL_MAP.items():
        if keyword in all_text:
            for career in careers:
                matched_careers[career] = matched_careers.get(career, 0) + 3

    # Word-level partial matches
    for word in words:
        for keyword, careers in _SKILL_MAP.items():
            if len(word) >= 4 and (word in keyword or keyword in word):
                for career in careers:
                    matched_careers[career] = matched_careers.get(career, 0) + 1

    # Freelance paths
    for keyword, paths in _FREELANCE_MAP.items():
        if keyword in all_text:
            for path in paths:
                matched_freelance[path] = matched_freelance.get(path, 0) + 2

    # Trait-based boosts
    trait_boosts = {
        "creative": ["UX/UI Designer", "Graphic Designer", "Content Writer", "Copywriter", "Visual Artist"],
        "analytical": ["Data Analyst", "Financial Analyst", "Business Analyst", "Research Analyst"],
        "social": ["Sales Representative", "Account Executive", "PR Specialist", "Customer Success Manager"],
        "independent": ["Freelance Web Developer", "Independent Consultant", "Online Coach"],
        "organized": ["Project Manager", "Operations Manager", "Event Planner"],
        "technical": ["Software Engineer", "DevOps Engineer", "Data Scientist"],
        "leadership": ["Team Lead", "Manager", "Director", "Executive"],
        "empathetic": ["Therapist", "Counselor", "HR Specialist", "Customer Success Manager"],
    }

    for trait in traits:
        boost_careers = trait_boosts.get(trait.lower(), [])
        for career in boost_careers:
            matched_careers[career] = matched_careers.get(career, 0) + 2

    # Sort by score
    top_careers = sorted(matched_careers.items(), key=lambda x: x[1], reverse=True)[:8]
    top_freelance = sorted(matched_freelance.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "careers": [c[0] for c in top_careers],
        "freelance": [f[0] for f in top_freelance],
        "has_results": bool(top_careers),
    }


@router.get("/tools/job-matcher", response_class=HTMLResponse)
def job_matcher_page(
    request: Request,
    user=Depends(get_current_user_optional),
):
    return templates.TemplateResponse(
        "pages/job_matcher.html",
        {
            "request": request,
            "user": user,
            "results": None,
            "form": {},
            "base_url": external_base_url(request),
        },
    )


@router.post("/tools/job-matcher", response_class=HTMLResponse)
def job_matcher_submit(
    request: Request,
    skills: str = Form(default=""),
    interests: str = Form(default=""),
    traits: list[str] = Form(default=[]),
    location: str = Form(default=""),
    csrf_token: str = Depends(require_csrf),
    user=Depends(get_current_user_optional),
):
    skills = skills.strip()[:500]
    interests = interests.strip()[:500]
    location = location.strip()[:200]

    results = _match_careers(skills, interests, traits)
    results["location"] = location

    form = {
        "skills": skills,
        "interests": interests,
        "traits": traits,
        "location": location,
    }

    return templates.TemplateResponse(
        "pages/job_matcher.html",
        {
            "request": request,
            "user": user,
            "results": results,
            "form": form,
            "base_url": external_base_url(request),
        },
    )


# ── News ──────────────────────────────────────────────────────────────────────

# Curated articles — real external links to authoritative career resources.
# Each entry links to a stable, publicly accessible page.  No fake content.
_CURATED_ARTICLES = [
    {
        "title": "Personal Branding Articles from Harvard Business Review",
        "summary": "A curated HBR search page covering personal branding, professional visibility, and how to present your work with more credibility.",
        "category": "Personal Branding",
        "read_time": "6 min",
        "url": "https://hbr.org/search?term=personal%20brand",
        "source": "Harvard Business Review",
    },
    {
        "title": "Remote Job Search on LinkedIn Jobs",
        "summary": "A live LinkedIn Jobs search surface for remote roles, useful for monitoring demand and refining how you position your profile for hiring teams.",
        "category": "Career Strategy",
        "read_time": "8 min",
        "url": "https://www.linkedin.com/jobs/search?keywords=remote",
        "source": "LinkedIn Jobs",
    },
    {
        "title": "LinkedIn's Workforce Confidence Index",
        "summary": "LinkedIn's ongoing research into workforce trends, confidence levels, and what professionals are doing to stay competitive.",
        "category": "Skills & Growth",
        "read_time": "5 min",
        "url": "https://www.linkedin.com/pulse/topics/workforce-confidence/",
        "source": "LinkedIn",
    },
    {
        "title": "Upwork Business and Freelancer Resources",
        "summary": "A practical collection of guides on pricing, freelancing, proposals, client communication, and building a sustainable independent practice.",
        "category": "Freelancing",
        "read_time": "10 min",
        "url": "https://www.upwork.com/resources",
        "source": "Upwork",
    },
    {
        "title": "Resume Tips from Coursera",
        "summary": "Coursera's resume guidance covers structure, clarity, and how to present measurable results in a way that supports stronger applications.",
        "category": "Resume Tips",
        "read_time": "7 min",
        "url": "https://www.coursera.org/articles/resume-tips",
        "source": "Coursera",
    },
    {
        "title": "The Muse on Interviewing",
        "summary": "A practical set of interview guides and coaching articles covering preparation, answers, follow-up, and decision making.",
        "category": "Career Strategy",
        "read_time": "6 min",
        "url": "https://www.themuse.com/advice/interviewing",
        "source": "The Muse",
    },
    {
        "title": "Using AI Responsibly in Your Job Search",
        "summary": "MIT Technology Review explores the benefits and risks of AI-assisted job applications, and how to maintain authenticity.",
        "category": "Technology",
        "read_time": "5 min",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/",
        "source": "MIT Technology Review",
    },
    {
        "title": "Glassdoor Career and Workplace Blog",
        "summary": "Glassdoor's workplace and career coverage includes salary context, interviewing advice, and practical job-search commentary.",
        "category": "Job Search",
        "read_time": "6 min",
        "url": "https://www.glassdoor.com/blog/",
        "source": "Glassdoor",
    },
    {
        "title": "Building a Portfolio That Gets You Hired",
        "summary": "freeCodeCamp's guide to creating an effective developer or creative portfolio that demonstrates real skills and projects.",
        "category": "Personal Branding",
        "read_time": "8 min",
        "url": "https://www.freecodecamp.org/news/how-to-build-a-developer-portfolio-website/",
        "source": "freeCodeCamp",
    },
    {
        "title": "Career Development Articles from Coursera",
        "summary": "Coursera's career development hub covers skills growth, personal branding, and practical next steps for job seekers and career changers.",
        "category": "Skills & Growth",
        "read_time": "7 min",
        "url": "https://www.coursera.org/articles/career-development",
        "source": "Coursera",
    },
    {
        "title": "Codecademy Career and Learning Guides",
        "summary": "Codecademy's resource library offers practical reading on technical growth, developer positioning, and portfolio-building habits.",
        "category": "Skills & Growth",
        "read_time": "6 min",
        "url": "https://www.codecademy.com/resources/blog/",
        "source": "Codecademy",
    },
]


@router.get("/news", response_class=HTMLResponse)
def news_page(
    request: Request,
    category: str = "",
    user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    from app.models.article import Article

    article_query = (
        db.query(Article)
        .filter(Article.is_published.is_(True))
        .order_by(Article.created_at.desc())
    )
    if category:
        article_query = article_query.filter(Article.category == category)

    db_articles = article_query.all()

    if db_articles:
        for article in db_articles:
            article.hero_image = normalize_optional_external_url(article.hero_image)
        # Show admin-created content
        categories = sorted(set(a.category for a in db_articles if a.category))
        return templates.TemplateResponse(
            "pages/news.html",
            {
                "request": request,
                "user": user,
                "articles": db_articles,
                "categories": categories,
                "selected_category": category,
                "source": "db",
                "base_url": external_base_url(request),
            },
        )

    # Fallback: curated external articles (real, authoritative sources)
    articles = _CURATED_ARTICLES
    if category:
        articles = [a for a in articles if a["category"] == category]
    categories = sorted(set(a["category"] for a in _CURATED_ARTICLES))

    return templates.TemplateResponse(
        "pages/news.html",
        {
            "request": request,
            "user": user,
            "articles": articles,
            "categories": categories,
            "selected_category": category,
            "source": "curated",
            "base_url": external_base_url(request),
        },
    )


@router.get("/news/{slug}", response_class=HTMLResponse)
@router.get("/articles/{slug}", response_class=HTMLResponse)
def article_page(
    slug: str,
    request: Request,
    user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    from app.models.article import Article

    article = (
        db.query(Article)
        .filter(Article.slug == slug, Article.is_published.is_(True))
        .first()
    )
    if not article:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Article not found")

    article.content_html = sanitize_article_html(article.content_html)
    article.hero_image = normalize_optional_external_url(article.hero_image)
    article.video_url = normalize_optional_external_url(article.video_url)

    return templates.TemplateResponse(
        "pages/article.html",
        {
            "request": request,
            "user": user,
            "article": article,
            "base_url": external_base_url(request),
        },
    )


# ── Contact ───────────────────────────────────────────────────────────────────

@router.get("/contact", response_class=HTMLResponse)
def contact_page(
    request: Request,
    user=Depends(get_current_user_optional),
):
    return templates.TemplateResponse(
        "pages/contact.html",
        {"request": request, "user": user, "submitted": False, "base_url": external_base_url(request)},
    )


@router.post("/contact", response_class=HTMLResponse)
def contact_submit(
    request: Request,
    name: str = Form(default=""),
    email: str = Form(default=""),
    subject: str = Form(default=""),
    message: str = Form(default=""),
    csrf_token: str = Depends(require_csrf),
    user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    name = sanitize_plain_text(name)[:200]
    email = sanitize_plain_text(email)[:255]
    subject = sanitize_plain_text(subject)[:300]
    message = sanitize_plain_text(message)[:5000]

    # Basic validation
    errors: dict[str, str] = {}
    if not name:
        errors["name"] = "Name is required."
    if not email or "@" not in email:
        errors["email"] = "A valid email is required."
    if not subject:
        errors["subject"] = "Please select a subject."
    if not message:
        errors["message"] = "Message cannot be empty."

    if errors:
        return templates.TemplateResponse(
            "pages/contact.html",
            {
                "request": request,
                "user": user,
                "submitted": False,
                "errors": errors,
                "form": {"name": name, "email": email, "subject": subject, "message": message},
                "base_url": external_base_url(request),
            },
            status_code=422,
        )

    try:
        from app.models.message import ContactMessage

        msg = ContactMessage(
            sender_name=name,
            sender_email=email,
            subject=subject,
            body=message,
            status="unread",
            user_id=user.id if user else None,
            source="internal" if user else "external",
        )
        db.add(msg)
        db.commit()
        logger.info("Contact message saved id=%s source=%s", msg.id, msg.source)
    except Exception:
        db.rollback()
        logger.exception("Failed to save contact message")
        flash(request, "An error occurred. Please try again later.", "error")
        return templates.TemplateResponse(
            "pages/contact.html",
            {
                "request": request,
                "user": user,
                "submitted": False,
                "base_url": external_base_url(request),
            },
            status_code=500,
        )

    return templates.TemplateResponse(
        "pages/contact.html",
        {"request": request, "user": user, "submitted": True, "base_url": external_base_url(request)},
    )
