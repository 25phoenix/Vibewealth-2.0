"""Savings-goal and append-only allocation ledger API schemas."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.financial import MAX_SAFE_PAISE, financial_today


class GoalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    target_paise: int = Field(strict=True, gt=0, le=MAX_SAFE_PAISE)
    target_date: date | None = None

    @field_validator("target_date")
    @classmethod
    def target_date_is_not_past(cls, value: date | None) -> date | None:
        if value is not None and value < financial_today():
            raise ValueError("target_date cannot be in the past")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value or None


class GoalUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    target_paise: int | None = Field(
        default=None, strict=True, gt=0, le=MAX_SAFE_PAISE
    )
    target_date: date | None = None

    @field_validator("target_date")
    @classmethod
    def target_date_is_not_past(cls, value: date | None) -> date | None:
        if value is not None and value < financial_today():
            raise ValueError("target_date cannot be in the past")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def require_a_change(self) -> "GoalUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one goal field must be supplied")
        return self


class GoalEntryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    amount_paise: int = Field(strict=True, gt=0, le=MAX_SAFE_PAISE)


class GoalAccountAllocationResponse(BaseModel):
    account_id: UUID
    allocated_paise: int


class GoalResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    target_paise: int
    target_date: date | None
    allocated_paise: int
    remaining_target_paise: int
    account_allocations: list[GoalAccountAllocationResponse]
    created_at: datetime
    updated_at: datetime


class GoalPageResponse(BaseModel):
    items: list[GoalResponse]
    total: int
    offset: int
    limit: int


class GoalEntryResponse(BaseModel):
    id: UUID
    goal_id: UUID
    account_id: UUID
    entry_type: str
    amount_paise: int
    effective_date: date
    created_at: datetime


class GoalEntryPageResponse(BaseModel):
    items: list[GoalEntryResponse]
    total: int
    offset: int
    limit: int


class GoalAccountSummaryResponse(BaseModel):
    account_id: UUID
    balance_paise: int
    goal_allocated_paise: int
    available_to_spend_paise: int


class GoalEntryMutationResponse(BaseModel):
    entry: GoalEntryResponse
    goal: GoalResponse
    account: GoalAccountSummaryResponse
