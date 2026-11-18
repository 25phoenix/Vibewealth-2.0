"""Authenticated dashboard summary response contracts."""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, StrictStr


class DashboardAccountTotals(BaseModel):
    account_count: int
    balance_paise: StrictStr
    goal_allocated_paise: StrictStr
    available_to_spend_paise: StrictStr


class DashboardCashFlow(BaseModel):
    income_paise: StrictStr
    expenses_paise: StrictStr
    net_paise: StrictStr


class DashboardBudget(BaseModel):
    id: UUID
    month_start: date
    category_id: UUID | None
    category_name: str | None
    limit_paise: int
    actual_spending_paise: StrictStr
    remaining_paise: StrictStr
    percent_used_basis_points: StrictStr


class DashboardGoal(BaseModel):
    id: UUID
    name: str
    target_date: date | None
    target_paise: int
    allocated_paise: int
    remaining_target_paise: int


class DashboardTransaction(BaseModel):
    id: UUID
    account_id: UUID
    category_id: UUID | None
    category_name: str | None
    transaction_type: Literal["income", "expense"]
    amount_paise: int
    description: str
    transaction_date: date


class DashboardTransactionPage(BaseModel):
    items: list[DashboardTransaction]
    total: int
    offset: int
    limit: int


class DashboardSummaryResponse(BaseModel):
    financial_date: date
    month_start: date
    month_end_exclusive: date
    account_totals: DashboardAccountTotals
    cash_flow: DashboardCashFlow
    budgets: list[DashboardBudget]
    goals: list[DashboardGoal]
    goals_total: int
    recent_transactions: DashboardTransactionPage
