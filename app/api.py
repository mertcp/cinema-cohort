"""Cinema cohort API."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.campaign import campaign_suggestions, draft
from app.cost_db import SessionMarketing, SessionOther
from app.costs import (
    build_cost_table,
    create_cost_stores,
    read_segment_marketing,
    seed_cost_stores_if_empty,
    upsert_other_monthly,
    upsert_segment_marketing,
    future_month_keys,
)
from app.db import create_tables, get_session
from app.models import CampaignDraft, Customer, Segment, Theatre, Visit
from app.seed import seed
from app.segments import assign_segment, circuit_return_rate, segment_stats, table_label_for_slug, target_profile

app = FastAPI(title="Cinema cohort demo", version="0.1.0")

_NO_STORE = "no-cache, no-store, must-revalidate"


@app.middleware("http")
async def api_no_cache(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith(("/segments", "/theatres", "/customers", "/campaigns", "/costs")):
        response.headers["Cache-Control"] = _NO_STORE
    return response


def session_scope():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


@app.on_event("startup")
def startup():
    create_tables()
    create_cost_stores()
    session = get_session()
    try:
        if session.query(Theatre).count() == 0:
            seed(session)
        seed_cost_stores_if_empty(session)
    finally:
        session.close()


def _segment_row(segment: Segment) -> dict:
    return {
        "id": segment.id,
        "slug": segment.slug,
        "label": segment.label,
        "short_label": table_label_for_slug(segment.slug),
        "return_rate": segment.return_rate,
        "visits_per_year": segment.visits_per_year,
        "top_genre": segment.top_genre,
        "peak_month": segment.peak_month,
        "member_count": segment.member_count,
        "formula": "return_rate = share of members with a repeat visit within 90 days",
        "target_group": segment.label,
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


class MarketingBudgetIn(BaseModel):
    monthly_spend: int
    active_months: list[int]


class OtherCostIn(BaseModel):
    amount_gbp: int


def _marketing_budget_fields(session: Session, segment: Segment) -> dict:
    session_mkt = SessionMarketing()
    try:
        return {"marketing_budget": read_segment_marketing(session, session_mkt, segment)}
    finally:
        session_mkt.close()


@app.get("/")
def home():
    return FileResponse(
        Path(__file__).resolve().parent / "dashboard.html",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


def _segment_marketing(segment: Segment, **stats) -> dict:
    """Slug-based profile and ideas; safe on list endpoint without loading visits."""
    return {
        "target_profile": target_profile(segment, **stats),
        "campaign_suggestions": campaign_suggestions(segment),
    }


def _resolve_theatre(session: Session, theatre_id: Optional[int]) -> Optional[Theatre]:
    if theatre_id is None:
        return None
    theatre = session.get(Theatre, theatre_id)
    if theatre is None:
        raise HTTPException(status_code=404, detail="Theatre not found")
    return theatre


def _customer_ids_at_theatre(session: Session, theatre_id: int) -> set[int]:
    """Customers whose home site is this theatre (partition of 200, no double-count)."""
    rows = session.query(Customer.id).filter(Customer.home_theatre_id == theatre_id).all()
    return {row[0] for row in rows}


def _members_for_segment(
    session: Session, segment: Segment, theatre_id: Optional[int], load_visits: bool = False
) -> list[Customer]:
    query = session.query(Customer).filter(Customer.segment_id == segment.id)
    if load_visits:
        query = query.options(joinedload(Customer.visits))
    members = query.all()
    if theatre_id is None:
        return members
    allowed = _customer_ids_at_theatre(session, theatre_id)
    return [customer for customer in members if customer.id in allowed]


def _segment_row_computed(
    session: Session, segment: Segment, theatre_id: Optional[int], today: date
) -> dict:
    members = _members_for_segment(session, segment, theatre_id)
    row = _segment_row(segment)
    if theatre_id is None:
        return row
    rr, vpy, top_g, peak_m = segment_stats(members, today)
    row["return_rate"] = rr
    row["visits_per_year"] = vpy
    row["top_genre"] = top_g
    row["peak_month"] = peak_m
    row["member_count"] = len(members)
    return row


def _visit_mix(members: list[Customer], theatre_id: Optional[int]) -> tuple[dict, dict]:
    genres: dict = {}
    months: dict = {}
    for customer in members:
        for visit in customer.visits:
            if theatre_id is not None and visit.theatre_id != theatre_id:
                continue
            genres[visit.genre] = genres.get(visit.genre, 0) + 1
            months[visit.visited_on.month] = months.get(visit.visited_on.month, 0) + 1
    return genres, months


@app.get("/customers/map")
def customers_map(
    session: Session = Depends(session_scope),
    theatre_id: Optional[int] = Query(None),
):
    _resolve_theatre(session, theatre_id)
    allowed = _customer_ids_at_theatre(session, theatre_id) if theatre_id else None
    rows = (
        session.query(Customer)
        .options(joinedload(Customer.segment))
        .order_by(Customer.id)
        .all()
    )
    points = []
    for customer in rows:
        if allowed is not None and customer.id not in allowed:
            continue
        seg = customer.segment
        points.append(
            {
                "code": customer.code,
                "borough": customer.borough,
                "postcode": customer.postcode,
                "lat": customer.lat,
                "lng": customer.lng,
                "segment_id": customer.segment_id,
                "segment_slug": seg.slug if seg else None,
                "segment_label": seg.label if seg else None,
            }
        )
    payload = {"count": len(points), "city": "London", "points": points}
    if theatre_id is not None:
        theatre = session.get(Theatre, theatre_id)
        payload["theatre_id"] = theatre_id
        payload["theatre_name"] = theatre.name if theatre else None
    return payload


@app.get("/costs/table")
def costs_table(
    session: Session = Depends(session_scope),
    mode: str = Query("all"),
    theatre_id: Optional[int] = Query(None),
):
    if mode not in ("all", "compare", "site"):
        raise HTTPException(status_code=400, detail="mode must be all, compare, or site")
    if mode == "site":
        if theatre_id is None:
            raise HTTPException(status_code=400, detail="theatre_id required for site mode")
        _resolve_theatre(session, theatre_id)
    try:
        return build_cost_table(session, mode, theatre_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/costs/marketing/{segment_id}")
def patch_marketing_budget(
    segment_id: int,
    incoming: MarketingBudgetIn,
    session: Session = Depends(session_scope),
):
    segment = session.get(Segment, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    session_mkt = SessionMarketing()
    try:
        upsert_segment_marketing(
            session_mkt,
            segment_id,
            incoming.monthly_spend,
            incoming.active_months,
        )
        budget = read_segment_marketing(session, session_mkt, segment)
    finally:
        session_mkt.close()
    return {"ok": True, "marketing_budget": budget}


@app.patch("/costs/other/{theatre_id}")
def patch_other_cost(
    theatre_id: int,
    incoming: OtherCostIn,
    session: Session = Depends(session_scope),
):
    _resolve_theatre(session, theatre_id)
    period_keys = [m["key"] for m in future_month_keys(12)]
    session_other = SessionOther()
    try:
        upsert_other_monthly(session_other, theatre_id, period_keys, incoming.amount_gbp)
    finally:
        session_other.close()
    return {"ok": True, "theatre_id": theatre_id, "amount_gbp": incoming.amount_gbp}


@app.get("/theatres/map")
def theatres_map(session: Session = Depends(session_scope)):
    rows = session.query(Theatre).order_by(Theatre.id).all()
    sites = [
        {
            "id": t.id,
            "name": t.name,
            "borough": t.borough,
            "address": t.address,
            "postcode": t.postcode,
            "city": t.city,
            "lat": t.lat,
            "lng": t.lng,
            "screen_count": t.screen_count,
            "seat_capacity": t.seat_capacity,
        }
        for t in rows
    ]
    return {"count": len(sites), "city": "London", "theatres": sites}


@app.get("/segments")
def list_segments(
    session: Session = Depends(session_scope),
    theatre_id: Optional[int] = Query(None),
):
    _resolve_theatre(session, theatre_id)
    today = date.today()
    segments = session.query(Segment).all()
    rows = []
    for s in segments:
        row = _segment_row_computed(session, s, theatre_id, today)
        stats = {}
        if theatre_id is not None:
            members = _members_for_segment(session, s, theatre_id)
            stats = {
                "return_rate": row["return_rate"],
                "visits_per_year": row["visits_per_year"],
                "top_genre": row["top_genre"],
                "peak_month": row["peak_month"],
                "members": row["member_count"],
            }
        row.update(_segment_marketing(s, **stats))
        row.update(_marketing_budget_fields(session, s))
        rows.append(row)
    rows.sort(key=lambda r: (r["return_rate"], -r["member_count"]))
    if theatre_id is None:
        circuit_rr = circuit_return_rate(segments)
    else:
        total = sum(r["member_count"] for r in rows)
        circuit_rr = (
            round(sum(r["return_rate"] * r["member_count"] for r in rows) / total, 3) if total else 0.0
        )
    theatre = session.get(Theatre, theatre_id) if theatre_id else None
    segment_total = sum(r["member_count"] for r in rows)
    if theatre_id is None:
        customers_n = session.query(Customer).count()
    else:
        customers_n = segment_total
    return {
        "circuit_return_rate": circuit_rr,
        "theatre_count": session.query(Theatre).count(),
        "theatre_id": theatre_id,
        "theatre_name": theatre.name if theatre else None,
        "customer_count": customers_n,
        "segments": rows,
    }


@app.get("/segments/{segment_id}")
def segment_detail(
    segment_id: int,
    session: Session = Depends(session_scope),
    theatre_id: Optional[int] = Query(None),
):
    _resolve_theatre(session, theatre_id)
    today = date.today()
    segment = _one_segment(session, segment_id)
    body = _segment_row_computed(session, segment, theatre_id, today)
    members = _members_for_segment(session, segment, theatre_id, load_visits=True)
    genres, months = _visit_mix(members, theatre_id)
    stats = {}
    if theatre_id is not None:
        stats = {
            "return_rate": body["return_rate"],
            "visits_per_year": body["visits_per_year"],
            "top_genre": body["top_genre"],
            "peak_month": body["peak_month"],
            "members": body["member_count"],
        }
    body.update(_segment_marketing(segment, **stats))
    body.update(_marketing_budget_fields(session, segment))
    body["genre_counts"] = genres
    body["month_counts"] = months
    if theatre_id is not None:
        body["theatre_id"] = theatre_id
        theatre = session.get(Theatre, theatre_id)
        body["theatre_name"] = theatre.name if theatre else None
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


@app.get("/segments/{segment_id}/evidence")
def segment_evidence(
    segment_id: int,
    session: Session = Depends(session_scope),
    theatre_id: Optional[int] = Query(None),
):
    _resolve_theatre(session, theatre_id)
    today = date.today()
    segment = _one_segment(session, segment_id)
    body = _segment_row_computed(session, segment, theatre_id, today)
    stats = {}
    if theatre_id is not None:
        stats = {
            "return_rate": body["return_rate"],
            "visits_per_year": body["visits_per_year"],
            "top_genre": body["top_genre"],
            "peak_month": body["peak_month"],
            "members": body["member_count"],
        }
    campaign = segment.campaigns[-1] if segment.campaigns else None
    return {
        "segment": segment.label,
        "slug": segment.slug,
        "target_profile": target_profile(segment, **stats),
        "campaign_suggestions": campaign_suggestions(segment),
        "return_rate": body["return_rate"],
        "circuit_return_rate": circuit_return_rate(session.query(Segment).all()),
        "visits_per_year": body["visits_per_year"],
        "top_genre": body["top_genre"],
        "peak_month": body["peak_month"],
        "member_count": body["member_count"],
        "theatre_id": theatre_id,
        "campaign": None
        if campaign is None
        else {
            "action": campaign.edited_action or campaign.action,
            "channel": campaign.channel,
            "expected_lift": campaign.expected_lift,
            "status": campaign.status,
        },
    }


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
    slug = assign_segment(customer.visits, today, customer.age)
    segment = session.query(Segment).filter(Segment.slug == slug).first()
    if segment is None:
        segment = session.query(Segment).filter(Segment.slug == "age_adults").first()
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
