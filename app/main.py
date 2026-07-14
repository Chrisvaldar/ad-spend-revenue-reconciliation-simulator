from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.routes import router
from app.clock import RealClock
from app.config import Settings
from app.generators.revenue import RevenueGenerator
from app.generators.spend import SpendGenerator
from app.matching.engine import MatchingEngine
from app.matching.stale_checker import StaleChecker
from app.models.events import SpendEvent
from app.store.redis_store import RedisStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    clock = RealClock()
    store = await RedisStore.from_url(
        settings.redis_url,
        events_log_max_len=settings.events_log_max_len,
    )
    revenue_generator = RevenueGenerator(store, settings, clock)

    async def on_spend(spend: SpendEvent) -> None:
        revenue_generator.schedule_for_spend(spend)

    spend_generator = SpendGenerator(store, settings, clock, on_spend=on_spend)
    matcher = MatchingEngine(store, settings, clock)
    stale_checker = StaleChecker(store, settings, clock)

    app.state.store = store
    app.state.settings = settings
    app.state.clock = clock

    worker_tasks = [
        asyncio.create_task(spend_generator.run(), name="spend-generator"),
        asyncio.create_task(matcher.run(), name="matcher"),
        asyncio.create_task(stale_checker.run(), name="stale-checker"),
    ]

    try:
        yield
    finally:
        spend_generator.stop()
        matcher.stop()
        stale_checker.stop()
        revenue_generator.cancel_pending()

        for task in worker_tasks:
            task.cancel()
        await asyncio.gather(*worker_tasks, return_exceptions=True)
        await store.close()


app = FastAPI(
    title="Ad Spend / Revenue Reconciliation Simulator",
    lifespan=lifespan,
)
app.include_router(router)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
