"""
Contact message model — stores messages submitted via the public contact form.

Status values:
  unread   — new message, not yet seen by admin
  read     — admin has viewed the message
  resolved — admin has resolved / closed the message

Source values:
  internal — submitted by a logged-in registered user
  external — submitted by an anonymous / unauthenticated visitor
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Sender info (from form — may not be a registered user)
    sender_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)

    # Linked registered user (null for anonymous / external senders)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]

    # Source distinguishes internal (registered) vs external (anonymous) senders
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="external", index=True)

    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Workflow status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unread", index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<ContactMessage id={self.id} source={self.source!r} status={self.status!r} subject={self.subject!r}>"

