"""Savings goal model; progress is derived from goal entries."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.goal_entry import GoalEntry
    from app.models.user import User


class SavingsGoal(Base):
    """A user-defined savings target."""

    __tablename__ = "savings_goals"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_savings_goals"),
        UniqueConstraint("user_id", "id", name="uq_savings_goals_user_id_id"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_savings_goals_name_nonempty"),
        CheckConstraint("target_paise > 0", name="ck_savings_goals_target_positive"),
        Index(
            "ix_savings_goals_user_target_date_active",
            "user_id",
            "target_date",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_savings_goals_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship("User", back_populates="savings_goals")
