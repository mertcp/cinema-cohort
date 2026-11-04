"""Draft a campaign line from segment stats. LLM optional."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def brief(segment):
    return {
        "segment": segment.label,
        "return_rate": segment.return_rate,
        "visits_per_year": segment.visits_per_year,
        "top_genre": segment.top_genre,
        "peak_month": MONTHS[segment.peak_month] if 0 < segment.peak_month < 13 else "",
        "members": segment.member_count,
    }


def draft_from_rules(segment):
    month = MONTHS[segment.peak_month] if 0 < segment.peak_month < 13 else "peak month"
    if segment.slug == "lapsed_family":
        return (
            "Target {0}: Saturday matinee bundle, animation + kid meal — push in November before {1} peak.".format(
                segment.label, month
            ),
            "email + social",
            0.08,
            0.78,
        )
    if segment.slug == "horror_autumn":
        return (
            "Target {0}: horror festival trailer and {1} night offer — double feature for returning fans.".format(
                segment.label, month
            ),
            "in-app + poster",
            0.06,
            0.72,
        )
    if segment.slug == "at_risk":
        return (
            "Win-back {0}: two-for-one drama or comedy, limit to members inactive 120+ days.".format(segment.label),
            "email",
            0.05,
            0.65,
        )
    return (
        "Maintain {0}: genre-led previews for {1} lovers ahead of {2}.".format(
            segment.label, segment.top_genre, month
        ),
        "social",
        0.03,
        0.55,
    )


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
                    "You propose cinema marketing campaigns from segment stats. "
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
