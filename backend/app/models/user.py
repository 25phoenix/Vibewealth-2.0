"""User identity and profile model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, PrimaryKeyConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression
from sqlalchemy.types import Uuid

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.auth_session import AuthSession
    from app.models.account import Account
    from app.models.assistant_conversation import AssistantConversation
    from app.models.assistant_message import AssistantMessage
    from app.models.budget import Budget
    from app.models.category import Category
    from app.models.goal_entry import GoalEntry
    from app.models.savings_goal import SavingsGoal
    from app.models.transaction import Transaction


class User(Base):
    """A registered VibeWealth user."""

    __tablename__ = "users"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_users"),
        CheckConstraint("length(btrim(email)) > 0", name="ck_users_email_nonempty"),
        CheckConstraint(
            "length(btrim(password_hash)) > 0", name="ck_users_password_hash_nonempty"
        ),
        Index("uq_users_email_lower", func.lower(expression.column("email")), unique=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    accounts: Mapped[list[Account]] = relationship(
        "Account", back_populates="user", passive_deletes="all"
    )
    categories: Mapped[list[Category]] = relationship(
        "Category", back_populates="user", passive_deletes="all"
    )
    transactions: Mapped[list[Transaction]] = relationship(
        "Transaction", back_populates="user", passive_deletes="all"
    )
    budgets: Mapped[list[Budget]] = relationship(
        "Budget", back_populates="user", passive_deletes="all"
    )
    savings_goals: Mapped[list[SavingsGoal]] = relationship(
        "SavingsGoal", back_populates="user", passive_deletes="all"
    )
    goal_entries: Mapped[list[GoalEntry]] = relationship(
        "GoalEntry", back_populates="user", passive_deletes="all"
    )
    assistant_conversations: Mapped[list[AssistantConversation]] = relationship(
        "AssistantConversation", back_populates="user", passive_deletes="all"
    )
    assistant_messages: Mapped[list[AssistantMessage]] = relationship(
        "AssistantMessage", back_populates="user", passive_deletes="all"
    )
    auth_sessions: Mapped[list[AuthSession]] = relationship(
        "AuthSession", back_populates="user", passive_deletes="all"
    )
