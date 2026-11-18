"""Durable assistant operation identity and fenced attempt state."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer,
    LargeBinary, PrimaryKeyConstraint, SmallInteger, String, UniqueConstraint,
    func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.assistant_conversation import AssistantConversation
from app.models.assistant_message import AssistantMessage
from app.models.base import Base


class AssistantTurn(Base):
    """One user-wide idempotent operation; retries reuse its user message.

    Relationships are read-only: services in later phases must explicitly
    validate roles and own the short, fenced write transactions.
    """

    __tablename__ = "assistant_turns"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_assistant_turns"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_assistant_turns_user_key"),
        UniqueConstraint("conversation_id", "user_sequence_no", name="uq_assistant_turns_user_message"),
        ForeignKeyConstraint(
            ["user_id", "conversation_id"],
            ["assistant_conversations.user_id", "assistant_conversations.id"],
            name="fk_assistant_turns_conversation_owner", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "user_sequence_no"],
            ["assistant_messages.conversation_id", "assistant_messages.sequence_no"],
            name="fk_assistant_turns_user_message", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "assistant_sequence_no"],
            ["assistant_messages.conversation_id", "assistant_messages.sequence_no"],
            name="fk_assistant_turns_assistant_message", ondelete="NO ACTION",
            deferrable=True, initially="DEFERRED",
        ),
        CheckConstraint("octet_length(request_fingerprint) = 32", name="ck_assistant_turns_fingerprint_length"),
        CheckConstraint("user_sequence_no BETWEEN 1 AND 2147483646", name="ck_assistant_turns_user_sequence"),
        CheckConstraint(
            "assistant_sequence_no IS NULL OR assistant_sequence_no = user_sequence_no + 1",
            name="ck_assistant_turns_reply_sequence",
        ),
        CheckConstraint("status IN ('pending', 'completed', 'failed', 'abandoned')", name="ck_assistant_turns_status"),
        CheckConstraint("attempt_no BETWEEN 1 AND 3", name="ck_assistant_turns_attempt"),
        CheckConstraint("provider_kind IN ('ollama', 'llama_cpp', 'hosted', 'fake')", name="ck_assistant_turns_provider"),
        CheckConstraint("model_name ~ '[^[:space:]]'", name="ck_assistant_turns_model_nonblank"),
        CheckConstraint("contract_version = 1", name="ck_assistant_turns_contract_version"),
        CheckConstraint(
            "error_code IS NULL OR error_code IN ("
            "'PROVIDER_TIMEOUT', 'PROVIDER_UNAVAILABLE', 'PROVIDER_RATE_LIMITED', "
            "'INVALID_PROVIDER_RESPONSE', 'CONTEXT_UNAVAILABLE', 'SESSION_INVALIDATED', "
            "'INTERNAL_FAILURE', 'CONTEXT_LIMIT', 'FINANCIAL_INVARIANT', 'OUTPUT_REJECTED')",
            name="ck_assistant_turns_error_code",
        ),
        CheckConstraint(
            "(context_as_of IS NULL) = (financial_date IS NULL)",
            name="ck_assistant_turns_context_pair",
        ),
        CheckConstraint("created_at <= attempt_started_at", name="ck_assistant_turns_started_order"),
        CheckConstraint(
            "attempt_finished_at IS NULL OR attempt_finished_at >= attempt_started_at",
            name="ck_assistant_turns_finished_order",
        ),
        CheckConstraint(
            "context_as_of IS NULL OR context_as_of >= attempt_started_at",
            name="ck_assistant_turns_context_order",
        ),
        CheckConstraint(
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
        Index(
            "uq_assistant_turns_unresolved_conversation", "conversation_id", unique=True,
            postgresql_where=text("status IN ('pending', 'failed')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    user_sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    assistant_sequence_no: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    attempt_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    context_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    financial_date: Mapped[date | None] = mapped_column(Date)
    provider_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    contract_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(40))

    conversation: Mapped[AssistantConversation] = relationship(
        "AssistantConversation", foreign_keys=[user_id, conversation_id], viewonly=True,
    )
    user_message: Mapped[AssistantMessage] = relationship(
        "AssistantMessage", foreign_keys=[conversation_id, user_sequence_no], viewonly=True,
    )
    assistant_message: Mapped[AssistantMessage | None] = relationship(
        "AssistantMessage", foreign_keys=[conversation_id, assistant_sequence_no], viewonly=True,
    )
