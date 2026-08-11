"""Execuções de automação — permitem retomar, auditar e parar (kill switch)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import AutomationRunKind, AutomationRunStatus

if TYPE_CHECKING:
    from app.models.job import Search
    from app.models.user import User


class AutomationRun(Base, TimestampMixin):
    """Uma execução do engine (busca, preparação ou envio).

    `checkpoint` guarda o progresso para retomar depois de uma falha, e
    `stop_requested` é o kill switch cooperativo lido pelo engine entre passos.
    """

    __tablename__ = "automation_runs"
    __table_args__ = (Index("ix_run_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    search_id: Mapped[int | None] = mapped_column(
        ForeignKey("searches.id", ondelete="SET NULL"), default=None
    )

    kind: Mapped[AutomationRunKind] = mapped_column(String(20), index=True)
    status: Mapped[AutomationRunStatus] = mapped_column(
        String(20), default=AutomationRunStatus.PENDING, index=True
    )
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)

    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    jobs_skipped: Mapped[int] = mapped_column(Integer, default=0)
    applications_prepared: Mapped[int] = mapped_column(Integer, default=0)
    applications_submitted: Mapped[int] = mapped_column(Integer, default=0)

    stop_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(300), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    # Estado para retomada, ex.: {"page": 2, "processed_ids": [...]}.
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)

    user: Mapped[User] = relationship(back_populates="runs")
    search: Mapped[Search | None] = relationship(back_populates="runs")

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            AutomationRunStatus.COMPLETED,
            AutomationRunStatus.STOPPED,
            AutomationRunStatus.FAILED,
        }
