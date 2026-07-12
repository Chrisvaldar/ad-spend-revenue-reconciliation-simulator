from __future__ import annotations

from uuid import UUID

from app.clock import Clock
from app.config import Settings
from app.matching.scoring import amount_delta_pct, confidence
from app.models.events import RevenueEvent
from app.models.reconciliation import (
    MatchCandidate,
    MatchOutcome,
    ReconciliationResult,
    SpendRecord,
    SpendStatus,
    StateTransition,
)
from app.store.redis_store import RedisStore


class MatchingEngine:
    def __init__(
        self,
        store: RedisStore,
        settings: Settings,
        clock: Clock,
        consumer_name: str = "matcher-1",
    ) -> None:
        self.store = store
        self.settings = settings
        self.clock = clock
        self.consumer_name = consumer_name
        self._running = False

    def build_candidates(
        self,
        revenue: RevenueEvent,
        pending_spends: list[SpendRecord],
    ) -> list[MatchCandidate]:
        candidates: list[MatchCandidate] = []

        for spend in pending_spends:
            if spend.created_at > revenue.arrived_at:
                continue

            delta = amount_delta_pct(spend.amount, revenue.amount)
            if delta >= self.settings.amount_tolerance_pct:
                continue

            elapsed = revenue.arrived_at - spend.created_at
            score = confidence(
                spend.amount,
                revenue.amount,
                elapsed,
                self.settings,
            )
            if score <= 0:
                continue

            candidates.append(
                MatchCandidate(
                    spend_id=spend.id,
                    confidence=score,
                    amount_delta_pct=delta,
                    elapsed_sec=elapsed,
                )
            )

        candidates.sort(key=lambda candidate: candidate.confidence, reverse=True)
        return candidates

    def decide_match(
        self,
        revenue_id: UUID,
        candidates: list[MatchCandidate],
    ) -> ReconciliationResult:
        if not candidates:
            return ReconciliationResult(
                revenue_id=revenue_id,
                outcome=MatchOutcome.NO_CANDIDATES,
            )

        best = candidates[0]
        second_best = candidates[1] if len(candidates) > 1 else None

        if best.confidence < self.settings.match_threshold:
            return ReconciliationResult(
                revenue_id=revenue_id,
                outcome=MatchOutcome.BELOW_THRESHOLD,
                candidates=candidates,
            )

        if second_best is not None:
            margin = best.confidence - second_best.confidence
            if margin < self.settings.ambiguity_margin:
                return ReconciliationResult(
                    revenue_id=revenue_id,
                    outcome=MatchOutcome.AMBIGUOUS,
                    candidates=candidates,
                )

        return ReconciliationResult(
            revenue_id=revenue_id,
            outcome=MatchOutcome.MATCHED,
            spend_id=best.spend_id,
            confidence=best.confidence,
            candidates=candidates,
        )

    async def reconcile_revenue(self, revenue: RevenueEvent) -> ReconciliationResult:
        min_created_at = revenue.arrived_at - self.settings.lookback_sec
        pending_spends = await self.store.list_pending_spends_since(min_created_at)
        candidates = self.build_candidates(revenue, pending_spends)
        result = self.decide_match(revenue.id, candidates)
        now = self.clock.now()

        if result.outcome == MatchOutcome.MATCHED:
            assert result.spend_id is not None
            assert result.confidence is not None
            await self.store.mark_matched(
                result.spend_id,
                revenue.id,
                result.confidence,
                revenue.amount,
            )
            await self.store.log_transition(
                StateTransition(
                    timestamp=now,
                    event_type="matched",
                    spend_id=result.spend_id,
                    revenue_id=revenue.id,
                    from_status=SpendStatus.PENDING,
                    to_status=SpendStatus.MATCHED,
                    confidence=result.confidence,
                )
            )
            return result

        await self.store.increment_orphan_revenue()
        await self.store.log_transition(
            StateTransition(
                timestamp=now,
                event_type=result.outcome.value,
                revenue_id=revenue.id,
                confidence=candidates[0].confidence if candidates else None,
                detail=f"candidate_count={len(candidates)}",
            )
        )
        return result

    async def process_batch(self) -> int:
        batch = await self.store.read_revenue_batch(
            self.consumer_name,
            count=10,
            block_ms=1000,
        )
        processed = 0
        for stream_id, revenue in batch:
            await self.reconcile_revenue(revenue)
            await self.store.ack_revenue(stream_id)
            processed += 1
        return processed

    async def run(self) -> None:
        self._running = True
        while self._running:
            await self.process_batch()

    def stop(self) -> None:
        self._running = False
