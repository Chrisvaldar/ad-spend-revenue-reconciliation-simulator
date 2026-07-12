from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.models.events import RevenueEvent, SpendEvent
from app.models.reconciliation import SpendRecord, SpendStatus, StateTransition

STAT_FIELDS = ("matched", "pending", "stale", "orphan_revenue")


class RedisStore:
    PENDING_KEY = "pending:spends"
    REVENUE_STREAM = "revenue:stream"
    REVENUE_GROUP = "matchers"
    STATS_KEY = "stats"
    EVENTS_LOG_KEY = "events:log"

    def __init__(self, redis: Redis, events_log_max_len: int = 100) -> None:
        self.redis = redis
        self.events_log_max_len = events_log_max_len

    @classmethod
    async def from_url(cls, url: str, events_log_max_len: int = 100) -> RedisStore:
        redis = Redis.from_url(url, decode_responses=True)
        store = cls(redis, events_log_max_len)
        await store.ensure_consumer_group()
        await store.ensure_stats()
        return store

    async def close(self) -> None:
        await self.redis.aclose()

    def _spend_key(self, spend_id: UUID) -> str:
        return f"spend:{spend_id}"

    async def ensure_consumer_group(self) -> None:
        try:
            await self.redis.xgroup_create(
                self.REVENUE_STREAM,
                self.REVENUE_GROUP,
                id="0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def ensure_stats(self) -> None:
        async with self.redis.pipeline(transaction=True) as pipe:
            for field in STAT_FIELDS:
                pipe.hsetnx(self.STATS_KEY, field, 0)
            await pipe.execute()

    async def save_spend(self, event: SpendEvent) -> SpendRecord:
        record = SpendRecord(
            id=event.id,
            amount=event.amount,
            created_at=event.created_at,
            status=SpendStatus.PENDING,
        )
        key = self._spend_key(record.id)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping=self._serialize_spend(record))
            pipe.zadd(self.PENDING_KEY, {str(record.id): record.created_at})
            pipe.hincrby(self.STATS_KEY, "pending", 1)
            await pipe.execute()
        return record

    async def get_spend(self, spend_id: UUID) -> SpendRecord | None:
        data = await self.redis.hgetall(self._spend_key(spend_id))
        if not data:
            return None
        return self._deserialize_spend(data)

    async def list_pending_spends_since(self, min_created_at: float) -> list[SpendRecord]:
        spend_ids = await self.redis.zrangebyscore(
            self.PENDING_KEY,
            min=min_created_at,
            max="+inf",
        )
        records: list[SpendRecord] = []
        for spend_id in spend_ids:
            record = await self.get_spend(UUID(spend_id))
            if record is None or record.status != SpendStatus.PENDING:
                continue
            records.append(record)
        return records

    async def mark_matched(
        self,
        spend_id: UUID,
        revenue_id: UUID,
        confidence: float,
        revenue_amount: float,
    ) -> SpendRecord | None:
        record = await self.get_spend(spend_id)
        if record is None or record.status != SpendStatus.PENDING:
            return record

        record.status = SpendStatus.MATCHED
        record.matched_revenue_id = revenue_id
        record.confidence = confidence
        record.revenue_amount = revenue_amount

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(self._spend_key(spend_id), mapping=self._serialize_spend(record))
            pipe.zrem(self.PENDING_KEY, str(spend_id))
            pipe.hincrby(self.STATS_KEY, "pending", -1)
            pipe.hincrby(self.STATS_KEY, "matched", 1)
            await pipe.execute()
        return record

    async def mark_stale(self, spend_id: UUID) -> SpendRecord | None:
        record = await self.get_spend(spend_id)
        if record is None or record.status != SpendStatus.PENDING:
            return record

        record.status = SpendStatus.STALE

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(self._spend_key(spend_id), mapping=self._serialize_spend(record))
            pipe.zrem(self.PENDING_KEY, str(spend_id))
            pipe.hincrby(self.STATS_KEY, "pending", -1)
            pipe.hincrby(self.STATS_KEY, "stale", 1)
            await pipe.execute()
        return record

    async def list_stale_pending_spends(self, cutoff: float) -> list[SpendRecord]:
        spend_ids = await self.redis.zrangebyscore(
            self.PENDING_KEY,
            min="-inf",
            max=cutoff,
        )
        records: list[SpendRecord] = []
        for spend_id in spend_ids:
            record = await self.get_spend(UUID(spend_id))
            if record is None or record.status != SpendStatus.PENDING:
                continue
            records.append(record)
        return records

    async def publish_revenue(self, event: RevenueEvent) -> str:
        return await self.redis.xadd(
            self.REVENUE_STREAM,
            {
                "event_id": str(event.id),
                "amount": str(event.amount),
                "arrived_at": str(event.arrived_at),
            },
        )

    async def read_revenue_batch(
        self,
        consumer: str,
        count: int = 10,
        block_ms: int = 1000,
    ) -> list[tuple[str, RevenueEvent]]:
        response = await self.redis.xreadgroup(
            groupname=self.REVENUE_GROUP,
            consumername=consumer,
            streams={self.REVENUE_STREAM: ">"},
            count=count,
            block=block_ms,
        )
        if not response:
            return []

        events: list[tuple[str, RevenueEvent]] = []
        for _stream, entries in response:
            for stream_id, fields in entries:
                events.append(
                    (
                        stream_id,
                        RevenueEvent(
                            id=UUID(fields["event_id"]),
                            amount=float(fields["amount"]),
                            arrived_at=float(fields["arrived_at"]),
                        ),
                    )
                )
        return events

    async def ack_revenue(self, stream_id: str) -> None:
        await self.redis.xack(self.REVENUE_STREAM, self.REVENUE_GROUP, stream_id)

    async def increment_orphan_revenue(self) -> None:
        await self.redis.hincrby(self.STATS_KEY, "orphan_revenue", 1)

    async def get_stats(self) -> dict[str, int]:
        raw = await self.redis.hgetall(self.STATS_KEY)
        return {field: int(raw.get(field, 0)) for field in STAT_FIELDS}

    async def log_transition(self, transition: StateTransition) -> None:
        payload = transition.model_dump(mode="json")
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.lpush(self.EVENTS_LOG_KEY, json.dumps(payload))
            pipe.ltrim(self.EVENTS_LOG_KEY, 0, self.events_log_max_len - 1)
            await pipe.execute()

    async def get_recent_events(self, limit: int = 50) -> list[StateTransition]:
        raw_events = await self.redis.lrange(self.EVENTS_LOG_KEY, 0, limit - 1)
        transitions: list[StateTransition] = []
        for raw in raw_events:
            data = json.loads(raw)
            transitions.append(StateTransition.model_validate(data))
        return transitions

    def _serialize_spend(self, record: SpendRecord) -> dict[str, str]:
        data: dict[str, Any] = {
            "id": str(record.id),
            "amount": record.amount,
            "created_at": record.created_at,
            "status": record.status.value,
            "matched_revenue_id": record.matched_revenue_id,
            "confidence": record.confidence,
            "revenue_amount": record.revenue_amount,
        }
        return {
            key: "" if value is None else str(value)
            for key, value in data.items()
        }

    def _deserialize_spend(self, data: dict[str, str]) -> SpendRecord:
        return SpendRecord(
            id=UUID(data["id"]),
            amount=float(data["amount"]),
            created_at=float(data["created_at"]),
            status=SpendStatus(data["status"]),
            matched_revenue_id=UUID(data["matched_revenue_id"])
            if data.get("matched_revenue_id")
            else None,
            confidence=float(data["confidence"]) if data.get("confidence") else None,
            revenue_amount=float(data["revenue_amount"])
            if data.get("revenue_amount")
            else None,
        )
