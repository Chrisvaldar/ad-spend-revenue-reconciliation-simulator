from uuid import uuid4

import pytest

from app.matching.engine import MatchingEngine
from app.models.events import RevenueEvent, SpendEvent
from app.models.reconciliation import MatchCandidate, MatchOutcome, SpendStatus
from app.store.redis_store import RedisStore


def test_decide_match_selects_confident_candidate(
    matching_engine: MatchingEngine,
) -> None:
    spend_id = uuid4()
    revenue_id = uuid4()
    candidates = [
        MatchCandidate(
            spend_id=spend_id,
            confidence=0.92,
            amount_delta_pct=0.02,
            elapsed_sec=10.0,
        )
    ]

    result = matching_engine.decide_match(revenue_id, candidates)

    assert result.outcome == MatchOutcome.MATCHED
    assert result.spend_id == spend_id
    assert result.confidence == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_reconcile_revenue_matches_pending_spend(
    redis_store: RedisStore,
    matching_engine: MatchingEngine,
) -> None:
    spend_id = uuid4()
    revenue_id = uuid4()
    await redis_store.save_spend(
        SpendEvent(id=spend_id, amount=100.0, created_at=1000.0)
    )

    result = await matching_engine.reconcile_revenue(
        RevenueEvent(id=revenue_id, amount=100.0, arrived_at=1010.0)
    )

    assert result.outcome == MatchOutcome.MATCHED
    assert result.spend_id == spend_id

    spend = await redis_store.get_spend(spend_id)
    assert spend is not None
    assert spend.status == SpendStatus.MATCHED
    assert spend.matched_revenue_id == revenue_id

    stats = await redis_store.get_stats()
    assert stats["matched"] == 1
    assert stats["pending"] == 0
    assert stats["orphan_revenue"] == 0


@pytest.mark.asyncio
async def test_reconcile_revenue_orphans_when_no_candidates(
    redis_store: RedisStore,
    matching_engine: MatchingEngine,
) -> None:
    revenue_id = uuid4()

    result = await matching_engine.reconcile_revenue(
        RevenueEvent(id=revenue_id, amount=50.0, arrived_at=1000.0)
    )

    assert result.outcome == MatchOutcome.NO_CANDIDATES

    stats = await redis_store.get_stats()
    assert stats["orphan_revenue"] == 1
    assert stats["matched"] == 0


@pytest.mark.asyncio
async def test_reconcile_revenue_rejects_below_threshold(
    redis_store: RedisStore,
    matching_engine: MatchingEngine,
) -> None:
    spend_id = uuid4()
    revenue_id = uuid4()
    await redis_store.save_spend(
        SpendEvent(id=spend_id, amount=100.0, created_at=1000.0)
    )

    result = await matching_engine.reconcile_revenue(
        RevenueEvent(id=revenue_id, amount=97.0, arrived_at=1100.0)
    )

    assert result.outcome == MatchOutcome.BELOW_THRESHOLD

    spend = await redis_store.get_spend(spend_id)
    assert spend is not None
    assert spend.status == SpendStatus.PENDING

    stats = await redis_store.get_stats()
    assert stats["orphan_revenue"] == 1
    assert stats["pending"] == 1
    assert stats["matched"] == 0
