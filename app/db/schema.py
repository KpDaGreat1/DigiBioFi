from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.core.config import settings

REQUIRED_TABLES = {
    "analytics_events",
    "articles",
    "awards",
    "certifications",
    "contact_messages",
    "custom_sections",
    "educations",
    "experiences",
    "profile_views",
    "profiles",
    "projects",
    "qr_codes",
    "skills",
    "stripe_events",
    "users",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    root = _project_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def get_expected_schema_revision() -> str:
    script = ScriptDirectory.from_config(_alembic_config())
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(
            f"Expected exactly one Alembic head revision, found {len(heads)}."
        )
    return heads[0]


def assert_schema_ready(engine: Engine) -> None:
    expected_revision = get_expected_schema_revision()

    with engine.connect() as connection:
        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())
        missing_tables = sorted(REQUIRED_TABLES - existing_tables)
        if missing_tables:
            raise RuntimeError(
                "Database schema is incomplete. Missing tables: "
                + ", ".join(missing_tables)
                + ". Run `alembic upgrade head` before starting the app."
            )

        current_revision = MigrationContext.configure(connection).get_current_revision()

    if current_revision != expected_revision:
        raise RuntimeError(
            "Database schema revision mismatch. "
            f"Current revision: {current_revision!r}, expected: {expected_revision!r}. "
            "Run `alembic upgrade head` before starting the app."
        )
