"""
Database engine and session factory.

Uses SQLite for local development (DATABASE_URL starts with sqlite://)
and PostgreSQL for production. The switch is purely environment-driven.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────

_connect_args = {}
if settings.database_url.startswith("sqlite"):
    # SQLite requires check_same_thread=False when used with FastAPI's
    # thread-pool-based sync route handlers.
    _connect_args = {
        "check_same_thread": False,
        "timeout": 30,
    }

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=settings.debug,        # log SQL in dev; disable in prod
    pool_pre_ping=True,         # reconnect after idle periods
)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA busy_timeout = 30000")
        if ":memory:" not in settings.database_url:
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Base model ───────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """All SQLAlchemy models inherit from this base."""
    pass
