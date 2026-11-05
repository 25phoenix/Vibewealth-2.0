"""User-owned income and expense categories."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
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
from sqlalchemy.sql import expression
from sqlalchemy.types import Uuid

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.budget import Budget
    from app.models.transaction import Transaction
    from app.models.user import User


class Category(Base):
    """A user-owned income or expense category."""

    __tablename__ = "categories"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_categories"),
        UniqueConstraint("user_id", "id", name="uq_categories_user_id_id"),
        UniqueConstraint(
            "user_id", "id", "transaction_type", name="uq_categories_user_id_id_type"
        ),
        CheckConstraint("length(btrim(name)) > 0", name="ck_categories_name_nonempty"),
        CheckConstraint(
            "transaction_type IN ('income', 'expense')", name="ck_categories_transaction_type"
        ),
        Index(
            "uq_categories_active_name_per_type",
            "user_id",
            expression.func.lower(expression.column("name")),
            "transaction_type",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
            sqlite_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_categories_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship("User", back_populates="categories")
