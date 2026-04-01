from sqlalchemy import Column, String, DateTime, func
from app.db.database import Base


class StripeEvent(Base):
    __tablename__ = "stripe_events"

    event_id = Column(String(255), primary_key=True, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    def __repr__(self):
        return f"<StripeEvent event_id={self.event_id}>"
