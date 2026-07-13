from __future__ import annotations

import asyncio
import random
from uuid import uuid4

from app.clock import Clock
from app.config import Settings
from app.models.events import RevenueEvent, SpendEvent
from app.store.redis_store import RedisStore


class RevenueGenerator:
    def __init__(
        self,
        store: RedisStore,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self.store = store
        self.settings = settings
        self.clock = clock
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule_for_spend(self, spend: SpendEvent) -> None:
        task = asyncio.create_task(self._emit_revenue(spend))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _emit_revenue(self, spend: SpendEvent) -> None:
        delay = random.uniform(
            self.settings.revenue_delay_min_sec,
            self.settings.revenue_delay_max_sec,
        )
        await self.clock.sleep(delay)

        factor = random.uniform(
            self.settings.revenue_amount_min_factor,
            self.settings.revenue_amount_max_factor,
        )
        event = RevenueEvent(
            id=uuid4(),
            amount=round(spend.amount * factor, 2),
            arrived_at=self.clock.now(),
        )
        await self.store.publish_revenue(event)

    async def wait_for_pending(self) -> None:
        if not self._tasks:
            return
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def cancel_pending(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
