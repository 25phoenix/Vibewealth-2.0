"""Completed income and expense transactions."""

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
    Text,
    UniqueConstraint,
    and_,
    func,
    text,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.account import Account
from app.models.base import Base
from app.models.category import Category
from app.models.user import User


class Transaction(Base):
    """A completed income or expense record."""

    __tablename__ = "transactions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_transactions"),
        UniqueConstraint("user_id", "id", name="uq_transactions_user_id_id"),
        ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_transactions_account_owner",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["user_id", "category_id", "transaction_type"],
            ["categories.user_id", "categories.id", "categories.transaction_type"],
            name="fk_transactions_category_owner_type",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("transaction_type IN ('income', 'expense')", name="ck_transactions_type"),
        CheckConstraint("amount_paise > 0", name="ck_transactions_amount_positive"),
        CheckConstraint("length(btrim(description)) > 0", name="ck_transactions_description_nonempty"),
        Index(
            "ix_transactions_user_date_live",
            "user_id",
            text("transaction_date DESC"),
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_transactions_account_date_live",
            "user_id",
            "account_id",
            "transaction_date",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_transactions_expense_category_date_live",
            "user_id",
            "category_id",
            "transaction_date",
            postgresql_where=text("deleted_at IS NULL AND transaction_type = 'expense'"),
            sqlite_where=text("deleted_at IS NULL AND transaction_type = 'expense'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_transactions_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    category_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    transaction_type: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[str] = mapped_column(String(120), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship("User", back_populates="transactions")
    account: Mapped[Account] = relationship(
        "Account",
        primaryjoin=lambda: and_(
            Account.id == foreign(Transaction.account_id), Account.user_id == Transaction.user_id
        ),
        foreign_keys=lambda: [Transaction.account_id],
        viewonly=True,
    )
    category: Mapped[Category | None] = relationship(
        "Category",
        primaryjoin=lambda: and_(
            Category.id == foreign(Transaction.category_id),
            Category.user_id == Transaction.user_id,
            Category.transaction_type == Transaction.transaction_type,
        ),
        foreign_keys=lambda: [Transaction.category_id],
        viewonly=True,
    )
