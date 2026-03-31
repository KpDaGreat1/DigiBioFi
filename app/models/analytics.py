"""
Analytics event model — lightweight, append-only event log.

event_type values:
  page_view   — someone visited /p/{slug}
  qr_scan     — visitor arrived via ?src=qr
  pdf_download — resume PDF was downloaded
  link_click  — outbound social/contact link clicked (tracked client-side)

source values:
  direct  — no referrer / typed URL
  qr      — came from QR code
  referral — came from another site
"""
from datetime import datetime, timezone
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    event_type: Mapped[str] = mapped_column(String(50), nullable=False)   # see docstring
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="direct")
    qr_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Anonymised visitor fingerprint — SHA-256(ip + user_agent) first 16 chars
    visitor_hash: Mapped[str] = mapped_column(String(32), nullable=False, default="")

    # Stored only for aggregation; strip PII before production if required
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    # Link click target (social link clicked, e.g. "linkedin")
    link_target: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    profile: Mapped["Profile"] = relationship(  # type: ignore[name-defined]
        "Profile", back_populates="analytics_events"
    )
