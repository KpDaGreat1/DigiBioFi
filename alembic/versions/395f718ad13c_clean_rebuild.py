"""Bootstrap the current schema."""

from alembic import op
import sqlalchemy as sa

revision = "395f718ad13c"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stripe_events",
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        op.f("ix_stripe_events_event_id"),
        "stripe_events",
        ["event_id"],
        unique=True,
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("subscription_tier", sa.String(length=20), nullable=False),
        sa.Column("subscription_status", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=200), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("headline", sa.String(length=300), nullable=False),
        sa.Column("bio", sa.Text(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("website", sa.String(length=500), nullable=False),
        sa.Column("twitter", sa.String(length=500), nullable=False),
        sa.Column("github", sa.String(length=500), nullable=False),
        sa.Column("telegram", sa.String(length=500), nullable=False),
        sa.Column("profile_image", sa.String(length=500), nullable=False),
        sa.Column("resume_pdf", sa.String(length=500), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("recruiter_visibility", sa.Boolean(), nullable=False),
        sa.Column("freelance_availability", sa.Boolean(), nullable=False),
        sa.Column("profile_image_2", sa.String(length=500), nullable=False),
        sa.Column("profile_image_3", sa.String(length=500), nullable=False),
        sa.Column("custom_background_url", sa.String(length=500), nullable=False),
        sa.Column("custom_header_url", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_profiles_id"), "profiles", ["id"], unique=False)
    op.create_index(op.f("ix_profiles_slug"), "profiles", ["slug"], unique=True)

    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("qr_id", sa.UUID(), nullable=True),
        sa.Column("visitor_hash", sa.String(length=32), nullable=False),
        sa.Column("user_agent", sa.String(length=500), nullable=False),
        sa.Column("link_target", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_analytics_events_created_at"),
        "analytics_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_analytics_events_id"), "analytics_events", ["id"], unique=False)
    op.create_index(
        op.f("ix_analytics_events_profile_id"),
        "analytics_events",
        ["profile_id"],
        unique=False,
    )

    op.create_table(
        "awards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("issuer", sa.String(length=200), nullable=False),
        sa.Column("date", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_awards_id"), "awards", ["id"], unique=False)
    op.create_index(op.f("ix_awards_profile_id"), "awards", ["profile_id"], unique=False)

    op.create_table(
        "certifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("issuer", sa.String(length=200), nullable=False),
        sa.Column("date", sa.String(length=20), nullable=False),
        sa.Column("credential_id", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_certifications_id"), "certifications", ["id"], unique=False)
    op.create_index(
        op.f("ix_certifications_profile_id"),
        "certifications",
        ["profile_id"],
        unique=False,
    )

    op.create_table(
        "custom_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_custom_sections_id"), "custom_sections", ["id"], unique=False)
    op.create_index(
        op.f("ix_custom_sections_profile_id"),
        "custom_sections",
        ["profile_id"],
        unique=False,
    )

    op.create_table(
        "educations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("school", sa.String(length=200), nullable=False),
        sa.Column("degree", sa.String(length=200), nullable=False),
        sa.Column("field", sa.String(length=200), nullable=False),
        sa.Column("start_date", sa.String(length=20), nullable=False),
        sa.Column("end_date", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("certificate_url", sa.String(length=500), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_educations_id"), "educations", ["id"], unique=False)
    op.create_index(op.f("ix_educations_profile_id"), "educations", ["profile_id"], unique=False)

    op.create_table(
        "experiences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("start_date", sa.String(length=20), nullable=False),
        sa.Column("end_date", sa.String(length=20), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_experiences_id"), "experiences", ["id"], unique=False)
    op.create_index(
        op.f("ix_experiences_profile_id"),
        "experiences",
        ["profile_id"],
        unique=False,
    )

    op.create_table(
        "profile_views",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("visitor_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_profile_views_created_at"),
        "profile_views",
        ["created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_profile_views_id"), "profile_views", ["id"], unique=False)
    op.create_index(
        op.f("ix_profile_views_profile_id"),
        "profile_views",
        ["profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_profile_views_visitor_hash"),
        "profile_views",
        ["visitor_hash"],
        unique=False,
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_id"), "projects", ["id"], unique=False)
    op.create_index(op.f("ix_projects_profile_id"), "projects", ["profile_id"], unique=False)

    op.create_table(
        "qr_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("qr_id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.String(length=500), nullable=False),
        sa.Column("qr_url", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id"),
    )
    op.create_index(op.f("ix_qr_codes_id"), "qr_codes", ["id"], unique=False)
    op.create_index(op.f("ix_qr_codes_qr_id"), "qr_codes", ["qr_id"], unique=True)

    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_skills_id"), "skills", ["id"], unique=False)
    op.create_index(op.f("ix_skills_profile_id"), "skills", ["profile_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_skills_profile_id"), table_name="skills")
    op.drop_index(op.f("ix_skills_id"), table_name="skills")
    op.drop_table("skills")

    op.drop_index(op.f("ix_qr_codes_qr_id"), table_name="qr_codes")
    op.drop_index(op.f("ix_qr_codes_id"), table_name="qr_codes")
    op.drop_table("qr_codes")

    op.drop_index(op.f("ix_projects_profile_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_id"), table_name="projects")
    op.drop_table("projects")

    op.drop_index(op.f("ix_profile_views_visitor_hash"), table_name="profile_views")
    op.drop_index(op.f("ix_profile_views_profile_id"), table_name="profile_views")
    op.drop_index(op.f("ix_profile_views_id"), table_name="profile_views")
    op.drop_index(op.f("ix_profile_views_created_at"), table_name="profile_views")
    op.drop_table("profile_views")

    op.drop_index(op.f("ix_experiences_profile_id"), table_name="experiences")
    op.drop_index(op.f("ix_experiences_id"), table_name="experiences")
    op.drop_table("experiences")

    op.drop_index(op.f("ix_educations_profile_id"), table_name="educations")
    op.drop_index(op.f("ix_educations_id"), table_name="educations")
    op.drop_table("educations")

    op.drop_index(op.f("ix_custom_sections_profile_id"), table_name="custom_sections")
    op.drop_index(op.f("ix_custom_sections_id"), table_name="custom_sections")
    op.drop_table("custom_sections")

    op.drop_index(op.f("ix_certifications_profile_id"), table_name="certifications")
    op.drop_index(op.f("ix_certifications_id"), table_name="certifications")
    op.drop_table("certifications")

    op.drop_index(op.f("ix_awards_profile_id"), table_name="awards")
    op.drop_index(op.f("ix_awards_id"), table_name="awards")
    op.drop_table("awards")

    op.drop_index(op.f("ix_analytics_events_profile_id"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_id"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_created_at"), table_name="analytics_events")
    op.drop_table("analytics_events")

    op.drop_index(op.f("ix_profiles_slug"), table_name="profiles")
    op.drop_index(op.f("ix_profiles_id"), table_name="profiles")
    op.drop_table("profiles")

    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    op.drop_index(op.f("ix_stripe_events_event_id"), table_name="stripe_events")
    op.drop_table("stripe_events")
