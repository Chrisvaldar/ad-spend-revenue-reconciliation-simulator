from collections.abc import AsyncIterator

import fakeredis.aioredis
import pytest
import pytest_asyncio

from app.clock import SimClock
from app.config import Settings
from app.matching.engine import MatchingEngine
from app.store.redis_store import RedisStore


@pytest.fixture
def sim_clock() -> SimClock:
    return SimClock(start=1000.0)


@pytest.fixture
def settings() -> Settings:
    return Settings(stale_after_sec=120.0, lookback_sec=300.0)


@pytest_asyncio.fixture
async def redis_store(settings: Settings) -> AsyncIterator[RedisStore]:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisStore(redis, events_log_max_len=settings.events_log_max_len)
    await store.ensure_consumer_group()
    await store.ensure_stats()
    yield store
    await store.close()


@pytest_asyncio.fixture
async def matching_engine(
    redis_store: RedisStore,
    settings: Settings,
    sim_clock: SimClock,
) -> MatchingEngine:
    return MatchingEngine(redis_store, settings, sim_clock)
