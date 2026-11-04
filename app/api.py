"""Cinema cohort API."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.campaign import draft
from app.db import create_tables, get_session
from app.models import CampaignDraft, Customer, Segment, Theatre, Visit
from app.seed import seed
from app.segments import assign_segment, segment_stats

app = FastAPI(title="Cinema cohort demo", version="0.1.0")


def session_scope():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


@app.on_event("startup")
def startup():
    create_tables()
    session = get_session()
    try:
        if session.query(Theatre).count() == 0:
            seed(session)
    finally:
        session.close()


def _segment_row(segment: Segment) -> dict:
    return {
        "id": segment.id,
        "slug": segment.slug,
        "label": segment.label,
        "return_rate": segment.return_rate,
        "visits_per_year": segment.visits_per_year,
        "top_genre": segment.top_genre,
        "peak_month": segment.peak_month,
        "member_count": segment.member_count,
        "formula": "return_rate = share of members with a repeat visit within 90 days",
    }


def _one_segment(session: Session, segment_id: int) -> Segment:
    segment = (
        session.query(Segment)
        .options(joinedload(Segment.customers).joinedload(Customer.visits), joinedload(Segment.campaigns))
        .filter(Segment.id == segment_id)
        .first()
    )
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    return segment


class VisitIn(BaseModel):
    customer_code: str
    theatre_id: int
    visited_on: date
    genre: str
    ticket_type: str = "standard"


class DecisionIn(BaseModel):
    status: str
    edited_action: Optional[str] = None


@app.get("/")
def home():
    return FileResponse(Path(__file__).resolve().parent / "dashboard.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/segments")
def list_segments(session: Session = Depends(session_scope)):
    segments = session.query(Segment).all()
    rows = [_segment_row(s) for s in segments]
    rows.sort(key=lambda r: (r["return_rate"], -r["member_count"]))
    return rows


@app.get("/segments/{segment_id}")
def segment_detail(segment_id: int, session: Session = Depends(session_scope)):
    segment = _one_segment(session, segment_id)
    body = _segment_row(segment)
    genres = {}
    months = {}
    for customer in segment.customers:
        for visit in customer.visits:
            genres[visit.genre] = genres.get(visit.genre, 0) + 1
            months[visit.visited_on.month] = months.get(visit.visited_on.month, 0) + 1
    body["genre_counts"] = genres
    body["month_counts"] = months
    body["campaigns"] = [
        {
            "id": c.id,
            "action": c.edited_action or c.action,
            "channel": c.channel,
            "expected_lift": c.expected_lift,
            "confidence": c.confidence,
            "status": c.status,
        }
        for c in segment.campaigns
    ]
    return body


@app.post("/visits")
def add_visit(incoming: VisitIn, session: Session = Depends(session_scope)):
    customer = session.query(Customer).filter(Customer.code == incoming.customer_code).first()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    theatre = session.get(Theatre, incoming.theatre_id)
    if theatre is None:
        raise HTTPException(status_code=404, detail="Theatre not found")
    session.add(
        Visit(
            customer=customer,
            theatre=theatre,
            visited_on=incoming.visited_on,
            genre=incoming.genre,
            ticket_type=incoming.ticket_type,
        )
    )
    session.flush()
    _refresh_customer_segment(session, customer, date.today())
    session.commit()
    return {"ok": True}


def _refresh_customer_segment(session, customer, today):
    slug = assign_segment(customer.visits, today)
    segment = session.query(Segment).filter(Segment.slug == slug).first()
    if segment is None:
        segment = session.query(Segment).filter(Segment.slug == "steady_mixed").first()
    customer.segment_id = segment.id if segment else None
    session.flush()
    if segment:
        members = session.query(Customer).filter(Customer.segment_id == segment.id).all()
        rr, vpy, top_g, peak_m = segment_stats(members, today)
        segment.return_rate = rr
        segment.visits_per_year = vpy
        segment.top_genre = top_g
        segment.peak_month = peak_m
        segment.member_count = len(members)


@app.post("/segments/{segment_id}/campaign")
def create_campaign(segment_id: int, session: Session = Depends(session_scope)):
    segment = _one_segment(session, segment_id)
    action, channel, lift, confidence = draft(segment)
    record = CampaignDraft(
        segment=segment,
        created_at=datetime.now(),
        action=action,
        channel=channel,
        expected_lift=lift,
        confidence=confidence,
        status="draft",
    )
    session.add(record)
    session.commit()
    return {
        "id": record.id,
        "action": record.action,
        "channel": record.channel,
        "expected_lift": record.expected_lift,
        "status": record.status,
    }


@app.post("/campaigns/{campaign_id}/decision")
def decide(campaign_id: int, incoming: DecisionIn, session: Session = Depends(session_scope)):
    if incoming.status not in ("accepted", "edited", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid status")
    record = session.get(CampaignDraft, campaign_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    record.status = incoming.status
    if incoming.status == "edited":
        if not incoming.edited_action:
            raise HTTPException(status_code=400, detail="edited_action required")
        record.edited_action = incoming.edited_action
    session.commit()
    return {"id": record.id, "status": record.status}


@app.post("/segments/refresh")
def refresh_all(session: Session = Depends(session_scope)):
    today = date.today()
    for segment in session.query(Segment).all():
        members = session.query(Customer).filter(Customer.segment_id == segment.id).all()
        rr, vpy, top_g, peak_m = segment_stats(members, today)
        segment.return_rate = rr
        segment.visits_per_year = vpy
        segment.top_genre = top_g
        segment.peak_month = peak_m
        segment.member_count = len(members)
    session.commit()
    return {"ok": True}
