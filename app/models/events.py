from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class SpendEvent(BaseModel):
    id: UUID
    amount: float = Field(gt=0)
    created_at: float


class RevenueEvent(BaseModel):
    id: UUID
    amount: float = Field(gt=0)
    arrived_at: float
