"""Assign customers to age-based cinema audiences plus a family outing group."""

from collections import Counter
from datetime import date, timedelta

GENRES = ("action", "comedy", "drama", "horror", "animation", "documentary")

# Five age buckets + family (parent-led outings). Ages are demo synthetic field on Customer.
TARGET_GROUPS = {
    "age_kids": "Kids (ages 6–12 · animation & matinees)",
    "age_teens": "Teens (ages 13–17 · friends & buzz titles)",
    "age_young_adults": "Young adults (ages 18–29 · social & opening nights)",
    "age_adults": "Adults (ages 30–54 · broad slate)",
    "age_seniors": "Seniors (ages 55+ · matinees & drama)",
    "family_moviegoing": "Family moviegoing (parents booking with kids)",
}

TABLE_LABELS = {
    "age_kids": "Kids 6–12",
    "age_teens": "Teens 13–17",
    "age_young_adults": "Young adults 18–29",
    "age_adults": "Adults 30–54",
    "age_seniors": "Seniors 55+",
    "family_moviegoing": "Family",
}

GROUP_PROFILES = {
    "age_kids": {
        "when_likely": "School breaks and Sat/Sun matinees; half-term and holiday weeks.",
        "prefers": "Animation and PG titles; often with a parent or guardian booking.",
    },
    "age_teens": {
        "when_likely": "Fri–Sat evenings and holidays; often in friend groups.",
        "prefers": "Buzz titles, comedy, and event screenings (PG-13 / 15-rated).",
    },
    "age_young_adults": {
        "when_likely": "Opening weekends and Fri–Sat nights; social plans.",
        "prefers": "New releases, premium formats, and shareable experiences.",
    },
    "age_adults": {
        "when_likely": "Evenings and selective weekends year-round.",
        "prefers": "Drama, comedy, and tentpoles — balanced genre mix.",
    },
    "age_seniors": {
        "when_likely": "Weekday and weekend matinees; quieter dayparts.",
        "prefers": "Drama, documentary, and classic repertory-style titles.",
    },
    "family_moviegoing": {
        "when_likely": "Weekends and school holidays; daytime matinees.",
        "prefers": "Family animation and kid-friendly titles; parents book, kids pick the title.",
    },
}

AGE_RANGE_BY_SLUG = {
    "age_kids": (6, 12),
    "age_teens": (13, 17),
    "age_young_adults": (18, 29),
    "age_adults": (30, 54),
    "age_seniors": (55, 90),
}


def label_for_slug(slug: str) -> str:
    return TARGET_GROUPS.get(slug, "Unassigned")


def table_label_for_slug(slug: str) -> str:
    return TABLE_LABELS.get(slug, label_for_slug(slug))


def target_profile(segment, **stats) -> dict:
    base = GROUP_PROFILES.get(segment.slug, {"when_likely": "Varies", "prefers": "Mixed"})
    month_names = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    peak = stats.get("peak_month", segment.peak_month)
    peak_name = month_names[peak] if 0 < peak < 13 else ""
    profile = {
        "target_group": segment.label,
        "when_likely": base["when_likely"],
        "prefers": base["prefers"],
        "data_peak_month": peak_name,
        "data_top_genre": stats.get("top_genre", segment.top_genre),
        "return_rate": stats.get("return_rate", segment.return_rate),
        "visits_per_year": stats.get("visits_per_year", segment.visits_per_year),
        "members": stats.get("members", segment.member_count),
    }
    if segment.slug in AGE_RANGE_BY_SLUG:
        lo, hi = AGE_RANGE_BY_SLUG[segment.slug]
        profile["age_range"] = "{0}–{1}".format(lo, hi)
    elif segment.slug == "family_moviegoing":
        profile["age_range"] = "Parent-led (typically 25–50 booking for household)"
    return profile


def slug_for_age(age: int) -> str:
    if age <= 12:
        return "age_kids"
    if age <= 17:
        return "age_teens"
    if age <= 29:
        return "age_young_adults"
    if age <= 54:
        return "age_adults"
    return "age_seniors"


def _family_moviegoing(visits, today: date, age: int) -> bool:
    """Adult booker with kid-oriented visit pattern (not the child's age bucket)."""
    if age < 22 or age > 55 or not visits:
        return False
    dates = sorted(v.visited_on for v in visits)
    genres = [v.genre for v in visits]
    counts = Counter(genres)
    anim_n = counts.get("animation", 0)
    matinee_n = sum(1 for v in visits if v.ticket_type == "matinee")
    holiday_months = sum(1 for v in visits if v.visited_on.month in (2, 4, 7, 8, 10, 12))
    dec_family = sum(
        1 for v in visits if v.genre in ("animation", "comedy") and v.visited_on.month == 12
    )
    if anim_n >= 1 and (matinee_n >= 1 or holiday_months >= 1 or dec_family >= 1):
        return True
    if counts.get("animation", 0) + counts.get("comedy", 0) >= len(dates) // 2 + 1 and matinee_n >= 1:
        return True
    return False


def assign_segment(visits, today: date, age: int = 35):
    if _family_moviegoing(visits, today, age):
        return "family_moviegoing"
    return slug_for_age(age)


def return_rate_for_members(customers, today: date, window_days=90):
    eligible = 0
    returned = 0
    cutoff = today - timedelta(days=365)
    for customer in customers:
        dates = sorted(v.visited_on for v in customer.visits if v.visited_on >= cutoff)
        if not dates:
            continue
        eligible += 1
        if len(dates) < 2:
            continue
        if (dates[1] - dates[0]).days <= window_days:
            returned += 1
    if eligible == 0:
        return 0.0
    return round(returned / eligible, 3)


def circuit_return_rate(segments) -> float:
    total = sum(s.member_count for s in segments)
    if total == 0:
        return 0.0
    weighted = sum(s.return_rate * s.member_count for s in segments)
    return round(weighted / total, 3)


def segment_stats(customers, today: date):
    visits = []
    for customer in customers:
        visits.extend(customer.visits)
    if not visits:
        return 0.0, 0.0, "", 1
    genres = Counter(v.genre for v in visits)
    months = Counter(v.visited_on.month for v in visits)
    per_customer = len(visits) / max(len(customers), 1)
    years = max((max(v.visited_on for v in visits) - min(v.visited_on for v in visits)).days, 1) / 365.0
    return (
        return_rate_for_members(customers, today),
        round(per_customer / max(years, 0.25), 1),
        genres.most_common(1)[0][0],
        months.most_common(1)[0][0],
    )
