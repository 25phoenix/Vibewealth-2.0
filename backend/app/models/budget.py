"""Monthly overall and category budgets."""

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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base
from app.models.category import Category
from app.models.user import User


class Budget(Base):
    """An overall monthly or category-specific spending limit."""

    __tablename__ = "budgets"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_budgets"),
        UniqueConstraint("user_id", "id", name="uq_budgets_user_id_id"),
        ForeignKeyConstraint(
            ["user_id", "category_id"],
            ["categories.user_id", "categories.id"],
            name="fk_budgets_category_owner",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("EXTRACT(DAY FROM month_start) = 1", name="ck_budgets_month_start_first_day"),
        CheckConstraint("limit_paise > 0", name="ck_budgets_limit_positive"),
        Index(
            "uq_budgets_one_overall_per_month",
            "user_id",
            "month_start",
            unique=True,
            postgresql_where=text("category_id IS NULL"),
            sqlite_where=text("category_id IS NULL"),
        ),
        Index(
            "uq_budgets_one_per_category_month",
            "user_id",
            "category_id",
            "month_start",
            unique=True,
            postgresql_where=text("category_id IS NOT NULL"),
            sqlite_where=text("category_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_budgets_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    category_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    month_start: Mapped[date] = mapped_column(Date, nullable=False)
    limit_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship("User", back_populates="budgets")
    category: Mapped[Category | None] = relationship(
        "Category",
        primaryjoin=lambda: (Category.id == foreign(Budget.category_id))
        & (Category.user_id == Budget.user_id),
        foreign_keys=lambda: [Budget.category_id],
        viewonly=True,
    )
