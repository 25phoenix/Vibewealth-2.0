"""Dashboard response precision and Asia/Kolkata period tests."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core import financial
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard import dashboard_month_range


def _summary(**overrides):
    value = {
        "financial_date": "2026-12-01",
        "month_start": "2026-12-01",
        "month_end_exclusive": "2027-01-01",
        "account_totals": {
            "account_count": 1,
            "balance_paise": "9007199254741991",
            "goal_allocated_paise": "5000",
            "available_to_spend_paise": "9007199254736991",
        },
        "cash_flow": {
            "income_paise": "1000",
            "expenses_paise": "10000",
            "net_paise": "-9000",
        },
        "budgets": [{
            "id": str(uuid4()),
            "month_start": "2026-12-01",
            "category_id": None,
            "category_name": None,
            "limit_paise": 8000,
            "actual_spending_paise": "10000",
            "remaining_paise": "-2000",
            "percent_used_basis_points": "12500",
        }],
        "goals": [{
            "id": str(uuid4()),
            "name": "Emergency fund",
            "target_date": None,
            "target_paise": 4000,
            "allocated_paise": 5000,
            "remaining_target_paise": -1000,
        }],
        "goals_total": 1,
        "recent_transactions": {"items": [], "total": 0, "offset": 0, "limit": 4},
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize(
    ("day", "expected_start", "expected_end"),
    [
        (date(2026, 2, 28), date(2026, 2, 1), date(2026, 3, 1)),
        (date(2026, 12, 31), date(2026, 12, 1), date(2027, 1, 1)),
        (date(2027, 1, 1), date(2027, 1, 1), date(2027, 2, 1)),
    ],
)
def test_dashboard_month_range_uses_first_day_and_exclusive_next_month(day, expected_start, expected_end):
    assert dashboard_month_range(day) == (expected_start, expected_end)


@pytest.mark.parametrize(
    ("utc_time", "expected_day"),
    [
        (datetime(2026, 11, 30, 18, 29, tzinfo=timezone.utc), date(2026, 11, 30)),
        (datetime(2026, 11, 30, 18, 30, tzinfo=timezone.utc), date(2026, 12, 1)),
        (datetime(2026, 12, 31, 18, 30, tzinfo=timezone.utc), date(2027, 1, 1)),
    ],
)
def test_financial_today_uses_asia_kolkata_at_month_and_year_boundaries(monkeypatch, utc_time, expected_day):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return utc_time.astimezone(tz) if tz else utc_time.replace(tzinfo=None)

    monkeypatch.setattr(financial, "datetime", FrozenDateTime)
    assert financial.financial_today() == expected_day


def test_dashboard_response_preserves_exact_aggregate_strings_negative_net_and_overfunded_goals():
    summary = DashboardSummaryResponse.model_validate(_summary())
    assert summary.account_totals.balance_paise == "9007199254741991"
    assert summary.cash_flow.net_paise == "-9000"
    assert summary.budgets[0].remaining_paise == "-2000"
    assert summary.goals[0].remaining_target_paise == -1000


def test_dashboard_response_rejects_numeric_aggregate_coercion():
    value = _summary()
    value["account_totals"]["balance_paise"] = 9007199254741991
    with pytest.raises(ValidationError):
        DashboardSummaryResponse.model_validate(value)
