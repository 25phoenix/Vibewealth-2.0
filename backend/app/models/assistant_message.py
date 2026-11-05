"""Persistent user and assistant messages."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    and_,
    func,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.assistant_conversation import AssistantConversation
from app.models.base import Base
from app.models.user import User


class AssistantMessage(Base):
    """A single ordered message in an assistant conversation."""

    __tablename__ = "assistant_messages"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_assistant_messages"),
        ForeignKeyConstraint(
            ["user_id", "conversation_id"],
            ["assistant_conversations.user_id", "assistant_conversations.id"],
            name="fk_assistant_messages_conversation_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("conversation_id", "sequence_no", name="uq_assistant_messages_conversation_sequence"),
        CheckConstraint("sequence_no > 0", name="ck_assistant_messages_sequence_positive"),
        CheckConstraint("role IN ('user', 'assistant')", name="ck_assistant_messages_role"),
        CheckConstraint("length(btrim(content)) > 0", name="ck_assistant_messages_content_nonempty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_assistant_messages_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sequence_no: Mapped[int] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user: Mapped[User] = relationship("User", back_populates="assistant_messages")
    conversation: Mapped[AssistantConversation] = relationship(
        "AssistantConversation",
        primaryjoin=lambda: and_(
            AssistantConversation.id == foreign(AssistantMessage.conversation_id),
            AssistantConversation.user_id == AssistantMessage.user_id,
        ),
        foreign_keys=lambda: [AssistantMessage.conversation_id],
        viewonly=True,
    )
