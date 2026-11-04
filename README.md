# Cinema cohort demo

Synthetic **North Star Cinemas** ticket rows → **return rates**, **segments**, **genre/month patterns** → draft **campaign** lines.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.api:app --host 127.0.0.1 --port 8002
```

Open http://127.0.0.1:8002/ — **Lapsed family** opens first; campaign drafts on click.

## API

- `GET /segments` — circuit return rate + segments (lowest first)
- `GET /segments/{id}` — genre/month counts + campaigns
- `POST /visits` — ingest a visit
- `POST /segments/{id}/campaign` — draft campaign
- `POST /campaigns/{id}/decision` — accept / edit
- `GET /segments/{id}/evidence` — marketing evidence JSON

```bash
curl -s http://127.0.0.1:8002/segments | python3 -m json.tool | head -20
curl -s -X POST http://127.0.0.1:8002/visits -H 'content-type: application/json' \
  -d '{"customer_code":"P-10042","theatre_id":1,"visited_on":"2026-11-01","genre":"animation"}'
```

Synthetic data only. See [PROJECT.md](PROJECT.md).
