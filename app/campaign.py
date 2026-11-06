"""Campaign ideas aligned to age-based cinema audiences and family outings."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from app.segments import target_profile

SUGGESTIONS = {
    "age_kids": [
        (
            "Kids club: stamp card → free popcorn after 3 animation matinees.",
            "in-venue + email",
            0.07,
            "Year-round · Jul–Aug & school breaks (Feb, Apr, Oct half-term, Dec)",
        ),
        (
            "Holiday morning screening + activity sheet for PG animation.",
            "social + poster",
            0.06,
            "Jul–Aug summer break · late Oct half-term · mid-Dec",
        ),
        (
            "Parent email: next school-break matinee times for top kid title.",
            "email",
            0.05,
            "1 week before each break · Sat/Sun matinee slots",
        ),
    ],
    "age_teens": [
        (
            "Student / teen ticket night — Fri–Sat with ID at box office.",
            "social + in-venue",
            0.05,
            "Term-time Fri–Sat · spikes before holidays",
        ),
        (
            "Group of 4+ discount on buzz PG-13 / 15 titles opening weekend.",
            "app",
            0.04,
            "May–Aug & Nov–Dec tentpole openings",
        ),
        (
            "Snap-to-win concession credit after sharing a post-film poll.",
            "social",
            0.03,
            "Opening weekends year-round",
        ),
    ],
    "age_young_adults": [
        (
            "Opening-night party screening — target groups who book Fri–Sat.",
            "social",
            0.05,
            "May–Aug & Nov–Dec buzz titles · Fri–Sat opening weekends",
        ),
        (
            "Friends bundle: 4 tickets for price of 3 on buzz titles.",
            "app",
            0.04,
            "Opening week of tentpoles · spring/summer & holiday season",
        ),
        (
            "Post-film dining partner offer (extend-the-night behaviour).",
            "partnership",
            0.03,
            "Fri–Sat year-round · peak May–Aug social season",
        ),
    ],
    "age_adults": [
        (
            "Tentpole reminder 10 days before release — occasional goers respond to event films.",
            "email",
            0.05,
            "May–Aug & Nov–Dec blockbuster windows",
        ),
        (
            "Midweek date-night bundle: two tickets + shared concession.",
            "email + app",
            0.04,
            "Wed–Thu year-round · stronger Oct–Feb",
        ),
        (
            "Dynamic ad for their last-watched genre when a similar title opens.",
            "programmatic",
            0.03,
            "2 weeks before each major release in their preferred genre",
        ),
    ],
    "age_seniors": [
        (
            "Silver screen matinee: discounted weekday slots + free tea/coffee.",
            "in-venue + email",
            0.06,
            "Tue–Thu matinees · Sep–Apr (outside peak summer)",
        ),
        (
            "Classic & drama season pass — four matinees at fixed price.",
            "loyalty",
            0.05,
            "Jan–Mar & Sep–Nov when drama/documentary slates peak",
        ),
        (
            "Coach / community group booking for morning screenings.",
            "partnership",
            0.04,
            "Spring & autumn shoulder months",
        ),
    ],
    "family_moviegoing": [
        (
            "School-holiday matinee bundle + kids meal (family motivators).",
            "email + in-venue",
            0.08,
            "School breaks · Feb, Easter, Jul–Aug, Oct half-term · Dec",
        ),
        (
            "Saturday morning family slot advertised 2 weeks before holiday.",
            "social",
            0.06,
            "Start ads 2 weeks before each break · Sat/Sun matinees",
        ),
        (
            "Parent newsletter: next animation release + kid-friendly showtimes.",
            "email",
            0.05,
            "Nov–Dec animation season · summer family releases (Jul–Aug)",
        ),
    ],
}


def campaign_suggestions(segment):
    rows = SUGGESTIONS.get(segment.slug, SUGGESTIONS["age_adults"])
    month_names = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    peak = segment.peak_month
    data_peak = month_names[peak] if 0 < peak < 13 else ""
    out = []
    for text, channel, lift, season in rows:
        item = {
            "action": text,
            "channel": channel,
            "expected_lift": lift,
            "season_focus": season,
        }
        if data_peak and not out:
            item["data_peak_month"] = data_peak
        out.append(item)
    return out


def brief(segment):
    body = target_profile(segment)
    body["slug"] = segment.slug
    return body


def draft_from_rules(segment):
    options = campaign_suggestions(segment)
    first = options[0]
    return first["action"], first["channel"], first["expected_lift"], 0.75


def draft_from_llm(segment):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    body = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You propose one cinema marketing campaign for an age-based or family target group. "
                    "Reply JSON: action, channel, expected_lift, confidence."
                ),
            },
            {"role": "user", "content": json.dumps(brief(segment))},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer {0}".format(key)},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        payload = json.loads(raw["choices"][0]["message"]["content"])
        return (
            str(payload.get("action", "")).strip(),
            str(payload.get("channel", "email")),
            float(payload.get("expected_lift", 0.05)),
            float(payload.get("confidence", 0.7)),
        )
    except (urllib.error.URLError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def draft(segment):
    from_llm = draft_from_llm(segment)
    if from_llm:
        return from_llm
    return draft_from_rules(segment)
