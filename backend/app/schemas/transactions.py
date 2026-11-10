"""Transaction request and response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.financial import MAX_SAFE_PAISE

TransactionType = Literal["income", "expense"]


class TransactionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    account_id: UUID
    category_id: UUID
    transaction_type: TransactionType
    amount_paise: int = Field(strict=True, gt=0, le=MAX_SAFE_PAISE)
    description: str = Field(min_length=1, max_length=120)
    transaction_date: date
    notes: str | None = Field(default=None, max_length=4000)


class TransactionResponse(BaseModel):
    id: UUID
    account_id: UUID
    category_id: UUID | None
    category_name: str | None
    transaction_type: TransactionType
    amount_paise: int
    description: str
    transaction_date: date
    notes: str | None
    created_at: datetime
    updated_at: datetime


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    offset: int
    limit: int
