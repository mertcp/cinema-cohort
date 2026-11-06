"""Synthetic Lynch Boulevard Cinemas visits — London circuit demo."""

import random
from collections import Counter
from datetime import date, timedelta

from sqlalchemy.orm import Session, joinedload

from app.costs import reset_cost_stores, seed_cost_stores
from app.db import ENGINE, create_tables
from app.models import Base, Customer, Segment, Theatre, Visit
from app.segments import TARGET_GROUPS, assign_segment, segment_stats

TODAY = date(2026, 11, 3)
CUSTOMER_COUNT = 200

# Borough / outward postcode / approximate centre (OpenStreetMap-friendly demo coords).
LONDON_AREAS = (
    ("Camden", "NW1", 51.5390, -0.1426),
    ("Westminster", "SW1A", 51.5014, -0.1419),
    ("Islington", "N1", 51.5416, -0.1022),
    ("Hackney", "E8", 51.5450, -0.0553),
    ("Tower Hamlets", "E1", 51.5155, -0.0650),
    ("Southwark", "SE1", 51.5035, -0.0800),
    ("Lambeth", "SE11", 51.4931, -0.1170),
    ("Wandsworth", "SW18", 51.4567, -0.1920),
    ("Hammersmith & Fulham", "W6", 51.4920, -0.2230),
    ("Kensington & Chelsea", "SW7", 51.4991, -0.1938),
    ("Westminster", "W2", 51.5154, -0.1755),
    ("City of London", "EC2", 51.5155, -0.0922),
    ("Greenwich", "SE10", 51.4820, -0.0100),
    ("Lewisham", "SE13", 51.4630, -0.0120),
    ("Croydon", "CR0", 51.3720, -0.1000),
    ("Ealing", "W5", 51.5130, -0.3080),
    ("Brent", "NW10", 51.5580, -0.2490),
    ("Haringey", "N17", 51.5900, -0.0700),
    ("Newham", "E15", 51.5380, 0.0030),
    ("Richmond upon Thames", "TW9", 51.4610, -0.3030),
    ("Merton", "SW19", 51.4090, -0.2100),
    ("Barnet", "N12", 51.6120, -0.1760),
    ("Redbridge", "IG1", 51.5590, 0.0740),
    ("Waltham Forest", "E17", 51.5830, -0.0190),
)

# Synthetic age + visit behaviour → six segments (five age buckets + family).
PROFILE_WEIGHTS = (
    ("kids", 2),
    ("teens", 2),
    ("young_adult", 2),
    ("adult", 2),
    ("senior", 2),
    ("family", 2),
)
PROFILE_CHOICES = [name for name, weight in PROFILE_WEIGHTS for _ in range(weight)]


def _age_for_profile(rng: random.Random, profile: str) -> int:
    if profile == "kids":
        return rng.randint(6, 12)
    if profile == "teens":
        return rng.randint(13, 17)
    if profile == "young_adult":
        return rng.randint(18, 29)
    if profile == "senior":
        return rng.randint(55, 74)
    if profile == "family":
        return rng.randint(28, 48)
    return rng.randint(30, 52)

# name, borough, street address, postcode, lat, lng, screens, seats
LONDON_THEATRES = (
    (
        "Lynch Boulevard Leicester Square",
        "Westminster",
        "24 Leicester Square",
        "WC2H 7LP",
        51.510067,
        -0.129869,
        12,
        2840,
    ),
    (
        "Lynch Boulevard Victoria",
        "Westminster",
        "58 Victoria Street",
        "SW1E 6QP",
        51.4978,
        -0.1354,
        10,
        2200,
    ),
    (
        "Lynch Boulevard Covent Garden",
        "Camden",
        "45 St Martin's Lane",
        "WC2N 4HX",
        51.5119,
        -0.1276,
        9,
        1750,
    ),
    (
        "Lynch Boulevard King's Cross",
        "Camden",
        "2 Pancras Square",
        "N1C 4AG",
        51.5324,
        -0.1255,
        11,
        2400,
    ),
    (
        "Lynch Boulevard Angel",
        "Islington",
        "1 Islington High Street",
        "N1 9LQ",
        51.5322,
        -0.1058,
        8,
        1500,
    ),
    (
        "Lynch Boulevard London Bridge",
        "Southwark",
        "32 Borough High Street",
        "SE1 1LL",
        51.5055,
        -0.0910,
        13,
        2600,
    ),
    (
        "Lynch Boulevard South Bank",
        "Lambeth",
        "11 Belvedere Road",
        "SE1 8XX",
        51.5059,
        -0.1175,
        12,
        2900,
    ),
    (
        "Lynch Boulevard Waterloo",
        "Lambeth",
        "56 Waterloo Road",
        "SE1 8SF",
        51.5034,
        -0.1110,
        9,
        1680,
    ),
    (
        "Lynch Boulevard Barbican",
        "City of London",
        "Silk Street",
        "EC2Y 8DS",
        51.5202,
        -0.0939,
        7,
        980,
    ),
)


def _reset():
    create_tables()
    Base.metadata.drop_all(ENGINE)
    create_tables()
    reset_cost_stores()


def _postcode(rng: random.Random, outward: str) -> str:
    return "{0} {1}{2}{3}".format(
        outward,
        rng.randint(1, 9),
        rng.choice("ABDEFGHJKLMNPQRSTUWXY"),
        rng.choice("ABDEFGHJKLMNPQRSTUWXY"),
    )


def _london_customer(rng: random.Random) -> tuple[str, str, float, float]:
    borough, outward, lat, lng = rng.choice(LONDON_AREAS)
    jitter_lat = rng.uniform(-0.018, 0.018)
    jitter_lng = rng.uniform(-0.022, 0.022)
    return borough, _postcode(rng, outward), round(lat + jitter_lat, 6), round(lng + jitter_lng, 6)


def seed(session: Session, rng=None) -> dict:
    if rng is None:
        rng = random.Random(20261105)
    for name, borough, address, postcode, lat, lng, screens, seats in LONDON_THEATRES:
        session.add(
            Theatre(
                name=name,
                city="London",
                borough=borough,
                address=address,
                postcode=postcode,
                lat=lat,
                lng=lng,
                screen_count=screens,
                seat_capacity=seats,
            )
        )
    session.flush()

    segments = {}
    for slug, label in TARGET_GROUPS.items():
        seg = Segment(slug=slug, label=label)
        session.add(seg)
        segments[slug] = seg
    session.flush()

    theatres = session.query(Theatre).all()
    counts = {"customers": 0, "visits": 0}
    for index in range(CUSTOMER_COUNT):
        borough, postcode, lat, lng = _london_customer(rng)
        customer = Customer(
            code="P-{0:05d}".format(10000 + index),
            borough=borough,
            postcode=postcode,
            lat=lat,
            lng=lng,
        )
        session.add(customer)
        counts["customers"] += 1
        profile = rng.choice(PROFILE_CHOICES)
        customer.age = _age_for_profile(rng, profile)
        if profile == "kids":
            visits_n = rng.randint(3, 8)
        elif profile == "family":
            visits_n = 1 if rng.random() < 0.55 else rng.randint(2, 4)
        else:
            visits_n = rng.randint(1, 12)
        for _ in range(visits_n):
            if profile == "family":
                if visits_n == 1:
                    day = date(2025, 12, rng.randint(1, 26))
                elif _ == 0:
                    day = date(2025, 12, rng.randint(1, 26))
                else:
                    day = TODAY - timedelta(days=rng.randint(120, 280))
            elif profile == "kids":
                month = rng.choice((2, 4, 7, 8, 10, 12))
                day = date(2026 if month >= 7 else 2025, month, rng.randint(1, 26))
            elif profile == "teens":
                day = TODAY - timedelta(days=rng.randint(3, 280))
            elif profile == "senior":
                day = TODAY - timedelta(days=rng.randint(10, 320))
            else:
                day = TODAY - timedelta(days=rng.randint(3, 400))
            if profile == "family":
                genre = rng.choice(("animation", "animation", "comedy"))
            elif profile == "kids":
                genre = rng.choice(("animation", "animation", "animation", "comedy"))
            elif profile == "teens":
                genre = rng.choice(("action", "comedy", "horror", "horror", "comedy"))
            elif profile == "young_adult":
                genre = rng.choice(("action", "action", "comedy", "horror", "drama"))
            elif profile == "senior":
                genre = rng.choice(("drama", "drama", "documentary", "comedy"))
            else:
                genre = rng.choice(("action", "comedy", "drama", "documentary"))
            ticket = "matinee"
            if profile == "kids" or profile == "senior" or (profile == "family" and rng.random() < 0.7):
                ticket = "matinee"
            elif profile == "teens":
                ticket = rng.choice(("standard", "student", "student"))
            else:
                ticket = rng.choice(("standard", "matinee", "student"))
            session.add(
                Visit(
                    customer=customer,
                    theatre=rng.choice(theatres),
                    visited_on=day,
                    genre=genre,
                    ticket_type=ticket,
                )
            )
            counts["visits"] += 1
    session.flush()

    by_theatre = {t.id: 0 for t in theatres}
    for customer in session.query(Customer).options(joinedload(Customer.visits)).all():
        if customer.visits:
            visit_counts = Counter(v.theatre_id for v in customer.visits)
            home_id, _ = max(visit_counts.items(), key=lambda item: (item[1], -item[0]))
        else:
            home_id = theatres[customer.id % len(theatres)].id
        customer.home_theatre_id = home_id
        by_theatre[home_id] += 1
    session.flush()

    by_slug = {slug: [] for slug in segments}
    for customer in session.query(Customer).all():
        slug = assign_segment(customer.visits, TODAY, customer.age)
        if slug not in segments:
            slug = "age_adults"
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
    seed_cost_stores(session)
    counts["by_borough"] = {}
    counts["by_segment"] = {slug: len(members) for slug, members in by_slug.items()}
    counts["by_theatre"] = by_theatre
    assert sum(by_theatre.values()) == counts["customers"]
    assert sum(counts["by_segment"].values()) == counts["customers"]
    return counts


def main():
    _reset()
    session = __import__("app.db", fromlist=["get_session"]).get_session()
    try:
        counts = seed(session)
    finally:
        session.close()
    print("customers={0} visits={1}".format(counts["customers"], counts["visits"]))
    print("segments:", counts.get("by_segment"))


if __name__ == "__main__":
    main()
