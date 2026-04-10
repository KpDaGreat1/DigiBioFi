# DigiBioFi

**A modern digital resume & identity platform.**  
Build a professional profile page with a unique URL and QR code. Replace paper resumes with a live, mobile-first digital card.

---

## Features

- Authenticated user accounts (JWT via httponly cookies)
- Dashboard to build and manage your profile
- Public profile page at `/p/{slug}`
- Unique QR code per user (PNG download)
- Analytics: page views, QR scans, link clicks, PDF downloads
- Resume PDF upload and public download
- Digital card preview (NFC smart card ready)
- Admin panel for user management
- SQLite (dev) / PostgreSQL (prod)

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI |
| Database | SQLAlchemy 2, Alembic, SQLite/PostgreSQL |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Templates | Jinja2 + Tailwind CSS |
| QR Codes | qrcode + Pillow |
| Server | Uvicorn / Gunicorn |

---

## PyCharm Setup

1. Open the `digibiofi/` folder in PyCharm.
2. Go to **Settings → Project → Python Interpreter**.
3. Select **Add Interpreter → Existing** and point to `.venv/bin/python`.
4. Mark `app/` as a Sources Root: right-click → Mark Directory As → Sources Root.
5. Set run configuration:
   - Script: `run.py`
   - Working directory: project root

---

## Local Development

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum, set strong `SECRET_KEY` and `CSRF_SECRET_KEY`
```

### 3. Run migrations

```bash
.venv/bin/alembic upgrade head
```

### 4. Start the app

```bash
python run.py
# or
uvicorn app.main:app --reload
```

Visit: http://localhost:8000

### 4. Create admin user

```bash
python scripts/create_admin.py
```

---

## Database Migrations (Alembic)

### Initial setup (first time)

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

### After model changes

```bash
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

### Downgrade

```bash
alembic downgrade -1
```

> **Note:** The app now requires a migrated schema before startup in every non-test environment. Run `alembic upgrade head` before starting it.

---

## Production Deployment

### Prerequisites

- A server or PaaS (Render, Railway, VPS)
- PostgreSQL database
- Environment variables set (see `.env.example`)

### 1. Set environment variables

```
APP_ENV=production
DEBUG=false
SECRET_KEY=<strong-random-64-char-string>
BASE_URL=https://yourdomain.com
DATABASE_URL=postgresql://user:pass@host:5432/digibiofi
```

### 2. Run migrations

```bash
alembic upgrade head
```

### 3. Create admin

```bash
python scripts/create_admin.py
```

### 4. Start with Gunicorn

```bash
gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w 4 \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

### Render.com (one-click)

Create a **Web Service**, set:
- Build command: `pip install -r requirements.txt && alembic upgrade head`
- Start command: `gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 --bind 0.0.0.0:$PORT`
- Add all environment variables from `.env.example`

### Railway

Same commands. Add a PostgreSQL addon and set `DATABASE_URL` automatically.

---

## File Structure

```
digibiofi/
├── app/
│   ├── main.py                  # App factory, middleware, routers
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── security.py          # JWT + bcrypt
│   │   └── dependencies.py      # FastAPI DI: get_db, get_current_user
│   ├── db/
│   │   └── database.py          # Engine, SessionLocal, Base
│   ├── models/
│   │   ├── user.py              # User model
│   │   ├── profile.py           # Profile + all section models + QRCode
│   │   └── analytics.py         # AnalyticsEvent
│   ├── schemas/
│   │   ├── auth.py              # Register / Login schemas
│   │   ├── profile.py           # Profile + section schemas
│   │   └── analytics.py         # Event schemas
│   ├── services/
│   │   ├── auth_service.py      # Registration, authentication
│   │   ├── profile_service.py   # Profile + section CRUD
│   │   ├── qr_service.py        # QR generation + retrieval
│   │   ├── analytics_service.py # Event recording + summary
│   │   └── file_service.py      # Image + PDF upload
│   ├── routers/
│   │   ├── auth.py              # /register, /login, /logout
│   │   ├── dashboard.py         # /dashboard/*
│   │   ├── public.py            # /p/{slug}, /qr/download, /resume/download
│   │   └── admin.py             # /admin/*
│   ├── templates/               # Jinja2 HTML templates
│   ├── static/                  # CSS, JS
│   └── utils/
│       ├── slug.py              # Unique slug generation
│       └── validators.py        # File validation, input sanitization
├── alembic/
├── scripts/
│   └── create_admin.py
├── uploads/                     # Local file storage (gitignored)
├── requirements.txt
├── .env.example
├── alembic.ini
└── run.py
```

---

## Security Notes

- JWT stored in `httponly`, `SameSite=Lax` cookies
- Passwords hashed with bcrypt
- File uploads: MIME type validation + size limits
- User-supplied HTML sanitized with `bleach`
- No raw SQL — all queries via SQLAlchemy ORM
- In production: set `secure=True` on cookies (requires HTTPS)

---

## Roadmap

- [ ] NFC smart card provisioning
- [ ] Profile themes / color customization
- [ ] Cloud file storage (S3/Cloudinary)
- [ ] QR analytics heatmap
- [ ] Custom domain mapping
