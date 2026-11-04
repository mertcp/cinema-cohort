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

- `GET /segments` — ranked by return rate (lowest first)
- `GET /segments/{id}` — genre/month counts + campaigns
- `POST /visits` — ingest a visit
- `POST /segments/{id}/campaign` — draft campaign
- `POST /campaigns/{id}/decision` — accept / edit

Synthetic data only. See [PROJECT.md](PROJECT.md).
