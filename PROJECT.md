# Cinema cohort demo

Living plan for this repo. Created 4 Nov 2026. Status: local demo at http://127.0.0.1:8002/

In a new chat in this folder, say: read `PROJECT.md` and continue from the next unchecked step.

## What we are building

A demo SaaS for **movie theatres**: track **return visits**, **segment audiences**, and see **when**, **how often**, and **which genres** each group buys — so marketing spend goes to the campaigns that actually bring people back.

Interview line: a **behaviour and cohort twin** for the circuit — not a full ticketing ERP or recommender black box. The product groups customers, surfaces patterns (frequency, month, genre), and ranks **which segment deserves the next promo euro**.

Pitch: stop blasting everyone the same poster; know that “horror loyalists in October” vs “family once-a-year December” need different channels and offers.

Audience: CV demo for cloud / SaaS solutions pre-sales (same lane as TraceRail and solar-warranty). **Synthetic customers and showtimes only.** No real cinema chain data, POS exports, or partner contracts.

## Why this shape

| Signal on the CV | What the demo shows |
|---|---|
| Cloud / SaaS | Hosted cohort dashboard, health check, CI |
| API | Visit ingest, segment refresh, OpenAPI |
| Data science | Cohort grouping, return rate, genre/month patterns |
| AI automation | Optional: draft campaign line per segment (one JSON LLM call) |
| Pre-sales | Short script: one segment, one pattern, one ad focus |

Done means a public GitHub repo and optionally a live URL. Finish on the Mac first; deploy only when Mert asks.

## Locked decisions (draft)

- **Domain:** cinema marketing efficiency — customer metric is **return rate** and **incremental visits per marketing euro** (demo uses **return rate** and **visit count** as proxy).
- **Workflow:** ingest visits → compute return metrics → group customers → show patterns (frequency, calendar month, genre) → recommend segment to target → human accept or edit campaign line.
- **Screens:** circuit overview, segment list, segment detail (heatmap or bars: months × genre), campaign draft panel.
- **Twin depth:** circuit → theatre (optional) → **customer** with segment badge; aggregate **segment** view for marketing.
- **World:** synthetic chain, ~3–5 theatres, **thousands of customers** (can seed hundreds for demo speed), 12–18 months of ticket rows.
- **Inputs (minimum honest set):**
  - **Visit:** customer_id (pseudonym), showtime date, genre, optional ticket type.
  - **Return:** derived — days since last visit, visits in last 90d, returned within 30/60/90d flag.
  - **Grouping:** simple explainable segments first (e.g. high-frequency action, seasonal family, lapsed horror) — k-means or rule buckets, visible rules on the page.
- **Scoring:** return_rate = returning customers / eligible; visits_per_year; genre share per segment; peak months.
- **Stack:** FastAPI, simple UI, SQLite, one optional LLM call for campaign copy; pandas or plain Python for aggregates.
- **Data:** synthetic only.
- **Repo:** GitHub `mertcp`, separate from TraceRail and solar-warranty.

## Out of scope

- Real POS / Vista / Comscore integration
- PII, email campaigns, GDPR production stack
- Full attribution (Facebook / Google Ads APIs)
- Box-office forecasting ML, seat optimization
- Real cinema names from work

## Build order

- [x] Name product and repo (**Cinema cohort demo** / `cinema-cohort`, GitHub `mertcp`)
- [x] Schema: theatre, customer, visit, segment, campaign_drafts (`app/models.py`)
- [x] Seed ~420 customers, visits, segments (`app/seed.py`)
- [x] Metrics: return rate, visits/year, genre/month (`app/segments.py`)
- [x] API (`app/api.py`)
- [x] UI (`app/dashboard.html`)
- [x] README; CI (`check.yml`)
- [ ] Deploy only when Mert asks (state cost and get approval)

## Eight-minute script (target)

1. One segment “lapsed family” — came for animation in Dec, not back in 6 months.
2. Dashboard ranks segments by **return rate gap** vs circuit average.
3. Open segment: bar chart — **months** and **genres** for that group.
4. Draft campaign: “Target lapsed family segment: double feature Sat matinee, animation + kid promo — expect lift in December return rate.”
5. Accept or edit; show aggregate stats backing the line.
6. `/docs` — how a ticketing feed POSTs the next visit row.

## Risks

- Looks like a generic CRM — always lead with **return rate** and **genre/month pattern**.
- Over-fancy clustering — keep segment rules readable aloud.
- Duplicate TraceRail/solar UI — lead with **cohorts and marketing**, not kWh or delay minutes.

## How the code should read

Mert walks recruiters through the repo. Small files, straight functions, cinema words: visit, return, segment, genre, matinee.

Comment only non-obvious segment rules or return-rate definition. No framework scaffolding.

## Before the project is finished

Warn Mert first. Do not delete agent notes until he agrees. Then remove agent-only sections and `.cursor/rules` except **cost approval**.

## Cost approval

Finish on this Mac. Do not deploy until Mert asks.

Any action that can cost money must stop first. State the amount, then ask exactly: **“This will cost you this amount. Do you approve this action?”** Do not continue until he says yes. Includes cloud host, OpenAI, paid APIs, Azure, etc. **Keep this rule when agent notes are removed.**

## How we work in Cursor

- Open this folder before coding.
- `PROJECT.md` is the memory; update unchecked steps honestly.
- `.cursor/rules/cinema-cohort.mdc` scopes new chats.
- Resume: read `PROJECT.md` and continue from the next unchecked step.
- Prefer minimum token use; no deploy loops unless Mert asks.

## Open decisions for Mert

1. **Product name on CV** (Cinema cohort, ReelReturn, ShowSegment, …).
2. **Segment method for v1:** fixed rule buckets vs k-means on (visits/year, genre entropy, recency).
3. **Chain fiction name** (e.g. Lynch Boulevard Cinemas).
4. **Public repo name** on `mertcp` — default `cinema-cohort`.
