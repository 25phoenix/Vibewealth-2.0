"""Transaction request and service-boundary validation unit tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.financial import MAX_SAFE_PAISE, financial_today
from app.schemas.transactions import TransactionCreateRequest
from app.services.transactions import InvalidTransactionError, create_transaction, list_transactions


def _payload(**overrides):
    values = {
        "account_id": str(uuid4()),
        "category_id": str(uuid4()),
        "transaction_type": "expense",
        "amount_paise": 1250,
        "description": "Groceries",
        "transaction_date": financial_today().isoformat(),
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("amount", [0, -1, 1.2, "100", MAX_SAFE_PAISE + 1, True])
def test_transaction_schema_rejects_invalid_paise_amounts(amount):
    with pytest.raises(ValidationError):
        TransactionCreateRequest(**_payload(amount_paise=amount))


def test_transaction_schema_requires_category_and_rejects_extra_owner_field():
    payload = _payload()
    del payload["category_id"]
    with pytest.raises(ValidationError):
        TransactionCreateRequest(**payload)

    with pytest.raises(ValidationError):
        TransactionCreateRequest(**_payload(user_id=str(uuid4())))


def test_transaction_schema_rejects_blank_description_and_invalid_type():
    with pytest.raises(ValidationError):
        TransactionCreateRequest(**_payload(description="   "))
    with pytest.raises(ValidationError):
        TransactionCreateRequest(**_payload(transaction_type="transfer"))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"transaction_type": "transfer"}, "type"),
        ({"amount_paise": 0}, "Amount"),
        ({"amount_paise": MAX_SAFE_PAISE + 1}, "Amount"),
        ({"description": " "}, "Description"),
        ({"transaction_date": date.max}, "future"),
    ],
)
def test_transaction_service_rejects_invalid_values_before_database_access(kwargs, message):
    db = Mock()
    values = {
        "user_id": uuid4(),
        "account_id": uuid4(),
        "category_id": uuid4(),
        "transaction_type": "expense",
        "amount_paise": 100,
        "description": "Purchase",
        "transaction_date": financial_today(),
    }
    values.update(kwargs)

    with pytest.raises(InvalidTransactionError, match=message):
        create_transaction(db, **values)

    db.scalar.assert_not_called()


def test_transaction_service_rejects_unordered_date_range_before_query():
    db = Mock()

    with pytest.raises(InvalidTransactionError, match="date_from"):
        list_transactions(
            db,
            user_id=uuid4(),
            date_from=date(2026, 2, 1),
            date_to=date(2026, 1, 1),
        )

    db.scalar.assert_not_called()
    db.execute.assert_not_called()
