"""Append-only history of the fit score.

`jobs.score` answers "how good is this job right now"; this table answers "how did
that number get there". They are different questions, so they are different rows —
see the comment on `Job.score` for why the denormalised column stays.

Two things need the dimensions as rows rather than as JSON inside `ai_analyses`:
showing the user that a job went from 62 to 81 after they added an experience, and
fitting real interview outcomes against the dimensions that produced the score.
Neither is possible against a column that the next scoring pass overwrites.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.job import Job

# How much of the posting the verdict was formed from. Only `DEEP` is produced
# today — the full read of the description. The column exists from the start
# because a cheap triage pass over listing metadata is coming, and a history
# whose rows cannot say which tier produced them is not comparable with itself.
SCORE_DEPTH_TRIAGE = "triage"
SCORE_DEPTH_DEEP = "deep"


class JobScore(Base):
    """One scoring verdict, kept forever.

    Note the name clash with `app.ai.schemas.JobScore`, which is the *model's*
    output contract. This is the persisted verdict derived from one of those, and
    modules needing both import this one as `JobScoreRow`.

    No `TimestampMixin`: an `updated_at` would be a lie on an append-only table.
    `created_at` is defaulted in `__init__` like `ApplicationEvent`, so a row has
    its timestamp before the flush and callers can order rows they just created.
    """

    __tablename__ = "job_scores"
    # The one query this table exists for: the timeline of a single job.
    __table_args__ = (Index("ix_job_score_job_created", "job_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    overall: Mapped[int] = mapped_column(Integer)
    # The band the overall score fell in *at the time*, not recomputed on read:
    # moving a boundary in `VERDICT_BANDS` must not rewrite what a past score said.
    verdict: Mapped[str] = mapped_column(String(20))
    # [{"dimension", "score", "weight", "weight_pct", "evidence"}] — the same shape
    # as `Job.score_breakdown`, frozen here so a later scoring pass cannot erase it.
    dimensions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # [{"gate", "status", "evidence"}] — the decisive checks, frozen the same way.
    gates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    model: Mapped[str] = mapped_column(String(100))
    depth: Mapped[str] = mapped_column(String(10), default=SCORE_DEPTH_DEEP)
    # Hash of the profile text the score was formed against, from the same function
    # that fingerprints a tailored resume. This is what makes a jump in the score
    # attributable: two verdicts with different fingerprints were scored against
    # different profiles, so the profile edit is a candidate explanation.
    # Null for rows written when no profile context was available.
    profile_fingerprint: Mapped[str | None] = mapped_column(String(64), default=None)

    created_at: Mapped[datetime] = mapped_column(default=None, index=True)

    job: Mapped[Job] = relationship(back_populates="scores")

    def __init__(self, **kwargs: Any) -> None:
        from app.database.base import utcnow

        kwargs.setdefault("created_at", utcnow())
        super().__init__(**kwargs)
