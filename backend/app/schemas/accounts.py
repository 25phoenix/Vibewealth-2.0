"""Account request and response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.financial import MAX_SAFE_PAISE

AccountType = Literal["cash", "bank", "wallet"]


class AccountUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    account_type: AccountType | None = None
    opening_balance_paise: int | None = Field(
        default=None, strict=True, ge=0, le=MAX_SAFE_PAISE
    )
    opening_balance_as_of: date | None = None

    @model_validator(mode="after")
    def require_a_change(self) -> "AccountUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one account field must be supplied")
        return self


class AccountResponse(BaseModel):
    id: UUID
    name: str
    account_type: AccountType
    is_default: bool
    opening_balance_paise: int
    opening_balance_as_of: date
    balance_paise: int
    created_at: datetime
    updated_at: datetime


class AccountBalanceResponse(BaseModel):
    account_id: UUID
    balance_paise: int
    as_of: date
