"""Declarative base and mixins shared by the models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Dialect, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator[datetime]):
    """A datetime that is always timezone-aware and in UTC on the Python side.

    SQLite has no native timezone support and hands back naive datetimes, so
    `DateTime(timezone=True)` alone is not enough: an aware value written on one
    backend comes back naive on the other, and `utcnow() - row.created_at` then
    raises TypeError. Normalizing in both directions keeps the semantics
    identical across SQLite and PostgreSQL.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    """Base of every model.

    `type_annotation_map` keeps `datetime` columns timezone-aware on any backend,
    so swapping SQLite for PostgreSQL does not change the semantics.
    """

    type_annotation_map = {datetime: UtcDateTime()}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow, onupdate=utcnow, server_default=func.now()
    )
