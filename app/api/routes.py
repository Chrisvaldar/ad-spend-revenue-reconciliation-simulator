from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import Settings

router = APIRouter()


class ConfigUpdate(BaseModel):
    match_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    ambiguity_margin: float | None = Field(default=None, ge=0.0, le=1.0)
    amount_tolerance_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    stale_after_sec: float | None = Field(default=None, ge=0.0)
    lookback_sec: float | None = Field(default=None, ge=0.0)
    spend_interval_min_sec: float | None = Field(default=None, ge=0.1)
    spend_interval_max_sec: float | None = Field(default=None, ge=0.1)
    revenue_delay_min_sec: float | None = Field(default=None, ge=0.0)
    revenue_delay_max_sec: float | None = Field(default=None, ge=0.0)


def _public_config(settings: Settings) -> dict[str, float]:
    return {
        "match_threshold": settings.match_threshold,
        "ambiguity_margin": settings.ambiguity_margin,
        "amount_tolerance_pct": settings.amount_tolerance_pct,
        "stale_after_sec": settings.stale_after_sec,
        "lookback_sec": settings.lookback_sec,
        "spend_interval_min_sec": settings.spend_interval_min_sec,
        "spend_interval_max_sec": settings.spend_interval_max_sec,
        "revenue_delay_min_sec": settings.revenue_delay_min_sec,
        "revenue_delay_max_sec": settings.revenue_delay_max_sec,
    }


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    store = request.app.state.store
    try:
        pong = await store.redis.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc
    if pong != "PONG":
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ok"}


@router.get("/status")
async def status(request: Request) -> dict:
    store = request.app.state.store
    settings: Settings = request.app.state.settings
    counts = await store.get_stats()
    events = await store.get_recent_events(limit=50)
    recent_matches = [
        {
            "timestamp": event.timestamp,
            "spend_id": str(event.spend_id) if event.spend_id else None,
            "revenue_id": str(event.revenue_id) if event.revenue_id else None,
            "confidence": event.confidence,
        }
        for event in events
        if event.event_type == "matched"
    ][:10]

    return {
        "counts": counts,
        "config": _public_config(settings),
        "recent_matches": recent_matches,
    }


@router.get("/events")
async def events(request: Request, limit: int = 50) -> dict:
    store = request.app.state.store
    transitions = await store.get_recent_events(limit=limit)
    return {
        "events": [transition.model_dump(mode="json") for transition in transitions],
    }


@router.get("/config")
async def get_config(request: Request) -> dict[str, float]:
    settings: Settings = request.app.state.settings
    return _public_config(settings)


@router.patch("/config")
async def patch_config(update: ConfigUpdate, request: Request) -> dict[str, float]:
    settings: Settings = request.app.state.settings
    for field, value in update.model_dump(exclude_none=True).items():
        setattr(settings, field, value)
    return _public_config(settings)
