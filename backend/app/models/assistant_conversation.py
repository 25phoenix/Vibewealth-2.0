"""Persistent assistant conversation model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, PrimaryKeyConstraint, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.assistant_message import AssistantMessage
    from app.models.user import User


class AssistantConversation(Base):
    """A persistent assistant conversation owned by one user."""

    __tablename__ = "assistant_conversations"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_assistant_conversations"),
        UniqueConstraint("user_id", "id", name="uq_assistant_conversations_user_id_id"),
        Index("ix_assistant_conversations_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id", name="fk_assistant_conversations_user_id_users", ondelete="CASCADE"
        ),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship("User", back_populates="assistant_conversations")
