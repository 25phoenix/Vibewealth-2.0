"""Account request validation and service-boundary unit tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.core.financial import MAX_SAFE_PAISE
from app.schemas.accounts import AccountUpdateRequest
from app.services.accounts import InvalidAccountUpdateError, update_account


def test_account_patch_schema_accepts_only_permitted_fields():
    request = AccountUpdateRequest(name="  Everyday  ", account_type="wallet")

    assert request.model_dump(exclude_unset=True) == {
        "name": "Everyday",
        "account_type": "wallet",
    }
    with pytest.raises(ValidationError):
        AccountUpdateRequest(is_default=False)
    with pytest.raises(ValidationError):
        AccountUpdateRequest()
    with pytest.raises(ValidationError):
        AccountUpdateRequest(name="  ")
    with pytest.raises(ValidationError):
        AccountUpdateRequest(opening_balance_paise=MAX_SAFE_PAISE + 1)


@pytest.mark.parametrize("invalid_value", [True, 1.0, "100", -1, MAX_SAFE_PAISE + 1])
def test_opening_balance_service_rejects_non_integer_or_unsafe_paise(invalid_value):
    db = Mock()
    account = Mock(
        id="account-id",
        user_id="user-id",
        opening_balance_paise=0,
        opening_balance_as_of=date(2026, 1, 1),
        archived_at=None,
    )
    db.scalar.side_effect = [account, None]

    with pytest.raises(InvalidAccountUpdateError, match="safe integer"):
        update_account(
            db,
            user_id="user-id",
            account_id="account-id",
            changes={"opening_balance_paise": invalid_value},
        )

    db.flush.assert_not_called()
