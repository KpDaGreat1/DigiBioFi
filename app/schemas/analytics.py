"""
Pydantic schemas for analytics event ingestion.
"""
from pydantic import BaseModel
from typing import Literal


class TrackEventRequest(BaseModel):
    event_type: Literal["page_view", "qr_scan", "pdf_download", "link_click"]
    source: Literal["direct", "qr", "referral"] = "direct"
    link_target: str = ""


class AnalyticsSummary(BaseModel):
    total_views: int
    unique_visitors: int
    qr_scans: int
    pdf_downloads: int
    link_clicks: int
