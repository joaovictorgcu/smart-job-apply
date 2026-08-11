"""Dashboard metrics, computed with SQL aggregates."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIAnalysis, Application, ApplicationStatus, Job, User
from app.schemas.stats import DailyCount, DashboardStats, ScoreBucket
from app.services import application_service, job_service, user_service

# Upper bound of each bucket; the label is what the dashboard prints.
_SCORE_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("0-39", 0, 39),
    ("40-59", 40, 59),
    ("60-79", 60, 79),
    ("80-100", 80, 100),
)

_DAYS = 7


async def build_dashboard_stats(session: AsyncSession, user: User) -> DashboardStats:
    """One page of numbers for the dashboard, in a handful of aggregate queries."""
    user_settings = await user_service.get_or_create_settings(session, user)
    jobs_by_status = await job_service.count_by_status(session, user)

    aggregates = await session.execute(
        select(
            func.count(Job.id),
            func.avg(Job.score),
            *[
                func.sum(
                    case((Job.score.between(low, high), 1), else_=0)
                ).label(f"bucket_{low}")
                for _, low, high in _SCORE_BUCKETS
            ],
        ).where(Job.user_id == user.id)
    )
    row = aggregates.one()
    jobs_total = int(row[0] or 0)
    average_score = round(float(row[1]), 1) if row[1] is not None else None
    distribution = [
        ScoreBucket(label=label, count=int(row[index + 2] or 0))
        for index, (label, _, _) in enumerate(_SCORE_BUCKETS)
    ]

    applications_total_result = await session.execute(
        select(func.count()).select_from(Application).where(Application.user_id == user.id)
    )
    applications_total = int(applications_total_result.scalar_one())

    applications_today = await application_service.count_submitted_today(session, user)
    awaiting_review = await application_service.count_by_status(
        session, user, ApplicationStatus.AWAITING_REVIEW
    )

    per_day = await application_service.submitted_last_days(session, user, days=_DAYS)
    first_day = application_service.start_of_day().date() - timedelta(days=_DAYS - 1)
    last_7_days = [
        DailyCount(
            date=(first_day + timedelta(days=offset)).isoformat(),
            count=per_day.get((first_day + timedelta(days=offset)).isoformat(), 0),
        )
        for offset in range(_DAYS)
    ]

    ai_totals = await session.execute(
        select(
            func.count(AIAnalysis.id),
            func.coalesce(func.sum(AIAnalysis.input_tokens), 0),
            func.coalesce(func.sum(AIAnalysis.output_tokens), 0),
        ).where(AIAnalysis.user_id == user.id)
    )
    ai_calls, tokens_in, tokens_out = ai_totals.one()

    return DashboardStats(
        jobs_total=jobs_total,
        jobs_by_status=jobs_by_status,
        applications_total=applications_total,
        applications_today=applications_today,
        awaiting_review=awaiting_review,
        daily_cap=user_settings.daily_cap,
        remaining_today=max(0, user_settings.daily_cap - applications_today),
        average_score=average_score,
        score_distribution=distribution,
        applications_last_7_days=last_7_days,
        ai_calls_total=int(ai_calls or 0),
        ai_tokens_input=int(tokens_in or 0),
        ai_tokens_output=int(tokens_out or 0),
    )
