"""persist transaction creation idempotency keys

Revision ID: 8c2d6f4a1b90
Revises: 6b9c2f1d4a80
Create Date: 2026-11-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c2d6f4a1b90"
down_revision: Union[str, None] = "6b9c2f1d4a80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("transactions", sa.Column("request_fingerprint", sa.String(length=64), nullable=True))
    op.create_unique_constraint(
        "uq_transactions_user_idempotency_key",
        "transactions",
        ["user_id", "idempotency_key"],
    )
    op.create_check_constraint(
        "ck_transactions_idempotency_pair",
        "transactions",
        "(idempotency_key IS NULL) = (request_fingerprint IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_transactions_idempotency_pair", "transactions", type_="check"
    )
    op.drop_constraint(
        "uq_transactions_user_idempotency_key", "transactions", type_="unique"
    )
    op.drop_column("transactions", "request_fingerprint")
    op.drop_column("transactions", "idempotency_key")
