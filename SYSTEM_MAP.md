# SYSTEM_MAP.md — DigiBioFi Full System Understanding

**Generated**: Phase 0 — Pre-integration analysis
**Team consensus**: All roles agree on accuracy.

---

## 1. Architecture Summary

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI 0.111.1 (Python 3.11+) |
| Templates | Jinja2 (server-side rendered HTML) |
| ORM | SQLAlchemy 2.0.31 |
| DB (dev) | SQLite |
| DB (prod) | PostgreSQL 17 (via Docker Compose) |
| Migrations | Alembic |
| Auth | JWT (python-jose) + cookie-based sessions |
| Passwords | bcrypt via passlib |
| CSRF | Double-submit cookie pattern |
| Payments | Stripe (subscriptions + webhooks) |
| Ads | Google AdSense (configurable slots) |
| Email | stdlib `smtplib` (SMTP/STARTTLS) |
| QR Codes | qrcode + pypng |
| Deployment | Docker + docker-compose |

## 2. Backend Structure

```
app/
├── main.py              # App factory, middleware, lifespan, webhook, error handlers
├── core/
│   ├── config.py        # Pydantic Settings (reads .env)
│   ├── dependencies.py  # FastAPI DI: DB session, auth, CSRF, admin guard
│   ├── owner.py         # Owner (admin bootstrap) access logic
│   ├── permissions.py   # Tier-based permission checks
│   ├── security.py      # Password hashing, JWT, cookies, CSRF
│   └── templates.py     # Jinja2 engine + flash messages
├── db/
│   ├── database.py      # SQLAlchemy engine + session factory
│   └── schema.py        # Schema migration checks
├── models/
│   ├── user.py          # User model (auth identity, role, tier)
│   ├── profile.py       # Profile + Experience/Education/Skill/Project/etc.
│   ├── analytics.py     # AnalyticsEvent model
│   ├── article.py       # News articles (admin-authored)
│   ├── message.py       # Contact form messages
│   └── stripe.py        # StripeEvent (webhook idempotency)
├── routers/
│   ├── auth.py          # Register, login, logout, verify-email, forgot/reset-password
│   ├── dashboard.py     # Authenticated user: profile edit, experience, skills, projects, QR, upgrade
│   ├── public.py        # Public profile view, analytics tracking, QR/resume download
│   ├── admin.py         # Admin panel: users, messages, articles
│   ├── billing.py       # Stripe checkout session, billing portal
│   ├── legal.py         # Privacy, terms pages
│   └── pages.py         # Explore, news, contact, job-matcher, what-is-digibiofi
├── schemas/             # Pydantic request/response schemas
├── services/
│   ├── auth_service.py      # Registration, authentication, token creation/verification
│   ├── email_service.py     # SMTP email delivery (verification, password reset)
│   ├── stripe_service.py    # Stripe SDK wrappers
│   ├── profile_service.py   # Profile CRUD
│   ├── analytics_service.py # Analytics recording + summaries
│   ├── qr_service.py        # QR code generation
│   ├── file_service.py      # File upload handling
│   ├── storage.py           # File storage abstraction
│   └── user_service.py      # User deletion + asset cleanup
├── utils/
│   ├── slug.py          # URL slug generation
│   └── validators.py    # Input sanitization, pydantic error formatting
├── static/              # CSS, JS, images, robots.txt
└── templates/           # Jinja2 HTML templates
```

## 3. Email System (CRITICAL for this task)

### Current Implementation
- **File**: `app/services/email_service.py`
- **Library**: Python stdlib `smtplib` (no external email SDK)
- **Transport**: SMTP with STARTTLS (port 587) or SMTP_SSL (port 465)
- **Guard**: `is_email_configured()` checks SMTP host/user/password are set

### Email Entry Points
1. **Registration** (`routers/auth.py:103-115`) → `send_verification_email()`
2. **Resend verification** (`routers/auth.py:440-446`) → `send_verification_email()`
3. **Forgot password** (`routers/auth.py:285-288`) → `send_password_reset_email()`

### Current .env Email Config
```
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=<sendgrid_username_here>        ← WRONG: should be "apikey"
SMTP_PASSWORD=<sendgrid_api_key_here>     ← CORRECT: SendGrid API key
EMAILS_FROM_EMAIL=noreply@digibiofi.com
EMAILS_FROM_NAME=DigiBioFi
SENDGRID_API_KEY=<sendgrid_api_key_here>  ← Unused by code
```

### CRITICAL BUG FOUND
**`SMTP_USER` is set to the SendGrid API key instead of the literal string `apikey`.**

SendGrid SMTP requires:
- `SMTP_USER=apikey` (the literal word)
- `SMTP_PASSWORD=<your_sendgrid_api_key>`

This means email delivery is currently BROKEN in production.

## 4. Billing System

### Tiers (confirmed correct — no "premium" tier anywhere in backend logic)
- **Free**: Default. Daily profile view limits. Ads shown.
- **Basic**: Portfolio access. No ads. No analytics.
- **Elite**: All Basic + analytics + elite customization features. No ads.

### Stripe Integration
- Checkout session creation → webhook-driven tier activation
- Webhook signature verification (mandatory)
- Event idempotency via `StripeEvent` table
- Customer portal for subscription management
- Owner account bypasses all billing (always elite admin)

### Price IDs
- `STRIPE_PRICE_BASIC` → basic tier
- `STRIPE_PRICE_ELITE` → elite tier

## 5. Auth + Verification Flow

1. User registers → account created with `is_verified=False`
2. Verification email sent (if SMTP configured)
3. User clicks link → `verify_email_token()` sets `is_verified=True`
4. Unverified users redirected to `/verify-email/pending` for all protected routes
5. Password reset: signed token via `itsdangerous`, emailed to user
6. JWT stored in httponly cookie, CSRF via double-submit cookie

## 6. Risk Areas

| Risk | Severity | Location |
|------|----------|----------|
| SMTP_USER misconfigured (API key instead of "apikey") | **CRITICAL** | `.env` line 53 |
| `.env.example` contains REAL production secrets | **CRITICAL** | `.env.example` |
| SENDGRID_API_KEY in .env is unused by code | LOW | `.env` line 57 |
| No `.gitignore` check performed (secrets may be in git) | HIGH | Repository |

## 7. Integration Constraints

- Email service uses **stdlib smtplib only** — no SendGrid SDK needed
- SMTP transport code is already correct for SendGrid (STARTTLS on 587)
- **Only config values need to change** — no code changes needed for email delivery
- All email function signatures must remain unchanged
- Template files are not affected by SMTP config changes
