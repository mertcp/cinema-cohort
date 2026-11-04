"""Synthetic North Star Cinemas visits."""

import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.db import ENGINE, create_tables
from app.models import Base, Customer, Segment, Theatre, Visit
from app.segments import assign_segment, segment_stats

TODAY = date(2026, 11, 3)
SEGMENT_LABELS = {
    "high_freq_action": "High-frequency action",
    "lapsed_family": "Lapsed family",
    "horror_autumn": "Horror autumn",
    "at_risk": "At-risk occasional",
    "steady_mixed": "Steady mixed",
    "unknown": "Unknown",
}


def _reset():
    create_tables()
    Base.metadata.drop_all(ENGINE)
    create_tables()


def seed(session: Session, rng=None) -> dict:
    if rng is None:
        rng = random.Random(20261105)
    for name, city in (("North Star Mall", "Uppsala"), ("North Star Harbor", "Turku"), ("North Star Plaza", "Odense")):
        session.add(Theatre(name=name, city=city))
    session.flush()

    segments = {}
    for slug, label in SEGMENT_LABELS.items():
        if slug == "unknown":
            continue
        seg = Segment(slug=slug, label=label)
        session.add(seg)
        segments[slug] = seg
    session.flush()

    theatres = session.query(Theatre).all()
    counts = {"customers": 0, "visits": 0}
    for index in range(420):
        customer = Customer(code="P-{0:05d}".format(10000 + index))
        session.add(customer)
        counts["customers"] += 1
        profile = rng.choice(("action_fan", "family", "horror", "random", "lapsed", "lapsed"))
        visits_n = 1 if profile == "lapsed" else rng.randint(1, 14)
        for _ in range(visits_n):
            if profile == "lapsed":
                day = date(2025, 12, rng.randint(2, 22))
            elif profile == "family":
                day = date(2025, 12, rng.randint(1, 26)) if rng.random() < 0.55 else TODAY - timedelta(days=rng.randint(5, 200))
            elif profile == "horror":
                month = rng.choice((9, 10, 9, 10, 3))
                day = date(2026 if month >= 9 else 2025, month, rng.randint(1, 26))
            else:
                day = TODAY - timedelta(days=rng.randint(3, 400))
            if profile == "action_fan":
                genre = rng.choice(("action", "action", "action", "comedy"))
            elif profile == "family":
                genre = rng.choice(("animation", "animation", "comedy"))
            elif profile == "horror":
                genre = rng.choice(("horror", "horror", "drama"))
            else:
                genre = rng.choice(("action", "comedy", "drama", "documentary"))
            session.add(
                Visit(
                    customer=customer,
                    theatre=rng.choice(theatres),
                    visited_on=day,
                    genre=genre if genre != "thriller" else "horror",
                    ticket_type=rng.choice(("standard", "matinee", "student")),
                )
            )
            counts["visits"] += 1
    session.flush()

    by_slug = {slug: [] for slug in segments}
    for customer in session.query(Customer).all():
        slug = assign_segment(customer.visits, TODAY)
        if slug not in segments:
            slug = "steady_mixed"
        customer.segment_id = segments[slug].id
        by_slug[slug].append(customer)

    for slug, seg in segments.items():
        members = by_slug.get(slug, [])
        rr, vpy, top_g, peak_m = segment_stats(members, TODAY)
        seg.return_rate = rr
        seg.visits_per_year = vpy
        seg.top_genre = top_g
        seg.peak_month = peak_m
        seg.member_count = len(members)

    session.commit()
    return counts


def main():
    _reset()
    session = __import__("app.db", fromlist=["get_session"]).get_session()
    try:
        counts = seed(session)
    finally:
        session.close()
    print("customers={0} visits={1}".format(counts["customers"], counts["visits"]))


if __name__ == "__main__":
    main()
