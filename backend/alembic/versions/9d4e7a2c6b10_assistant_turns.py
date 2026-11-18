"""persist assistant turns and fenced attempt state

Revision ID: 9d4e7a2c6b10
Revises: 8c2d6f4a1b90
"""

from alembic import op
import sqlalchemy as sa

revision = "9d4e7a2c6b10"
down_revision = "8c2d6f4a1b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.LargeBinary(32), nullable=False),
        sa.Column("user_sequence_no", sa.Integer(), nullable=False),
        sa.Column("assistant_sequence_no", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt_no", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("attempt_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("financial_date", sa.Date(), nullable=True),
        sa.Column("provider_kind", sa.String(16), nullable=False),
        sa.Column("model_name", sa.String(160), nullable=False),
        sa.Column("contract_version", sa.SmallInteger(), nullable=False),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_turns"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_assistant_turns_user_key"),
        sa.UniqueConstraint("conversation_id", "user_sequence_no", name="uq_assistant_turns_user_message"),
        sa.ForeignKeyConstraint(
            ["user_id", "conversation_id"], ["assistant_conversations.user_id", "assistant_conversations.id"],
            name="fk_assistant_turns_conversation_owner", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "user_sequence_no"], ["assistant_messages.conversation_id", "assistant_messages.sequence_no"],
            name="fk_assistant_turns_user_message", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "assistant_sequence_no"], ["assistant_messages.conversation_id", "assistant_messages.sequence_no"],
            name="fk_assistant_turns_assistant_message", ondelete="NO ACTION", deferrable=True, initially="DEFERRED",
        ),
        sa.CheckConstraint("octet_length(request_fingerprint) = 32", name="ck_assistant_turns_fingerprint_length"),
        sa.CheckConstraint("user_sequence_no BETWEEN 1 AND 2147483646", name="ck_assistant_turns_user_sequence"),
        sa.CheckConstraint("assistant_sequence_no IS NULL OR assistant_sequence_no = user_sequence_no + 1", name="ck_assistant_turns_reply_sequence"),
        sa.CheckConstraint("status IN ('pending', 'completed', 'failed', 'abandoned')", name="ck_assistant_turns_status"),
        sa.CheckConstraint("attempt_no BETWEEN 1 AND 3", name="ck_assistant_turns_attempt"),
        sa.CheckConstraint("provider_kind IN ('ollama', 'llama_cpp', 'hosted', 'fake')", name="ck_assistant_turns_provider"),
        sa.CheckConstraint("model_name ~ '[^[:space:]]'", name="ck_assistant_turns_model_nonblank"),
        sa.CheckConstraint("contract_version = 1", name="ck_assistant_turns_contract_version"),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code IN ("
            "'PROVIDER_TIMEOUT', 'PROVIDER_UNAVAILABLE', 'PROVIDER_RATE_LIMITED', "
            "'INVALID_PROVIDER_RESPONSE', 'CONTEXT_UNAVAILABLE', 'SESSION_INVALIDATED', "
            "'INTERNAL_FAILURE', 'CONTEXT_LIMIT', 'FINANCIAL_INVARIANT', 'OUTPUT_REJECTED')",
            name="ck_assistant_turns_error_code",
        ),
        sa.CheckConstraint("(context_as_of IS NULL) = (financial_date IS NULL)", name="ck_assistant_turns_context_pair"),
        sa.CheckConstraint("created_at <= attempt_started_at", name="ck_assistant_turns_started_order"),
        sa.CheckConstraint("attempt_finished_at IS NULL OR attempt_finished_at >= attempt_started_at", name="ck_assistant_turns_finished_order"),
        sa.CheckConstraint("context_as_of IS NULL OR context_as_of >= attempt_started_at", name="ck_assistant_turns_context_order"),
        sa.CheckConstraint(
            "(status = 'pending' AND assistant_sequence_no IS NULL "
            "AND lease_expires_at IS NOT NULL AND lease_expires_at > attempt_started_at "
            "AND attempt_finished_at IS NULL AND error_code IS NULL) OR "
            "(status = 'completed' AND assistant_sequence_no IS NOT NULL "
            "AND lease_expires_at IS NULL AND attempt_finished_at IS NOT NULL "
            "AND error_code IS NULL AND context_as_of IS NOT NULL AND financial_date IS NOT NULL) OR "
            "(status = 'failed' AND assistant_sequence_no IS NULL "
            "AND lease_expires_at IS NULL AND attempt_finished_at IS NOT NULL AND error_code IS NOT NULL) OR "
            "(status = 'abandoned' AND assistant_sequence_no IS NULL "
            "AND lease_expires_at IS NULL AND attempt_finished_at IS NOT NULL AND error_code IS NULL)",
            name="ck_assistant_turns_lifecycle",
        ),
    )
    op.create_index(
        "uq_assistant_turns_unresolved_conversation", "assistant_turns", ["conversation_id"],
        unique=True, postgresql_where=sa.text("status IN ('pending', 'failed')"),
    )


def downgrade() -> None:
    op.drop_index("uq_assistant_turns_unresolved_conversation", table_name="assistant_turns")
    op.drop_table("assistant_turns")
