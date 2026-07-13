from uuid import uuid4

import pytest

from app.config import Settings
from app.matching.engine import MatchingEngine
from app.matching.stale_checker import StaleChecker
from app.models.events import RevenueEvent, SpendEvent
from app.models.reconciliation import MatchOutcome, SpendStatus
from app.store.redis_store import RedisStore


@pytest.mark.asyncio
async def test_similar_concurrent_spends_block_auto_match(
    redis_store: RedisStore,
    matching_engine: MatchingEngine,
) -> None:
    spend_a = uuid4()
    spend_b = uuid4()
    revenue_id = uuid4()

    await redis_store.save_spend(
        SpendEvent(id=spend_a, amount=100.0, created_at=1000.0)
    )
    await redis_store.save_spend(
        SpendEvent(id=spend_b, amount=100.0, created_at=1020.0)
    )

    result = await matching_engine.reconcile_revenue(
        RevenueEvent(id=revenue_id, amount=97.0, arrived_at=1030.0)
    )

    assert result.outcome == MatchOutcome.AMBIGUOUS
    assert len(result.candidates) == 2
    assert result.spend_id is None

    spend_a_record = await redis_store.get_spend(spend_a)
    spend_b_record = await redis_store.get_spend(spend_b)
    assert spend_a_record is not None
    assert spend_b_record is not None
    assert spend_a_record.status == SpendStatus.PENDING
    assert spend_b_record.status == SpendStatus.PENDING

    stats = await redis_store.get_stats()
    assert stats["orphan_revenue"] == 1
    assert stats["matched"] == 0
    assert stats["pending"] == 2


@pytest.mark.asyncio
async def test_tightening_ambiguity_margin_allows_match(
    redis_store: RedisStore,
    settings: Settings,
    sim_clock,
) -> None:
    settings.ambiguity_margin = 0.05
    matching_engine = MatchingEngine(redis_store, settings, sim_clock)

    spend_a = uuid4()
    spend_b = uuid4()
    revenue_id = uuid4()

    await redis_store.save_spend(
        SpendEvent(id=spend_a, amount=100.0, created_at=1000.0)
    )
    await redis_store.save_spend(
        SpendEvent(id=spend_b, amount=100.0, created_at=1020.0)
    )

    result = await matching_engine.reconcile_revenue(
        RevenueEvent(id=revenue_id, amount=97.0, arrived_at=1030.0)
    )

    assert result.outcome == MatchOutcome.MATCHED
    assert result.spend_id == spend_b

    matched = await redis_store.get_spend(spend_b)
    still_pending = await redis_store.get_spend(spend_a)
    assert matched is not None
    assert still_pending is not None
    assert matched.status == SpendStatus.MATCHED
    assert still_pending.status == SpendStatus.PENDING


@pytest.mark.asyncio
async def test_late_revenue_arrives_after_spend_goes_stale(
    redis_store: RedisStore,
    matching_engine: MatchingEngine,
    settings: Settings,
    sim_clock,
) -> None:
    spend_id = uuid4()
    revenue_id = uuid4()
    stale_checker = StaleChecker(redis_store, settings, sim_clock)

    await redis_store.save_spend(
        SpendEvent(id=spend_id, amount=100.0, created_at=1000.0)
    )

    sim_clock.advance(settings.stale_after_sec + 1)
    marked = await stale_checker.check_once()

    assert marked == 1
    stale_spend = await redis_store.get_spend(spend_id)
    assert stale_spend is not None
    assert stale_spend.status == SpendStatus.STALE

    result = await matching_engine.reconcile_revenue(
        RevenueEvent(id=revenue_id, amount=97.0, arrived_at=sim_clock.now())
    )

    assert result.outcome == MatchOutcome.NO_CANDIDATES

    stats = await redis_store.get_stats()
    assert stats["stale"] == 1
    assert stats["pending"] == 0
    assert stats["orphan_revenue"] == 1
    assert stats["matched"] == 0


@pytest.mark.asyncio
async def test_stale_spend_and_ambiguous_revenue_compound_failure(
    redis_store: RedisStore,
    matching_engine: MatchingEngine,
    settings: Settings,
    sim_clock,
) -> None:
    spend_a = uuid4()
    spend_b = uuid4()
    revenue_id = uuid4()
    stale_checker = StaleChecker(redis_store, settings, sim_clock)

    await redis_store.save_spend(
        SpendEvent(id=spend_a, amount=100.0, created_at=880.0)
    )
    await redis_store.save_spend(
        SpendEvent(id=spend_b, amount=100.0, created_at=1020.0)
    )

    sim_clock.advance(settings.stale_after_sec + 1)
    await stale_checker.check_once()

    stale_spend = await redis_store.get_spend(spend_a)
    pending_spend = await redis_store.get_spend(spend_b)
    assert stale_spend is not None
    assert pending_spend is not None
    assert stale_spend.status == SpendStatus.STALE
    assert pending_spend.status == SpendStatus.PENDING

    result = await matching_engine.reconcile_revenue(
        RevenueEvent(id=revenue_id, amount=100.0, arrived_at=1030.0)
    )

    assert result.outcome == MatchOutcome.MATCHED
    assert result.spend_id == spend_b

    stats = await redis_store.get_stats()
    assert stats["stale"] == 1
    assert stats["matched"] == 1
    assert stats["pending"] == 0
