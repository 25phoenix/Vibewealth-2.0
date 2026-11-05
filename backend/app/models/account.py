"""User-owned cash, bank, and wallet asset accounts."""

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
    from app.models.transaction import Transaction
    from app.models.user import User


class Account(Base):
    """An asset account owned by one user."""

    __tablename__ = "accounts"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_accounts"),
        UniqueConstraint("user_id", "id", name="uq_accounts_user_id_id"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_accounts_name_nonempty"),
        CheckConstraint(
            "account_type IN ('cash', 'bank', 'wallet')", name="ck_accounts_type"
        ),
        CheckConstraint("opening_balance_paise >= 0", name="ck_accounts_opening_balance_nonnegative"),
        Index(
            "uq_accounts_one_default_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_default IS TRUE"),
            sqlite_where=text("is_default IS 1"),
        ),
        Index("ix_accounts_user_archived", "user_id", "archived_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_accounts_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(String(16), nullable=False)
    is_default: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    opening_balance_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    opening_balance_as_of: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship("User", back_populates="accounts")
