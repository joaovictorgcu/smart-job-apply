"""Dashboard metrics, computed with SQL aggregates."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AIAnalysis,
    Application,
    ApplicationOutcome,
    ApplicationStatus,
    Job,
    User,
)
from app.schemas.stats import (
    DailyCount,
    DashboardStats,
    OutcomeCount,
    OutcomeStats,
    ScoreBandRate,
    ScoreBucket,
    SegmentRate,
    SegmentStats,
)
from app.services import application_service, job_service, user_service

# Upper bound of each bucket; the label is what the dashboard prints.
_SCORE_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("0-39", 0, 39),
    ("40-59", 40, 59),
    ("60-79", 60, 79),
    ("80-100", 80, 100),
)

_DAYS = 7

# Fixed display order for the pipeline columns and the by-outcome breakdown.
_OUTCOME_ORDER: tuple[ApplicationOutcome, ...] = (
    ApplicationOutcome.APPLIED,
    ApplicationOutcome.INTERVIEW,
    ApplicationOutcome.OFFER,
    ApplicationOutcome.REJECTED,
    ApplicationOutcome.GHOSTED,
)
# "Reached an interview" = currently in interview or offer. A post-interview
# rejection is recorded as REJECTED, so this is a floor, not an exact count — the
# UI says so.
_INTERVIEW_OUTCOMES: tuple[ApplicationOutcome, ...] = (
    ApplicationOutcome.INTERVIEW,
    ApplicationOutcome.OFFER,
)
_OUTCOME_BANDS: tuple[tuple[str, int, int], ...] = (
    ("90-100", 90, 100),
    ("80-89", 80, 89),
    ("70-79", 70, 79),
    ("60-69", 60, 69),
    ("0-59", 0, 59),
)


async def build_outcome_stats(session: AsyncSession, user: User) -> OutcomeStats:
    """Does a high AI match score actually lead to interviews?

    Everything is computed over *submitted* applications joined to their job's
    score, in two aggregate queries.
    """
    submitted = (
        Application.user_id == user.id,
        Application.status == ApplicationStatus.SUBMITTED,
    )

    per_outcome = (
        await session.execute(
            select(Application.outcome, func.count(), func.avg(Job.score))
            .join(Job, Application.job_id == Job.id)
            .where(*submitted)
            .group_by(Application.outcome)
        )
    ).all()
    counts: dict[ApplicationOutcome, tuple[int, float | None]] = {
        row[0]: (int(row[1]), row[2]) for row in per_outcome if row[0] is not None
    }

    by_outcome = [
        OutcomeCount(
            outcome=outcome.value,
            count=counts.get(outcome, (0, None))[0],
            avg_score=(
                round(float(counts[outcome][1]), 1)
                if outcome in counts and counts[outcome][1] is not None
                else None
            ),
        )
        for outcome in _OUTCOME_ORDER
    ]

    total = sum(count for count, _ in counts.values())
    interviews = sum(counts.get(outcome, (0, None))[0] for outcome in _INTERVIEW_OUTCOMES)
    offers = counts.get(ApplicationOutcome.OFFER, (0, None))[0]
    rejected = counts.get(ApplicationOutcome.REJECTED, (0, None))[0]
    ghosted = counts.get(ApplicationOutcome.GHOSTED, (0, None))[0]

    interview_list = list(_INTERVIEW_OUTCOMES)
    band_columns = []
    for _, low, high in _OUTCOME_BANDS:
        band_columns.append(func.sum(case((Job.score.between(low, high), 1), else_=0)))
        band_columns.append(
            func.sum(
                case(
                    (
                        and_(
                            Job.score.between(low, high),
                            Application.outcome.in_(interview_list),
                        ),
                        1,
                    ),
                    else_=0,
                )
            )
        )
    band_row = (
        await session.execute(
            select(*band_columns)
            .select_from(Application)
            .join(Job, Application.job_id == Job.id)
            .where(*submitted)
        )
    ).one()
    bands = []
    for index, (label, _, _) in enumerate(_OUTCOME_BANDS):
        band_total = int(band_row[index * 2] or 0)
        band_interviews = int(band_row[index * 2 + 1] or 0)
        bands.append(
            ScoreBandRate(
                label=label,
                total=band_total,
                interviews=band_interviews,
                rate=round(band_interviews / band_total, 3) if band_total else None,
            )
        )

    return OutcomeStats(
        total_submitted=total,
        interviews=interviews,
        offers=offers,
        rejected=rejected,
        ghosted=ghosted,
        interview_rate=round(interviews / total, 3) if total else None,
        by_outcome=by_outcome,
        interview_rate_by_band=bands,
    )


async def build_dashboard_stats(session: AsyncSession, user: User) -> DashboardStats:
    """One page of numbers for the dashboard, in a handful of aggregate queries."""
    user_settings = await user_service.get_or_create_settings(session, user)
    jobs_by_status = await job_service.count_by_status(session, user)

    aggregates = await session.execute(
        select(
            func.count(Job.id),
            func.avg(Job.score),
            *[
                func.sum(case((Job.score.between(low, high), 1), else_=0)).label(f"bucket_{low}")
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


# Segments with fewer submissions than this are noise, not signal; they are
# still returned (the user should see them) but sorted after the meaningful ones.
_SEGMENT_LIMIT = 8


async def build_segment_stats(session: AsyncSession, user: User) -> SegmentStats:
    """Which kinds of application convert: by company, location and workplace."""
    interview_list = list(_INTERVIEW_OUTCOMES)
    submitted = (
        Application.user_id == user.id,
        Application.status == ApplicationStatus.SUBMITTED,
    )

    async def slice_by(column) -> list[SegmentRate]:  # noqa: ANN001 - SQLA column
        rows = (
            await session.execute(
                select(
                    column,
                    func.count(Application.id),
                    func.sum(case((Application.outcome.in_(interview_list), 1), else_=0)),
                )
                .select_from(Application)
                .join(Job, Application.job_id == Job.id)
                .where(*submitted)
                .group_by(column)
            )
        ).all()
        segments = []
        for label, total, interviews in rows:
            total = int(total or 0)
            interviews = int(interviews or 0)
            segments.append(
                SegmentRate(
                    label=str(label) if label else "(não informado)",
                    total=total,
                    interviews=interviews,
                    rate=round(interviews / total, 3) if total else None,
                )
            )
        segments.sort(key=lambda item: (-item.total, item.label.lower()))
        return segments[:_SEGMENT_LIMIT]

    return SegmentStats(
        by_company=await slice_by(Job.company),
        by_location=await slice_by(Job.location),
        by_workplace=await slice_by(Job.workplace_type),
    )
