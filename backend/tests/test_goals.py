"""Savings-goal and append-only ledger request validation tests."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.core.financial import MAX_SAFE_PAISE, financial_today
from app.schemas.goals import (
    GoalCreateRequest,
    GoalEntryCreateRequest,
    GoalUpdateRequest,
)


def _goal_payload(**overrides):
    payload = {"name": "Emergency fund", "target_paise": 100_000}
    payload.update(overrides)
    return payload


def test_goal_schema_accepts_optional_description_and_future_target_date():
    goal = GoalCreateRequest(
        **_goal_payload(
            description="  Home repairs  ",
            target_date=(financial_today() + timedelta(days=1)).isoformat(),
        )
    )

    assert goal.description == "Home repairs"
    assert goal.target_date == financial_today() + timedelta(days=1)


@pytest.mark.parametrize(
    "amount", [0, -1, True, 1.0, "100", MAX_SAFE_PAISE + 1]
)
def test_goal_schema_rejects_invalid_target_amounts(amount):
    with pytest.raises(ValidationError):
        GoalCreateRequest(**_goal_payload(target_paise=amount))


def test_goal_schema_accepts_maximum_safe_target_amount():
    goal = GoalCreateRequest(**_goal_payload(target_paise=MAX_SAFE_PAISE))

    assert goal.target_paise == MAX_SAFE_PAISE


def test_goal_schema_rejects_past_or_malformed_target_date():
    yesterday = financial_today() - timedelta(days=1)
    with pytest.raises(ValidationError, match="past"):
        GoalCreateRequest(**_goal_payload(target_date=yesterday.isoformat()))
    with pytest.raises(ValidationError):
        GoalCreateRequest(**_goal_payload(target_date="2026-02-30"))


def test_goal_update_allows_clearing_date_but_forbids_unapproved_fields():
    update = GoalUpdateRequest(target_date=None, description=None)

    assert update.model_dump(exclude_unset=True) == {
        "description": None,
        "target_date": None,
    }
    with pytest.raises(ValidationError):
        GoalUpdateRequest()
    with pytest.raises(ValidationError):
        GoalUpdateRequest(user_id="00000000-0000-0000-0000-000000000001")
    with pytest.raises(ValidationError):
        GoalUpdateRequest(deleted_at=None)


def test_goal_entry_request_accepts_only_account_and_positive_safe_paise():
    request = GoalEntryCreateRequest(
        account_id="00000000-0000-0000-0000-000000000001",
        amount_paise=MAX_SAFE_PAISE,
    )
    assert request.amount_paise == MAX_SAFE_PAISE

    for invalid in (0, -1, True, 1.0, "100", MAX_SAFE_PAISE + 1):
        with pytest.raises(ValidationError):
            GoalEntryCreateRequest(
                account_id="00000000-0000-0000-0000-000000000001",
                amount_paise=invalid,
            )

    with pytest.raises(ValidationError):
        GoalEntryCreateRequest(
            account_id="00000000-0000-0000-0000-000000000001",
            amount_paise=100,
            entry_type="withdrawal",
        )
