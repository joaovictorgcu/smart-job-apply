"""Append-only trail of account-level changes, guardrails first."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import AuditAction

if TYPE_CHECKING:
    from app.models.user import User


class AuditEvent(Base):
    """One recorded change to the settings that constrain the automation.

    The whole promise of the product is that nothing is submitted without a human
    saying so; the act of weakening that promise is therefore the last thing that
    may live only in a log line. Append-only, like `ApplicationEvent`: rows are
    written once and never updated, so there is no `updated_at` to keep.
    """

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # "user_settings" | "profile" | "linkedin_account" — the row that changed.
    subject_type: Mapped[str] = mapped_column(String(40), index=True)
    subject_id: Mapped[int | None] = mapped_column(Integer, default=None)
    action: Mapped[AuditAction] = mapped_column(String(60), index=True)

    # Only the fields that actually moved: a full snapshot would bury the diff,
    # and personal data is deliberately kept out (see `user_service`).
    before: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    after: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # The changed guardrails that moved in the permissive direction. Empty when a
    # change only tightened things, which is what makes the list worth reading.
    relaxed: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=None, index=True)

    user: Mapped[User] = relationship(back_populates="audit_events")

    def __init__(self, **kwargs: Any) -> None:
        from app.database.base import utcnow

        kwargs.setdefault("created_at", utcnow())
        super().__init__(**kwargs)
