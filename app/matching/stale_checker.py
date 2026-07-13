from __future__ import annotations

from app.clock import Clock
from app.config import Settings
from app.models.reconciliation import SpendStatus, StateTransition
from app.store.redis_store import RedisStore


class StaleChecker:
    def __init__(
        self,
        store: RedisStore,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self.store = store
        self.settings = settings
        self.clock = clock
        self._running = False

    async def check_once(self) -> int:
        now = self.clock.now()
        cutoff = now - self.settings.stale_after_sec
        expired_spends = await self.store.list_stale_pending_spends(cutoff)
        marked = 0

        for spend in expired_spends:
            updated = await self.store.mark_stale(spend.id)
            if updated is None or updated.status != SpendStatus.STALE:
                continue

            marked += 1
            await self.store.log_transition(
                StateTransition(
                    timestamp=now,
                    event_type="stale",
                    spend_id=spend.id,
                    from_status=SpendStatus.PENDING,
                    to_status=SpendStatus.STALE,
                    detail=(
                        f"waited {now - spend.created_at:.1f}s "
                        f"(limit {self.settings.stale_after_sec}s)"
                    ),
                )
            )

        return marked

    async def run(self) -> None:
        self._running = True
        while self._running:
            await self.check_once()
            await self.clock.sleep(self.settings.stale_check_interval_sec)

    def stop(self) -> None:
        self._running = False
