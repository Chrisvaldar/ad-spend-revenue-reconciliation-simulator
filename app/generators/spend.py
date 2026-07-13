from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from uuid import uuid4

from app.clock import Clock
from app.config import Settings
from app.models.events import SpendEvent
from app.store.redis_store import RedisStore

OnSpendCallback = Callable[[SpendEvent], Awaitable[None]]


class SpendGenerator:
    def __init__(
        self,
        store: RedisStore,
        settings: Settings,
        clock: Clock,
        on_spend: OnSpendCallback | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.clock = clock
        self.on_spend = on_spend
        self._running = False

    async def emit_once(self) -> SpendEvent:
        event = SpendEvent(
            id=uuid4(),
            amount=round(random.uniform(50.0, 500.0), 2),
            created_at=self.clock.now(),
        )
        await self.store.save_spend(event)
        if self.on_spend is not None:
            await self.on_spend(event)
        return event

    async def run(self) -> None:
        self._running = True
        while self._running:
            await self.emit_once()
            delay = random.uniform(
                self.settings.spend_interval_min_sec,
                self.settings.spend_interval_max_sec,
            )
            await self.clock.sleep(delay)

    def stop(self) -> None:
        self._running = False
