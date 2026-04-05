"""
Analytics service — record events and compute summary statistics.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.models.analytics import AnalyticsEvent, ProfileView
from app.models.profile import Profile
from app.schemas.analytics import TrackEventRequest, AnalyticsSummary
from app.utils.validators import hash_visitor


def record_event(
    profile: Profile,
    event: TrackEventRequest,
    ip: str,
    user_agent: str,
    db: Session,
    qr_id: str | None = None,
) -> AnalyticsEvent | None:
    """Persist a single analytics event. IP is anonymised before storage."""
    visitor_hash = hash_visitor(ip, user_agent)

    # Dedupe logic: Don't record same event from same visitor within 5 minutes
    five_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    existing = db.query(AnalyticsEvent).filter(
        and_(
            AnalyticsEvent.profile_id == profile.id,
            AnalyticsEvent.visitor_hash == visitor_hash,
            AnalyticsEvent.event_type == event.event_type,
            AnalyticsEvent.created_at >= five_mins_ago
        )
    ).first()

    if existing:
        return None

    record = AnalyticsEvent(
        profile_id=profile.id,
        event_type=event.event_type,
        source=event.source,
        qr_id=qr_id,
        visitor_hash=visitor_hash,
        user_agent=user_agent[:500],
        link_target=event.link_target[:100],
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def record_page_view(
    profile: Profile,
    source: str,
    ip: str,
    user_agent: str,
    db: Session,
    qr_id: str | None = None,
) -> None:
    """Convenience wrapper for server-side page view recording."""
    from app.schemas.analytics import TrackEventRequest
    event = TrackEventRequest(event_type="page_view", source=source)
    record_event(profile, event, ip, user_agent, db, qr_id=qr_id)


def get_summary(profile_id: int, db: Session) -> AnalyticsSummary:
    """Return aggregated analytics for a given profile."""
    base = db.query(AnalyticsEvent).filter(AnalyticsEvent.profile_id == profile_id)

    total_views = base.filter(AnalyticsEvent.event_type == "page_view").count()

    # Unique visitors by distinct visitor_hash
    unique_visitors = (
        base.filter(AnalyticsEvent.event_type == "page_view")
        .with_entities(func.count(func.distinct(AnalyticsEvent.visitor_hash)))
        .scalar()
        or 0
    )

    qr_scans = base.filter(AnalyticsEvent.source == "qr").count()
    pdf_downloads = base.filter(AnalyticsEvent.event_type == "pdf_download").count()
    link_clicks = base.filter(AnalyticsEvent.event_type == "link_click").count()

    return AnalyticsSummary(
        total_views=total_views,
        unique_visitors=unique_visitors,
        qr_scans=qr_scans,
        pdf_downloads=pdf_downloads,
        link_clicks=link_clicks,
    )


def get_profile_view_overview(profile_id: int, db: Session, limit: int = 10) -> dict:
    """Return basic local profile view analytics for dashboard display."""
    base = db.query(ProfileView).filter(ProfileView.profile_id == profile_id)

    total_views = base.count()
    unique_visitors = (
        base.with_entities(
            func.count(
                func.distinct(
                    func.coalesce(func.nullif(ProfileView.viewer_ip, ""), ProfileView.visitor_hash)
                )
            )
        ).scalar()
        or 0
    )
    recent_visits = (
        base.order_by(ProfileView.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "total_views": total_views,
        "unique_visitors": unique_visitors,
        "recent_visits": recent_visits,
    }
