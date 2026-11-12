"""Budget request and exact-percentage unit tests."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.financial import MAX_SAFE_PAISE
from app.models import Budget
from app.schemas.budgets import BudgetCreateRequest, BudgetUpdateRequest
from app.services.budgets import BudgetSnapshot


def _payload(**overrides):
    values = {
        "month_start": "2026-02-01",
        "category_id": None,
        "limit_paise": 10_000,
    }
    values.update(overrides)
    return values


def test_budget_schema_accepts_overall_and_category_budgets():
    overall = BudgetCreateRequest(**_payload())
    category = BudgetCreateRequest(**_payload(category_id=str(uuid4())))

    assert overall.category_id is None
    assert overall.month_start == date(2026, 2, 1)
    assert category.category_id is not None


@pytest.mark.parametrize("amount", [0, -1, True, 1.5, "100", MAX_SAFE_PAISE + 1])
def test_budget_schema_rejects_invalid_amounts(amount):
    with pytest.raises(ValidationError):
        BudgetCreateRequest(**_payload(limit_paise=amount))


@pytest.mark.parametrize("month_start", ["2026-02-02", "2026-02-28"])
def test_budget_schema_requires_first_day_of_month(month_start):
    with pytest.raises(ValidationError, match="first day"):
        BudgetCreateRequest(**_payload(month_start=month_start))


def test_budget_update_schema_requires_at_least_one_known_change():
    with pytest.raises(ValidationError):
        BudgetUpdateRequest()
    with pytest.raises(ValidationError):
        BudgetUpdateRequest(user_id=str(uuid4()))

    update = BudgetUpdateRequest(category_id=None)
    assert update.model_dump(exclude_unset=True) == {"category_id": None}


@pytest.mark.parametrize(
    ("actual", "limit", "expected_basis_points"),
    [
        (0, 100, 0),
        (100, 100, 10_000),
        (125, 100, 12_500),
        (1, 3, 3_333),
        (2, 3, 6_667),
    ],
)
def test_percentage_used_is_integer_basis_points(actual, limit, expected_basis_points):
    budget = Budget(limit_paise=limit)
    snapshot = BudgetSnapshot(
        budget=budget,
        category_name=None,
        actual_spending_paise=actual,
    )

    assert snapshot.percent_used_basis_points == expected_basis_points
    assert snapshot.remaining_paise == limit - actual
