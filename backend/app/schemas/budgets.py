"""Monthly budget request and response schemas."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.financial import MAX_SAFE_PAISE


class BudgetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month_start: date
    category_id: UUID | None = None
    limit_paise: int = Field(strict=True, gt=0, le=MAX_SAFE_PAISE)

    @field_validator("month_start")
    @classmethod
    def require_first_day(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError("month_start must be the first day of a month")
        return value


class BudgetUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month_start: date | None = None
    category_id: UUID | None = None
    limit_paise: int | None = Field(default=None, strict=True, gt=0, le=MAX_SAFE_PAISE)

    @field_validator("month_start")
    @classmethod
    def require_first_day(cls, value: date | None) -> date | None:
        if value is not None and value.day != 1:
            raise ValueError("month_start must be the first day of a month")
        return value

    @model_validator(mode="after")
    def require_a_change(self) -> "BudgetUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one budget field must be supplied")
        return self


class BudgetResponse(BaseModel):
    id: UUID
    month_start: date
    category_id: UUID | None
    category_name: str | None
    limit_paise: int
    actual_spending_paise: str
    remaining_paise: str
    percent_used_basis_points: str
    created_at: datetime
    updated_at: datetime
