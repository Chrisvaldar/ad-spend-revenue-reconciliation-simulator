# Ad Spend / Revenue Reconciliation Simulator

A small simulator for the core timing problem in ad-spend financing: **spend lands instantly, revenue arrives later and without a clean foreign key**. The matcher reconciles the two using amount proximity and time windows, producing confidence scores instead of binary yes/no matches.

## What it does

- **Spend generator** — fires random ad spend events every few seconds
- **Revenue generator** — schedules delayed revenue (5–90s) with amount variance (85–105% of spend)
- **Matching engine** — scores candidate spends per revenue event; auto-matches only when confidence is high *and* unambiguous
- **Stale checker** — flags pending spends that exceed the trust window for manual review

Three spend states: `pending` → `matched` or `stale`.

## Setup

**Requirements:** Python 3.11+, Docker (for Redis)

```bash
# Clone and install
pip install -r requirements.txt

# Start Redis
docker compose up -d

# Optional: copy env file (defaults work out of the box)
cp .env.example .env

# Run the API + background workers
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/status` after ~30 seconds to see matched, pending, and stale counts accumulate.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Redis connectivity check |
| `GET /status` | Counts (`matched`, `pending`, `stale`, `orphan_revenue`), current config, recent matches |
| `GET /events?limit=50` | Recent state transitions with confidence scores |
| `GET /config` | Current thresholds |
| `PATCH /config` | Tune thresholds at runtime (see below) |

Example status response:

```json
{
  "counts": {"matched": 12, "pending": 3, "stale": 2, "orphan_revenue": 1},
  "config": {"match_threshold": 0.75, "stale_after_sec": 120},
  "recent_matches": [{"spend_id": "...", "confidence": 0.91}]
}
```

## Configuration

Set via environment variables (see `app/config.py`) or patch at runtime:

```bash
curl -X PATCH http://127.0.0.1:8000/config \
  -H "Content-Type: application/json" \
  -d '{"ambiguity_margin": 0.05, "stale_after_sec": 150}'
```

| Variable | Default | What it controls |
|----------|---------|------------------|
| `MATCH_THRESHOLD` | 0.75 | Minimum confidence to auto-match |
| `AMBIGUITY_MARGIN` | 0.15 | Required gap between top two candidates |
| `AMOUNT_TOLERANCE_PCT` | 0.15 | How far revenue amount can drift from spend |
| `STALE_AFTER_SEC` | 120 | How long to wait before flagging a spend stale |
| `LOOKBACK_SEC` | 300 | How far back to search for candidate spends |
| `REVENUE_DELAY_MAX_SEC` | 90 | Max simulated revenue delay |

## Tests

```bash
pytest
```

The ambiguity tests in `tests/test_matching_ambiguity.py` reproduce the core failure modes — worth running before demoing.

## The snag: ambiguity vs stale flags

The thing that broke first in this simulator wasn't the scoring formula — it was **ambiguous attribution under similar concurrent spends**.

When two spends of similar amount land within seconds of each other, a single revenue event scores well against both. The `ambiguity_margin` rule correctly refuses to guess, leaving both spends pending. If revenue delay is near the stale window, those spends can flip to `stale` before the matcher ever gets a confident link — even though revenue did arrive.

Tightening `ambiguity_margin` fixes that (one spend auto-matches) but increases false-positive risk: the closer spend wins, not necessarily the right one. Widening `stale_after_sec` buys time but ties up capital longer. There is no free knob — it's the same tradeoff you'd face before financing against unattributed spend.

That tension — **confidence vs capital efficiency vs manual review noise** — is the hard part this simulator is meant to surface.

## Project structure

```
app/
├── main.py              # FastAPI + worker lifespan
├── config.py            # Pydantic settings
├── clock.py             # RealClock / SimClock (tests use SimClock)
├── generators/          # Spend + revenue event loops
├── matching/            # Scoring, matcher, stale checker
├── models/              # Event and reconciliation types
├── store/               # Redis abstraction
└── api/                 # HTTP routes
```
