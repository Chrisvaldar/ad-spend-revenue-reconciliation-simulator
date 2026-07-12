from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class SpendStatus(StrEnum):
    PENDING = "pending"
    MATCHED = "matched"
    STALE = "stale"


class MatchOutcome(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    BELOW_THRESHOLD = "below_threshold"
    NO_CANDIDATES = "no_candidates"
    ORPHAN = "orphan"


class SpendRecord(BaseModel):
    id: UUID
    amount: float = Field(gt=0)
    created_at: float
    status: SpendStatus = SpendStatus.PENDING
    matched_revenue_id: UUID | None = None
    confidence: float | None = None
    revenue_amount: float | None = None


class MatchCandidate(BaseModel):
    spend_id: UUID
    confidence: float = Field(ge=0.0, le=1.0)
    amount_delta_pct: float = Field(ge=0.0)
    elapsed_sec: float = Field(ge=0.0)


class ReconciliationResult(BaseModel):
    revenue_id: UUID
    outcome: MatchOutcome
    spend_id: UUID | None = None
    confidence: float | None = None
    candidates: list[MatchCandidate] = Field(default_factory=list)


class StateTransition(BaseModel):
    timestamp: float
    event_type: str
    spend_id: UUID | None = None
    revenue_id: UUID | None = None
    from_status: SpendStatus | None = None
    to_status: SpendStatus | None = None
    confidence: float | None = None
    detail: str | None = None
