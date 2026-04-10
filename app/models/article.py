"""
Article model — admin-authored content for the /news section.

status values:
  draft     — not visible to the public
  published — visible at /news/{slug}
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), unique=True, nullable=False, index=True)

    content_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    category: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    tags: Mapped[str] = mapped_column(String(300), nullable=False, default="")

    hero_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    author_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    author: Mapped["User"] = relationship("User", foreign_keys=[author_id])  # type: ignore[name-defined]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Article id={self.id} slug={self.slug!r} published={self.is_published}>"
