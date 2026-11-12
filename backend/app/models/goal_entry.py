"""Append-only virtual account-to-goal allocation entries."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    String,
    and_,
    func,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.account import Account
from app.models.base import Base
from app.models.savings_goal import SavingsGoal
from app.models.user import User


class GoalEntry(Base):
    """A contribution to or withdrawal from a goal/account allocation."""

    __tablename__ = "goal_entries"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_goal_entries"),
        ForeignKeyConstraint(
            ["user_id", "goal_id"],
            ["savings_goals.user_id", "savings_goals.id"],
            name="fk_goal_entries_goal_owner",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_goal_entries_account_owner",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("entry_type IN ('contribution', 'withdrawal')", name="ck_goal_entries_type"),
        CheckConstraint("amount_paise > 0", name="ck_goal_entries_amount_positive"),
        Index(
            "ix_goal_entries_user_account_goal_date",
            "user_id",
            "account_id",
            "goal_id",
            "effective_date",
        ),
        Index(
            "ix_goal_entries_user_goal_created",
            "user_id",
            "goal_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_goal_entries_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    goal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    account_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user: Mapped[User] = relationship("User", back_populates="goal_entries")
    goal: Mapped[SavingsGoal] = relationship(
        "SavingsGoal",
        primaryjoin=lambda: and_(
            SavingsGoal.id == foreign(GoalEntry.goal_id), SavingsGoal.user_id == GoalEntry.user_id
        ),
        foreign_keys=lambda: [GoalEntry.goal_id],
        viewonly=True,
    )
    account: Mapped[Account] = relationship(
        "Account",
        primaryjoin=lambda: and_(
            Account.id == foreign(GoalEntry.account_id), Account.user_id == GoalEntry.user_id
        ),
        foreign_keys=lambda: [GoalEntry.account_id],
        viewonly=True,
    )
