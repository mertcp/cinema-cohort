"""Assign customers to segments and compute return-rate stats."""

from collections import Counter
from datetime import date, timedelta

GENRES = ("action", "comedy", "drama", "horror", "animation", "documentary")

SEGMENT_RULES = {
    "lapsed_family": "One family-style visit (animation/comedy), last visit 90+ days ago.",
    "high_freq_action": "About six or more visits per year, mostly action.",
    "horror_autumn": "Two or more horror visits, at least one in September or October.",
    "at_risk": "Low frequency and last visit 120+ days ago.",
    "steady_mixed": "Everyone else with a mixed pattern.",
}


def rule_for_slug(slug: str) -> str:
    return SEGMENT_RULES.get(slug, "Assigned from visit history.")


def assign_segment(visits, today: date):
    """Rule buckets a recruiter can repeat aloud."""
    if not visits:
        return "unknown"
    dates = sorted(v.visited_on for v in visits)
    genres = [v.genre for v in visits]
    counts = Counter(genres)
    top = counts.most_common(1)[0][0]
    span_days = max((dates[-1] - dates[0]).days, 30)
    rate = len(dates) / span_days * 365.0
    last_gap = (today - dates[-1]).days
    dec_animation = sum(1 for v in visits if v.genre == "animation" and v.visited_on.month == 12)

    if len(dates) == 1 and last_gap > 90 and top in ("animation", "comedy"):
        return "lapsed_family"
    if len(dates) == 1 and last_gap > 90:
        return "at_risk"

    if rate >= 6 and top == "action":
        return "high_freq_action"
    if dec_animation >= 2 and last_gap > 90:
        return "lapsed_family"
    if counts.get("horror", 0) >= 2 and any(v.visited_on.month in (9, 10) for v in visits):
        return "horror_autumn"
    if rate < 2 and last_gap > 120:
        return "at_risk"
    return "steady_mixed"


def return_rate_for_members(customers, today: date, window_days=90):
    """Share of members with at least one visit who came back within window_days of first visit."""
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
