"""Tenant-scoped category reads for financial workflows."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category


def list_active_categories(db: Session, *, user_id: UUID) -> list[Category]:
    """Return only active categories owned by the authenticated user."""

    return list(
        db.scalars(
            select(Category)
            .where(Category.user_id == user_id, Category.archived_at.is_(None))
            .order_by(Category.transaction_type, func.lower(Category.name), Category.id)
        ).all()
    )
