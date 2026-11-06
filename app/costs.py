"""Load and aggregate monthly costs from five separate SQLite sources."""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.cost_db import (
    COST_SOURCE_PATHS,
    ENGINES,
    SessionMarketing,
    cost_store_sessions,
    marketing_session,
)
from app.cost_models import SegmentMarketingBudget, SiteMonthCost
from app.models import Customer, Segment, Theatre

PEAK_MONTHS = (7, 8, 11, 12)
MONTH_NAMES = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

DEFAULT_SPEND = {
    "family_moviegoing": 4800,
    "age_kids": 3600,
    "age_teens": 3200,
    "age_young_adults": 4200,
    "age_adults": 2800,
    "age_seniors": 1800,
}


def create_cost_stores():
    from app.cost_models import SegmentMarketingBudget, SiteMonthCost

    SegmentMarketingBudget.__table__.create(ENGINES["marketing"], checkfirst=True)
    for name in ("fnb", "staff", "utilities", "other"):
        SiteMonthCost.__table__.create(ENGINES[name], checkfirst=True)


def reset_cost_stores():
    from app.cost_models import SegmentMarketingBudget, SiteMonthCost

    SegmentMarketingBudget.__table__.drop(ENGINES["marketing"], checkfirst=True)
    for name in ("fnb", "staff", "utilities", "other"):
        SiteMonthCost.__table__.drop(ENGINES[name], checkfirst=True)
    create_cost_stores()


def _default_active_months(segment: Segment) -> list[int]:
    peak = segment.peak_month or 12
    months = {7, 8, 11, 12, 2, 4, 10, peak}
    if segment.slug in ("family_moviegoing", "age_kids"):
        months.update({2, 4, 10})
    return sorted(months)


def _parse_active_months(raw: str) -> list[int]:
    if not raw:
        return []
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
        except ValueError:
            continue
        if 1 <= n <= 12:
            out.add(n)
    return sorted(out)


def _format_active_months(months: list[int]) -> str:
    return ",".join(str(m) for m in sorted(set(months)))


def future_month_keys(count: int = 12, today: Optional[date] = None) -> list[dict]:
    start = (today or date.today()).replace(day=1)
    y, m = start.year, start.month
    out = []
    for i in range(count):
        mm = m + i
        yy = y + (mm - 1) // 12
        cm = (mm - 1) % 12 + 1
        out.append(
            {
                "key": "{0}-{1:02d}".format(yy, cm),
                "month": cm,
                "year": yy,
                "label": "{0} {1:02d}".format(MONTH_NAMES[cm - 1], yy % 100),
            }
        )
    return out


def _theatre_customer_counts(session: Session) -> dict[int, int]:
    rows = session.query(Customer.home_theatre_id).all()
    counts: dict[int, int] = {}
    for (tid,) in rows:
        if tid is None:
            continue
        counts[tid] = counts.get(tid, 0) + 1
    return counts


def theatre_share(counts: dict[int, int], theatre_id: int, theatre_count: int) -> float:
    total = sum(counts.values())
    if not total:
        return 1.0 / max(theatre_count, 1)
    return counts.get(theatre_id, 0) / total


def _extra_staff_cost(theatre: Theatre, month: int, customers: int) -> int:
    cap = theatre.seat_capacity or 1200
    density = customers / max(cap / 80, 1)
    base = cap * 0.012
    busy = month in PEAK_MONTHS
    extra = base * (0.28 + min(density, 2) * 0.12) if busy else base * 0.08
    return round(base + extra)


def _fnb_cost(customers: int, month: int) -> int:
    per = customers * 3.8
    if month in PEAK_MONTHS:
        per *= 1.22
    return round(per)


def _utilities_cost(theatre: Theatre) -> int:
    return round((theatre.screen_count or 8) * 420 + (theatre.seat_capacity or 1200) * 0.06)


def _other_default() -> int:
    return 1800


def marketing_budget_row(session_mkt: Session, segment_id: int) -> Optional[SegmentMarketingBudget]:
    return session_mkt.get(SegmentMarketingBudget, segment_id)


def read_segment_marketing(session: Session, session_mkt: Session, segment: Segment) -> dict:
    row = marketing_budget_row(session_mkt, segment.id)
    if row is None:
        return {
            "monthly_spend": DEFAULT_SPEND.get(segment.slug, 3000),
            "active_months": _default_active_months(segment),
        }
    return {
        "monthly_spend": row.monthly_spend_gbp,
        "active_months": _parse_active_months(row.active_months) or _default_active_months(segment),
    }


def upsert_segment_marketing(session_mkt: Session, segment_id: int, monthly_spend: int, active_months: list[int]):
    row = session_mkt.get(SegmentMarketingBudget, segment_id)
    if row is None:
        row = SegmentMarketingBudget(segment_id=segment_id)
        session_mkt.add(row)
    row.monthly_spend_gbp = int(monthly_spend)
    row.active_months = _format_active_months(active_months)
    session_mkt.commit()


def _load_ops_matrix(session_ops: Session, theatre_ids: list[int], period_keys: list[str]) -> dict[tuple[int, str], int]:
    rows = (
        session_ops.query(SiteMonthCost)
        .filter(SiteMonthCost.theatre_id.in_(theatre_ids))
        .filter(SiteMonthCost.period_key.in_(period_keys))
        .all()
    )
    return {(r.theatre_id, r.period_key): r.amount_gbp for r in rows}


def _marketing_totals_by_month(session_mkt: Session, segments: list[Segment]) -> dict[int, int]:
    """Single read of marketing.db for all segments."""
    budget_rows = {
        row.segment_id: row for row in session_mkt.query(SegmentMarketingBudget).all()
    }
    by_month: dict[int, int] = {}
    for seg in segments:
        row = budget_rows.get(seg.id)
        if row is None:
            spend = DEFAULT_SPEND.get(seg.slug, 3000)
            active = _default_active_months(seg)
        else:
            spend = row.monthly_spend_gbp
            active = _parse_active_months(row.active_months) or _default_active_months(seg)
        for cal in active:
            by_month[cal] = by_month.get(cal, 0) + spend
    return by_month


def _theatre_marketing_by_month(
    circuit_by_month: dict[int, int],
    counts: dict[int, int],
    theatre_id: int,
    theatre_count: int,
) -> dict[int, int]:
    scale = theatre_share(counts, theatre_id, theatre_count)
    return {cal: round(total * scale) for cal, total in circuit_by_month.items()}


def _site_rows_for_theatre(
    theatre: Theatre,
    months: list[dict],
    fnb_map,
    staff_map,
    util_map,
    other_map,
    marketing_by_month: dict[int, int],
    customers: int,
) -> list[dict]:
    rows = []
    for m in months:
        key = m["key"]
        cal = m["month"]
        rows.append(
            {
                "month": m,
                "marketing": marketing_by_month.get(cal, 0),
                "fnb": fnb_map.get((theatre.id, key), _fnb_cost(customers, cal)),
                "staff": staff_map.get((theatre.id, key), _extra_staff_cost(theatre, cal, customers)),
                "utilities": util_map.get((theatre.id, key), _utilities_cost(theatre)),
                "other": other_map.get((theatre.id, key), _other_default()),
            }
        )
    return rows


def cost_sources_meta() -> dict[str, str]:
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    return {name: str(path.relative_to(root)) for name, path in COST_SOURCE_PATHS.items()}


def seed_cost_stores(session: Session):
    """Populate all five cost databases from synthetic ops formulas."""
    create_cost_stores()
    theatres = session.query(Theatre).order_by(Theatre.id).all()
    segments = session.query(Segment).order_by(Segment.id).all()
    counts = _theatre_customer_counts(session)
    months = future_month_keys(12)
    period_keys = [m["key"] for m in months]

    with cost_store_sessions() as stores:
        session_mkt = stores["marketing"]
        session_fnb = stores["fnb"]
        session_staff = stores["staff"]
        session_util = stores["utilities"]
        session_other = stores["other"]
        session_mkt.query(SegmentMarketingBudget).delete()
        session_fnb.query(SiteMonthCost).delete()
        session_staff.query(SiteMonthCost).delete()
        session_util.query(SiteMonthCost).delete()
        session_other.query(SiteMonthCost).delete()

        for seg in segments:
            session_mkt.add(
                SegmentMarketingBudget(
                    segment_id=seg.id,
                    monthly_spend_gbp=DEFAULT_SPEND.get(seg.slug, 3000),
                    active_months=_format_active_months(_default_active_months(seg)),
                )
            )

        for theatre in theatres:
            customers = counts.get(theatre.id) or 0
            for m in months:
                key = m["key"]
                cal = m["month"]
                session_fnb.add(
                    SiteMonthCost(
                        theatre_id=theatre.id,
                        period_key=key,
                        amount_gbp=_fnb_cost(customers, cal),
                    )
                )
                session_staff.add(
                    SiteMonthCost(
                        theatre_id=theatre.id,
                        period_key=key,
                        amount_gbp=_extra_staff_cost(theatre, cal, customers),
                    )
                )
                session_util.add(
                    SiteMonthCost(
                        theatre_id=theatre.id,
                        period_key=key,
                        amount_gbp=_utilities_cost(theatre),
                    )
                )
                session_other.add(
                    SiteMonthCost(
                        theatre_id=theatre.id,
                        period_key=key,
                        amount_gbp=_other_default(),
                    )
                )

        session_mkt.commit()
        session_fnb.commit()
        session_staff.commit()
        session_util.commit()
        session_other.commit()


def seed_cost_stores_if_empty(session: Session):
    session_mkt = marketing_session()
    try:
        empty = session_mkt.query(SegmentMarketingBudget).count() == 0
    finally:
        session_mkt.close()
    if empty:
        seed_cost_stores(session)


def upsert_other_monthly(session_other: Session, theatre_id: int, period_keys: list[str], amount_gbp: int):
    for key in period_keys:
        row = (
            session_other.query(SiteMonthCost)
            .filter(SiteMonthCost.theatre_id == theatre_id, SiteMonthCost.period_key == key)
            .first()
        )
        if row is None:
            row = SiteMonthCost(theatre_id=theatre_id, period_key=key, amount_gbp=amount_gbp)
            session_other.add(row)
        else:
            row.amount_gbp = amount_gbp
    session_other.commit()


def build_cost_table(session: Session, mode: str, theatre_id: Optional[int]) -> dict:
    months = future_month_keys(12)
    period_keys = [m["key"] for m in months]
    theatres = session.query(Theatre).order_by(Theatre.id).all()
    theatre_ids = [t.id for t in theatres]
    theatre_count = len(theatres)
    counts = _theatre_customer_counts(session)
    segments = session.query(Segment).order_by(Segment.id).all()

    with cost_store_sessions() as stores:
        session_mkt = stores["marketing"]
        session_fnb = stores["fnb"]
        session_staff = stores["staff"]
        session_util = stores["utilities"]
        session_other = stores["other"]

        circuit_mkt = _marketing_totals_by_month(session_mkt, segments)
        fnb_map = _load_ops_matrix(session_fnb, theatre_ids, period_keys)
        staff_map = _load_ops_matrix(session_staff, theatre_ids, period_keys)
        util_map = _load_ops_matrix(session_util, theatre_ids, period_keys)
        other_map = _load_ops_matrix(session_other, theatre_ids, period_keys)

        payload = {
            "sources": cost_sources_meta(),
            "months": months,
        }

        if mode == "compare":
            sites = []
            for theatre in theatres:
                customers = counts.get(theatre.id) or round(200 / max(theatre_count, 1))
                mkt = _theatre_marketing_by_month(circuit_mkt, counts, theatre.id, theatre_count)
                site_rows = _site_rows_for_theatre(
                    theatre, months, fnb_map, staff_map, util_map, other_map, mkt, customers
                )
                totals = {cat: 0 for cat in ("marketing", "fnb", "staff", "utilities", "other")}
                for row in site_rows:
                    for cat in totals:
                        totals[cat] += row[cat]
                sites.append({"theatre_id": theatre.id, "name": theatre.name, "totals": totals})
            payload["compare"] = sites
            return payload

        if mode == "all":
            month_rows = []
            for mi, m in enumerate(months):
                row = {"month": m, "marketing": 0, "fnb": 0, "staff": 0, "utilities": 0, "other": 0}
                for theatre in theatres:
                    customers = counts.get(theatre.id) or round(200 / max(theatre_count, 1))
                    mkt = _theatre_marketing_by_month(circuit_mkt, counts, theatre.id, theatre_count)
                    part = _site_rows_for_theatre(
                        theatre, months, fnb_map, staff_map, util_map, other_map, mkt, customers
                    )[mi]
                    for cat in ("marketing", "fnb", "staff", "utilities", "other"):
                        row[cat] += part[cat]
                month_rows.append(row)
            payload["month_rows"] = month_rows
            return payload

        theatre = session.get(Theatre, theatre_id) if theatre_id else None
        if theatre is None:
            raise ValueError("theatre not found")
        customers = counts.get(theatre.id) or round(200 / max(theatre_count, 1))
        mkt = _theatre_marketing_by_month(circuit_mkt, counts, theatre.id, theatre_count)
        payload["theatre_id"] = theatre.id
        payload["theatre_name"] = theatre.name
        payload["month_rows"] = _site_rows_for_theatre(
            theatre, months, fnb_map, staff_map, util_map, other_map, mkt, customers
        )
        return payload
