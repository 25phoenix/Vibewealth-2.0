"""add goal descriptions and goal-scoped ledger index

Revision ID: 6b9c2f1d4a80
Revises: e7a30067c81c
Create Date: 2026-11-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "6b9c2f1d4a80"
down_revision: Union[str, None] = "e7a30067c81c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("savings_goals", sa.Column("description", sa.Text(), nullable=True))
    op.create_index(
        "ix_goal_entries_user_goal_created",
        "goal_entries",
        ["user_id", "goal_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_goal_entries_user_goal_created", table_name="goal_entries")
    op.drop_column("savings_goals", "description")
