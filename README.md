# Ad Spend / Revenue Reconciliation Simulator

I built this to get a feel for the timing problem in ad-spend financing. Spend happens right away, but the revenue it generates shows up later (and there's no clean ID linking the two). So you end up guessing which revenue belongs to which spend, and how confident you are in that guess before you'd actually front money against it.

**Live demo:** https://ad-spend-revenue-reconciliation-simulator-production.up.railway.app/

Give it ~30 seconds after opening — spends and revenue start populating the dashboard.

## What it does

- **Spend generator**: fires random ad spend events every few seconds
- **Revenue generator**: sends back delayed revenue (5-90s later) with slightly different amounts (roughly 85-105% of the spend)
- **Matching engine**: tries to pair revenue with pending spends based on amount + timing, outputs a confidence score instead of a hard yes/no
- **Stale checker**: if a spend sits unmatched too long, it gets flagged as stale

Each spend ends up as `pending`, `matched`, or `stale`.

## Setup

You'll need Python 3.11+ and Docker (for Redis).

```bash
pip install -r requirements.txt

docker compose up -d

# optional, defaults are fine without this
cp .env.example .env

uvicorn app.main:app --reload
```

Give it ~30 seconds, then open `http://127.0.0.1:8000/` for the live dashboard (or hit `/status` for raw JSON).

## API

| Endpoint | What it gives you |
|----------|-------------------|
| `GET /health` | Is Redis up |
| `GET /status` | Counts (matched / pending / stale / orphan), config, recent matches |
| `GET /events?limit=50` | Recent state changes with confidence scores |
| `GET /config` | Current thresholds |
| `PATCH /config` | Change thresholds on the fly |

Example `/status` response:

```json
{
  "counts": {"matched": 12, "pending": 3, "stale": 2, "orphan_revenue": 1},
  "config": {"match_threshold": 0.75, "stale_after_sec": 120},
  "recent_matches": [{"spend_id": "...", "confidence": 0.91}]
}
```

## Config

Env vars work (check `app/config.py`), or you can patch at runtime:

```bash
curl -X PATCH http://127.0.0.1:8000/config \
  -H "Content-Type: application/json" \
  -d '{"ambiguity_margin": 0.05, "stale_after_sec": 150}'
```

| Variable | Default | What it does |
|----------|---------|--------------|
| `MATCH_THRESHOLD` | 0.75 | Min confidence to auto-match |
| `AMBIGUITY_MARGIN` | 0.15 | How much better the top candidate needs to be vs the second |
| `AMOUNT_TOLERANCE_PCT` | 0.15 | How far off revenue amount can be from spend |
| `STALE_AFTER_SEC` | 120 | When to give up waiting and flag a spend stale |
| `LOOKBACK_SEC` | 300 | How far back to look for candidate spends |
| `REVENUE_DELAY_MAX_SEC` | 90 | Longest simulated revenue delay |

## Tests

```bash
pytest
```

## What actually broke

The scoring math was fine. The annoying part was **two similar spends landing close together**.

Say you get two $100 spends within 30 seconds, then $97 in revenue shows up. Both spends score pretty well. The matcher refuses to pick one (`ambiguity_margin`), so both stay pending. If revenue takes long enough, they can go stale before anything gets matched, even though the revenue did arrive.

You can lower `ambiguity_margin` and it'll just pick the closer spend. But that might be the wrong one. Or you can raise `stale_after_sec` to wait longer, but then you're sitting on unmatched spend forever.

## Project layout

```
app/
├── main.py              # FastAPI + background workers
├── config.py            # settings
├── clock.py             # RealClock / SimClock
├── generators/          # spend + revenue loops
├── matching/            # scoring, matcher, stale checker
├── models/              # data types
├── store/               # Redis stuff
└── api/                 # HTTP routes
```
