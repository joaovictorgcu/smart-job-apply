"""Platform-wide aggregates for the administrative panel.

Every other service in this package is scoped to one user; this one deliberately
is not, and that is exactly why it is the only module the admin router may call.
The scoping rule is replaced by two others:

* **Aggregates, not rows.** Almost everything here is a `COUNT`/`AVG`/`SUM` over
  an indexed column. The three places that do read rows (recent errors, the
  activity timeline, the technology extraction) are each capped by a constant
  declared next to them.
* **No personal content, ever.** No resume, cover letter, screening answer,
  session cookie or password hash is selected here. `AdminUserRow` and
  `UsageRow` carry contact details and counters, and there is nowhere else for
  such data to go.

Cost control is the other half of the design. `build_overview` answers the whole
first screen, so the panel makes one request instead of nine that would each
re-derive the same period bounds and could disagree about what "now" is. Its
result is memoised for `CACHE_TTL_SECONDS`, and the panel's "Atualizar dados"
button bypasses that with `refresh=True`.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.api.errors import ValidationError
from app.config import PROJECT_ROOT, get_settings
from app.database.base import utcnow
from app.domain.technologies import job_technologies
from app.models import (
    AIAnalysis,
    Application,
    ApplicationEvent,
    ApplicationEventType,
    ApplicationOutcome,
    ApplicationStatus,
    AuditAction,
    AuditEvent,
    AutomationRun,
    AutomationRunStatus,
    Job,
    JobStatus,
    User,
)
from app.observability import get_logger, record_audit_event
from app.schemas.admin import (
    ActivityEntry,
    AdminOverview,
    AdminPeriod,
    AdminUserFilter,
    AdminUserRow,
    AIHealth,
    Alert,
    AlertSeverity,
    AutomationHealth,
    ErrorEntry,
    FunnelStage,
    GrowthPoint,
    HealthStatus,
    JobInsights,
    LabelCount,
    Metric,
    MetricTrend,
    MetricUnit,
    PeriodInfo,
    ServiceState,
    ServiceStatus,
    SystemHealth,
    UsageRow,
)
from app.schemas.common import Page

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# Caps and thresholds — every magic number the panel depends on, in one place
# --------------------------------------------------------------------------- #

# How long a computed overview may be served again. Short enough that the panel
# feels live, long enough that holding the page open does not re-run the
# aggregates on every focus event.
CACHE_TTL_SECONDS = 30.0
_CACHE_MAX_ENTRIES = 16

# A custom range wider than this is refused: the growth series is one point per
# day, and nobody reads a chart with a thousand of them.
MAX_CUSTOM_DAYS = 366

# Row-reading caps.
ERRORS_LIMIT = 8  # on the dashboard; the errors endpoint takes its own limit
ACTIVITY_LIMIT = 12
USAGE_LIMIT = 5
DURATION_SAMPLE = 500  # completed runs averaged for "tempo médio de execução"
TECHNOLOGY_SAMPLE = 300  # postings whose text is scanned for technologies
TOP_LABELS = 6

# Alert thresholds. Named so the alert text can quote them.
FAILURE_RATE_WARNING = 0.20
FAILURE_RATE_CRITICAL = 0.40
MIN_ATTEMPTS_FOR_RATE = 4
ERROR_SPIKE_FACTOR = 2.0
MIN_ERRORS_FOR_SPIKE = 10
AI_ERROR_RATE_WARNING = 0.10
AI_ERROR_RATE_CRITICAL = 0.30
MIN_AI_CALLS_FOR_RATE = 5
AI_SLOW_LATENCY_MS = 15_000.0
QUEUE_BACKLOG_WARNING = 25
QUEUE_BACKLOG_CRITICAL = 100
# Below this a delta reads as noise, and an arrow next to it reads as a claim.
FLAT_DELTA = 0.005

# Job statuses that mean "the platform put this posting forward".
RECOMMENDED_STATUSES = (JobStatus.ANALYZED, JobStatus.QUEUED, JobStatus.APPLIED)

ACTIVE_RUN_STATUSES = (
    AutomationRunStatus.PENDING,
    AutomationRunStatus.RUNNING,
    AutomationRunStatus.PAUSED,
)

INTERVIEW_OUTCOMES = (ApplicationOutcome.INTERVIEW, ApplicationOutcome.OFFER)

# Persisted error messages are written for humans (`app.automation.errors`,
# `AIAnalysis.error_message`, `ApplicationEvent.message`); tracebacks go to the
# logger with `exc_info` and never reach a column. Truncating is therefore about
# layout, not redaction.
SUMMARY_CHARS = 160


# --------------------------------------------------------------------------- #
# The period
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Window:
    """A resolved period and the equally long window immediately before it."""

    period: AdminPeriod
    start: datetime
    end: datetime
    previous_start: datetime
    previous_end: datetime

    @property
    def span(self) -> timedelta:
        return self.end - self.start

    @property
    def days(self) -> int:
        """Calendar days the window touches, which is what the chart plots."""
        return (self.end.date() - self.start.date()).days + 1

    def to_info(self) -> PeriodInfo:
        return PeriodInfo(
            period=self.period,
            start=self.start,
            end=self.end,
            previous_start=self.previous_start,
            previous_end=self.previous_end,
            days=self.days,
        )


def _start_of_day(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


_PRESET_DAYS: dict[AdminPeriod, int] = {
    AdminPeriod.TODAY: 1,
    AdminPeriod.LAST_7_DAYS: 7,
    AdminPeriod.LAST_30_DAYS: 30,
    AdminPeriod.LAST_90_DAYS: 90,
}


def resolve_period(
    period: AdminPeriod,
    *,
    start: date | None = None,
    end: date | None = None,
    now: datetime | None = None,
) -> Window:
    """Turn a filter choice into concrete bounds, plus the window to compare with.

    The comparison window is the same *duration* immediately before the selected
    one, not the previous calendar unit. For "hoje" that means yesterday up to
    this hour, which is the only comparison that is not misleading before noon.
    """
    moment = (now or utcnow()).astimezone(UTC)

    if period is AdminPeriod.CUSTOM:
        if start is None or end is None:
            raise ValidationError("A custom period needs both 'start' and 'end' dates.")
        if end < start:
            raise ValidationError("'end' cannot be earlier than 'start'.")
        span_days = (end - start).days + 1
        if span_days > MAX_CUSTOM_DAYS:
            raise ValidationError(
                f"A custom period cannot be longer than {MAX_CUSTOM_DAYS} days."
            )
        window_start = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
        # Inclusive of the end date, and never in the future: a range ending
        # tomorrow would report a partial day as if it were complete.
        window_end = min(
            datetime.combine(end, datetime.min.time(), tzinfo=UTC) + timedelta(days=1),
            moment,
        )
        window_end = max(window_end, window_start)
    else:
        days = _PRESET_DAYS[period]
        window_start = _start_of_day(moment) - timedelta(days=days - 1)
        window_end = moment

    span = window_end - window_start
    return Window(
        period=period,
        start=window_start,
        end=window_end,
        previous_start=window_start - span,
        previous_end=window_start,
    )


def _within(column: Any, start: datetime, end: datetime) -> Any:
    """Half-open [start, end) so a row is never counted in two windows."""
    return and_(column.is_not(None), column >= start, column < end)


def _count_if(condition: Any) -> Any:
    return func.sum(case((condition, 1), else_=0))


# --------------------------------------------------------------------------- #
# Metric construction
# --------------------------------------------------------------------------- #


def build_metric(
    key: str,
    value: float | int | None,
    *,
    previous: float | int | None = None,
    unit: MetricUnit = MetricUnit.COUNT,
    has_data: bool = True,
) -> Metric:
    """One tile's worth of number, with an honest comparison or none at all.

    A percentage is compared in *points* (0.62 vs 0.54 -> +0.08), everything else
    relatively ((new - old) / old). Comparing a rate relatively is the classic way
    to turn "54% to 62%" into a triumphant "+14.8%", and this panel is supposed to
    support a decision, not sell one.
    """
    if value is None:
        return Metric(key=key, value=0.0, unit=unit, has_data=False)

    numeric = float(value)
    metric = Metric(key=key, value=numeric, unit=unit, has_data=has_data)
    if previous is None:
        return metric

    metric.previous = float(previous)
    if unit is MetricUnit.PERCENT:
        delta = numeric - float(previous)
    elif float(previous) == 0.0:
        # No baseline to grow from; the tile shows the raw previous value instead
        # of an infinite percentage.
        return metric
    else:
        delta = (numeric - float(previous)) / float(previous)

    metric.delta_pct = round(delta, 4)
    if abs(delta) < FLAT_DELTA:
        metric.trend = MetricTrend.FLAT
    else:
        metric.trend = MetricTrend.UP if delta > 0 else MetricTrend.DOWN
    return metric


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


# --------------------------------------------------------------------------- #
# Aggregate queries — one per table, each a single round trip
# --------------------------------------------------------------------------- #


async def _row(session: AsyncSession, statement: Select[Any]) -> Sequence[Any]:
    return (await session.execute(statement)).one()


def _int(value: Any) -> int:
    return int(value or 0)


async def _user_counts(session: AsyncSession, window: Window) -> dict[str, int]:
    """Registered totals and per-window signups/logins, in one pass over `users`.

    Unfiltered on purpose: the headline tile is a running total, so the row count
    is the metric. `users` is the smallest table in the schema.
    """
    row = await _row(
        session,
        select(
            _count_if(User.created_at < window.end),
            _count_if(User.created_at < window.previous_end),
            _count_if(_within(User.created_at, window.start, window.end)),
            _count_if(_within(User.created_at, window.previous_start, window.previous_end)),
            _count_if(_within(User.last_login_at, window.start, window.end)),
            _count_if(_within(User.last_login_at, window.previous_start, window.previous_end)),
            _count_if(User.is_active.is_(False)),
        ).select_from(User),
    )
    return {
        "total": _int(row[0]),
        "total_previous": _int(row[1]),
        "new": _int(row[2]),
        "new_previous": _int(row[3]),
        "active": _int(row[4]),
        "active_previous": _int(row[5]),
        "disabled": _int(row[6]),
    }


async def _job_counts(session: AsyncSession, window: Window) -> dict[str, Any]:
    """Jobs discovered in the window and the one before it.

    Seven numbers from one pass. `created_at` carries no index of its own today
    (`TimestampMixin` declares none), so the `WHERE` narrows the scan without
    being able to seek — which is fine at this scale and is the first thing to
    add when it stops being fine. The alternative, seven separate `COUNT`
    queries, would scan seven times.
    """
    current = _within(Job.created_at, window.start, window.end)
    previous = _within(Job.created_at, window.previous_start, window.previous_end)
    row = await _row(
        session,
        select(
            _count_if(current),
            _count_if(previous),
            func.avg(case((current, Job.score))),
            _count_if(and_(current, Job.status.in_(RECOMMENDED_STATUSES))),
            _count_if(and_(current, Job.status == JobStatus.SKIPPED)),
            _count_if(and_(current, Job.status == JobStatus.QUEUED)),
            _count_if(and_(current, Job.status == JobStatus.APPLIED)),
        )
        .select_from(Job)
        # Both windows in one pass, so the previous period costs nothing extra.
        .where(Job.created_at >= window.previous_start, Job.created_at < window.end),
    )
    return {
        "found": _int(row[0]),
        "found_previous": _int(row[1]),
        "average_score": round(float(row[2]), 1) if row[2] is not None else None,
        "recommended": _int(row[3]),
        "skipped": _int(row[4]),
        "queued": _int(row[5]),
        "applied": _int(row[6]),
    }


async def _application_counts(session: AsyncSession, window: Window) -> dict[str, int]:
    """Applications created in the window, split by how far they got."""
    current = _within(Application.created_at, window.start, window.end)
    previous = _within(Application.created_at, window.previous_start, window.previous_end)
    row = await _row(
        session,
        select(
            _count_if(current),
            _count_if(previous),
            _count_if(and_(current, Application.status == ApplicationStatus.SUBMITTED)),
            _count_if(and_(previous, Application.status == ApplicationStatus.SUBMITTED)),
            _count_if(and_(current, Application.status == ApplicationStatus.FAILED)),
            _count_if(and_(previous, Application.status == ApplicationStatus.FAILED)),
            _count_if(and_(current, Application.approved_at.is_not(None))),
            _count_if(and_(current, Application.status == ApplicationStatus.DISCARDED)),
        )
        .select_from(Application)
        .where(
            Application.created_at >= window.previous_start,
            Application.created_at < window.end,
        ),
    )
    return {
        "created": _int(row[0]),
        "created_previous": _int(row[1]),
        "submitted": _int(row[2]),
        "submitted_previous": _int(row[3]),
        "failed": _int(row[4]),
        "failed_previous": _int(row[5]),
        "approved": _int(row[6]),
        "discarded": _int(row[7]),
    }


async def _backlog_counts(session: AsyncSession) -> dict[str, int]:
    """The "right now" numbers: the review queue and live automation runs.

    Not period-scoped, and the labels on the panel say so. A backlog is only
    interesting as it stands; "applications that were awaiting review during
    March" is not a question anyone asks.

    Three narrow `COUNT(*) WHERE status = ...` rather than one pass with
    `SUM(CASE ...)`: these are the only queries in the overview with no date
    bound, so they are the ones that would scan the whole table as it grows.
    Written as an equality they can be answered from the index that
    `Application.status` and `AutomationRun.status` already declare.
    """

    async def count_where(model: Any, *conditions: Any) -> int:
        result = await session.execute(
            select(func.count()).select_from(model).where(*conditions)
        )
        return _int(result.scalar_one())

    return {
        "awaiting_review": await count_where(
            Application, Application.status == ApplicationStatus.AWAITING_REVIEW
        ),
        "active_runs": await count_where(
            AutomationRun, AutomationRun.status.in_(ACTIVE_RUN_STATUSES)
        ),
        "blocked_runs": await count_where(
            AutomationRun, AutomationRun.status == AutomationRunStatus.BLOCKED
        ),
    }


async def _interview_counts(session: AsyncSession, window: Window) -> dict[str, int]:
    """Applications that reached an interview inside each window.

    Keyed on `outcome_updated_at`: the interview happened when the user recorded
    it, not when the application was created.
    """
    row = await _row(
        session,
        select(
            _count_if(_within(Application.outcome_updated_at, window.start, window.end)),
            _count_if(
                _within(
                    Application.outcome_updated_at, window.previous_start, window.previous_end
                )
            ),
        )
        .select_from(Application)
        .where(Application.outcome.in_(list(INTERVIEW_OUTCOMES))),
    )
    return {"interviews": _int(row[0]), "interviews_previous": _int(row[1])}


async def _automation_counts(session: AsyncSession, window: Window) -> dict[str, Any]:
    current = _within(AutomationRun.created_at, window.start, window.end)
    previous = _within(AutomationRun.created_at, window.previous_start, window.previous_end)
    row = await _row(
        session,
        select(
            _count_if(current),
            _count_if(previous),
            _count_if(and_(current, AutomationRun.status == AutomationRunStatus.COMPLETED)),
            _count_if(and_(current, AutomationRun.status == AutomationRunStatus.FAILED)),
            _count_if(and_(current, AutomationRun.status == AutomationRunStatus.BLOCKED)),
            _count_if(and_(current, AutomationRun.status == AutomationRunStatus.STOPPED)),
            _count_if(
                and_(current, AutomationRun.created_at >= _start_of_day(window.end))
            ),
        )
        .select_from(AutomationRun)
        .where(
            AutomationRun.created_at >= window.previous_start,
            AutomationRun.created_at < window.end,
        ),
    )
    return {
        "runs": _int(row[0]),
        "runs_previous": _int(row[1]),
        "completed": _int(row[2]),
        "failed": _int(row[3]),
        "blocked": _int(row[4]),
        "stopped": _int(row[5]),
        "runs_today": _int(row[6]),
    }


async def _run_durations(session: AsyncSession, window: Window) -> float | None:
    """Mean seconds a completed run took, averaged in Python on purpose.

    SQLite and PostgreSQL disagree about how to subtract two timestamps, and the
    portable spellings (`julianday`, `EXTRACT(EPOCH ...)`) are backend-specific.
    Reading at most `DURATION_SAMPLE` two-column rows costs less than owning a
    dialect branch.
    """
    rows = (
        await session.execute(
            select(AutomationRun.started_at, AutomationRun.finished_at)
            .where(
                AutomationRun.status == AutomationRunStatus.COMPLETED,
                AutomationRun.started_at.is_not(None),
                AutomationRun.finished_at.is_not(None),
                AutomationRun.created_at >= window.start,
                AutomationRun.created_at < window.end,
            )
            .order_by(AutomationRun.id.desc())
            .limit(DURATION_SAMPLE)
        )
    ).all()
    spans = [
        (finished - started).total_seconds()
        for started, finished in rows
        if finished >= started
    ]
    if not spans:
        return None
    return round(sum(spans) / len(spans), 1)


async def _last_run(session: AsyncSession) -> AutomationRun | None:
    result = await session.execute(
        select(AutomationRun)
        .order_by(AutomationRun.created_at.desc(), AutomationRun.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _ai_counts(session: AsyncSession, window: Window) -> dict[str, Any]:
    current = _within(AIAnalysis.created_at, window.start, window.end)
    previous = _within(AIAnalysis.created_at, window.previous_start, window.previous_end)
    failed = or_(AIAnalysis.error_message.is_not(None), AIAnalysis.was_refusal.is_(True))
    row = await _row(
        session,
        select(
            _count_if(current),
            _count_if(previous),
            _count_if(and_(current, failed)),
            _count_if(and_(previous, failed)),
            _count_if(and_(current, AIAnalysis.was_refusal.is_(True))),
            func.avg(case((current, AIAnalysis.latency_ms))),
            func.sum(case((current, AIAnalysis.input_tokens), else_=0)),
            func.sum(case((current, AIAnalysis.output_tokens), else_=0)),
            func.sum(case((current, AIAnalysis.cost_usd))),
        )
        .select_from(AIAnalysis)
        .where(
            AIAnalysis.created_at >= window.previous_start,
            AIAnalysis.created_at < window.end,
        ),
    )
    return {
        "calls": _int(row[0]),
        "calls_previous": _int(row[1]),
        "failed": _int(row[2]),
        "failed_previous": _int(row[3]),
        "refusals": _int(row[4]),
        "avg_latency_ms": round(float(row[5]), 1) if row[5] is not None else None,
        "tokens_input": _int(row[6]),
        "tokens_output": _int(row[7]),
        # Null, not zero: only some providers report a price, and summing the
        # nulls to zero would read as "this cost nothing".
        "cost_usd": round(float(row[8]), 4) if row[8] is not None else None,
    }


async def _product_metrics(
    session: AsyncSession, window: Window, applications: dict[str, int]
) -> list[Metric]:
    """The "is this product useful" numbers, from the rows that already exist."""
    # Both numbers come from the same scan of the window: the accounts that
    # discovered anything, and how much was discovered.
    jobs_row = await _row(
        session,
        select(
            func.count(func.distinct(Job.user_id)),
            func.count(Job.id),
        ).where(_within(Job.created_at, window.start, window.end)),
    )
    active_owners = _int(jobs_row[0])
    jobs_in_window = _int(jobs_row[1])

    # Applications whose draft a human actually edited before approving it. The
    # trail already records it as USER_EDITED, so this is a count over an indexed
    # event type rather than a new column.
    reviewed = await _row(
        session,
        select(func.count(func.distinct(ApplicationEvent.application_id))).where(
            ApplicationEvent.event_type == ApplicationEventType.USER_EDITED,
            _within(ApplicationEvent.created_at, window.start, window.end),
        ),
    )
    manually_reviewed = _int(reviewed[0])

    # Median would be better than a mean here, and no portable SQL computes one;
    # the sample is capped and averaged in Python for the same reason durations
    # are.
    lag_rows = (
        await session.execute(
            select(Job.created_at, Application.submitted_at)
            .join(Application, Application.job_id == Job.id)
            .where(
                Application.status == ApplicationStatus.SUBMITTED,
                _within(Application.submitted_at, window.start, window.end),
            )
            .order_by(Application.id.desc())
            .limit(DURATION_SAMPLE)
        )
    ).all()
    lags = [
        (submitted - found).total_seconds()
        for found, submitted in lag_rows
        if found is not None and submitted is not None and submitted >= found
    ]
    time_to_apply = round(sum(lags) / len(lags), 1) if lags else None

    submitted = applications["submitted"]
    created = applications["created"]
    return [
        build_metric(
            "approval_rate",
            _rate(applications["approved"], created),
            unit=MetricUnit.PERCENT,
            has_data=created > 0,
        ),
        build_metric(
            "submit_rate",
            _rate(submitted, created),
            unit=MetricUnit.PERCENT,
            has_data=created > 0,
        ),
        build_metric(
            "manual_review_rate",
            _rate(manually_reviewed, created),
            unit=MetricUnit.PERCENT,
            has_data=created > 0,
        ),
        build_metric(
            "time_to_apply",
            time_to_apply,
            unit=MetricUnit.SECONDS,
            has_data=bool(lags),
        ),
        build_metric(
            "applications_per_user",
            round(created / active_owners, 2) if active_owners else None,
            has_data=active_owners > 0,
        ),
        build_metric(
            "jobs_per_user",
            round(jobs_in_window / active_owners, 2) if active_owners else None,
            has_data=active_owners > 0,
        ),
    ]


# --------------------------------------------------------------------------- #
# Growth series
# --------------------------------------------------------------------------- #


async def _series(session: AsyncSession, column: Any, model: Any, window: Window) -> dict[str, int]:
    day = func.date(column)
    rows = (
        await session.execute(
            select(day, func.count())
            .select_from(model)
            .where(_within(column, window.start, window.end))
            .group_by(day)
        )
    ).all()
    return {str(bucket): _int(count) for bucket, count in rows if bucket is not None}


async def _growth(session: AsyncSession, window: Window) -> list[GrowthPoint]:
    """One dense point per calendar day, so a quiet day plots as zero, not a gap."""
    users = await _series(session, User.created_at, User, window)
    jobs = await _series(session, Job.created_at, Job, window)
    applications = await _series(session, Application.created_at, Application, window)

    points: list[GrowthPoint] = []
    cursor = window.start.date()
    last = window.end.date()
    while cursor <= last:
        key = cursor.isoformat()
        points.append(
            GrowthPoint(
                date=key,
                users=users.get(key, 0),
                jobs=jobs.get(key, 0),
                applications=applications.get(key, 0),
            )
        )
        cursor += timedelta(days=1)
    return points


# --------------------------------------------------------------------------- #
# Funnel
# --------------------------------------------------------------------------- #


def _funnel(
    jobs: dict[str, Any], applications: dict[str, int], interviews: int
) -> list[FunnelStage]:
    """Where the flow narrows, stage by stage.

    Each stage counts what happened *inside the window*, not the fate of a single
    cohort: an application submitted today may belong to a posting found last
    month. That is the standard reading of an operational funnel, and it is the
    only one these tables can answer without a cohort column.
    """
    stages: list[tuple[str, int]] = [
        ("jobs_found", jobs["found"]),
        ("jobs_selected", jobs["queued"] + jobs["applied"]),
        ("applications_prepared", applications["created"]),
        ("applications_approved", applications["approved"]),
        ("applications_submitted", applications["submitted"]),
        ("interviews", interviews),
    ]

    first = stages[0][1]
    built: list[FunnelStage] = []
    for index, (key, count) in enumerate(stages):
        previous = stages[index - 1][1] if index else None
        built.append(
            FunnelStage(
                key=key,
                count=count,
                conversion_from_previous=(
                    _rate(count, previous) if previous is not None else None
                ),
                conversion_from_start=_rate(count, first) if index else None,
            )
        )
    return built


# --------------------------------------------------------------------------- #
# Health verdicts
# --------------------------------------------------------------------------- #


def _automation_health(
    counts: dict[str, Any],
    backlog: dict[str, int],
    last_run: AutomationRun | None,
    avg_duration: float | None,
) -> AutomationHealth:
    reasons: list[str] = []
    status = HealthStatus.HEALTHY

    finished = counts["completed"] + counts["failed"] + counts["stopped"]
    failure_rate = _rate(counts["failed"], finished) or 0.0

    if backlog["blocked_runs"]:
        status = HealthStatus.PROBLEM
        reasons.append(
            f"{backlog['blocked_runs']} execução(ões) bloqueada(s) por verificação de segurança."
        )
    if failure_rate >= FAILURE_RATE_CRITICAL and finished >= MIN_ATTEMPTS_FOR_RATE:
        status = HealthStatus.PROBLEM
        reasons.append(f"{counts['failed']} de {finished} execuções falharam no período.")
    elif failure_rate >= FAILURE_RATE_WARNING and finished >= MIN_ATTEMPTS_FOR_RATE:
        if status is HealthStatus.HEALTHY:
            status = HealthStatus.ATTENTION
        reasons.append(f"{counts['failed']} de {finished} execuções falharam no período.")

    if counts["runs"] == 0:
        if status is HealthStatus.HEALTHY:
            status = HealthStatus.ATTENTION
        reasons.append("Nenhuma execução no período selecionado.")
    if not reasons:
        reasons.append("Execuções concluindo normalmente.")

    return AutomationHealth(
        status=status,
        active_runs=backlog["active_runs"],
        runs_in_period=counts["runs"],
        runs_today=counts["runs_today"],
        completed=counts["completed"],
        failed=counts["failed"],
        blocked=counts["blocked"],
        stopped=counts["stopped"],
        last_run_at=last_run.created_at if last_run else None,
        last_run_status=str(last_run.status) if last_run else None,
        avg_duration_seconds=avg_duration,
        reasons=reasons,
    )


def _ai_health(counts: dict[str, Any]) -> AIHealth:
    settings = get_settings()
    provider = settings.resolved_ai_provider
    configured = settings.ai_enabled
    calls = counts["calls"]
    failed = counts["failed"]
    error_rate = _rate(failed, calls) or 0.0

    reasons: list[str] = []
    status = HealthStatus.HEALTHY
    if not configured:
        status = HealthStatus.ATTENTION
        # Deployment-level, and since an account may bring its own key this is
        # no longer the same as "nobody has AI" — saying which one it is keeps
        # the panel from reading as an outage when it is a default.
        reasons.append(
            f"Provider '{provider}' sem credencial ou endpoint configurado. "
            "Contas com chave própria não são afetadas."
        )
    if calls >= MIN_AI_CALLS_FOR_RATE and error_rate >= AI_ERROR_RATE_CRITICAL:
        status = HealthStatus.PROBLEM
        reasons.append(f"{failed} de {calls} chamadas falharam no período.")
    elif calls >= MIN_AI_CALLS_FOR_RATE and error_rate >= AI_ERROR_RATE_WARNING:
        if status is HealthStatus.HEALTHY:
            status = HealthStatus.ATTENTION
        reasons.append(f"{failed} de {calls} chamadas falharam no período.")
    latency = counts["avg_latency_ms"]
    if latency is not None and latency >= AI_SLOW_LATENCY_MS:
        if status is HealthStatus.HEALTHY:
            status = HealthStatus.ATTENTION
        reasons.append(f"Tempo médio de resposta em {latency / 1000:.1f}s.")
    if not reasons:
        reasons.append("Chamadas respondendo dentro do esperado.")

    return AIHealth(
        status=status,
        # The provider *name* and the model, never the key: `Settings.ai_api_key`
        # and `anthropic_api_key` are not read anywhere in this module.
        provider=provider,
        model=settings.ai_model or settings.anthropic_model,
        configured=configured,
        calls=calls,
        succeeded=max(0, calls - failed),
        failed=failed,
        refusals=counts["refusals"],
        avg_latency_ms=latency,
        tokens_input=counts["tokens_input"],
        tokens_output=counts["tokens_output"],
        cost_usd=counts["cost_usd"],
        reasons=reasons,
    )


async def build_system_health(
    session: AsyncSession,
    *,
    automation: AutomationHealth | None = None,
    ai: AIHealth | None = None,
    backlog: dict[str, int] | None = None,
) -> SystemHealth:
    """Per-service status strip.

    The API and the database are probed; the other three reuse verdicts already
    computed above rather than re-deriving them, which is the whole reason this
    takes them as arguments. `/api/health` stays the liveness probe it was — this
    is the operator's view, not a second probe for anything external to poll.
    """
    settings = get_settings()
    services: list[ServiceStatus] = [
        ServiceStatus(
            service="api",
            status=ServiceState.ONLINE,
            detail=f"Versão {__version__} · ambiente {settings.environment}.",
        )
    ]

    try:
        await session.execute(text("SELECT 1"))
        services.append(
            ServiceStatus(
                service="database", status=ServiceState.ONLINE, detail="Consultas respondendo."
            )
        )
    except Exception as exc:  # noqa: BLE001 - the point is to report any failure
        logger.error(
            "The administrative health probe could not reach the database.",
            exc_info=exc,
            extra={"action": "admin.health", "status": "error", "service": "database"},
        )
        services.append(
            ServiceStatus(
                service="database",
                status=ServiceState.OFFLINE,
                detail="A consulta de verificação falhou.",
            )
        )

    if ai is not None:
        services.append(
            ServiceStatus(
                service="ai",
                status=(
                    ServiceState.ONLINE
                    if ai.status is HealthStatus.HEALTHY
                    else ServiceState.ATTENTION
                    if ai.status is HealthStatus.ATTENTION
                    else ServiceState.OFFLINE
                ),
                detail=ai.reasons[0] if ai.reasons else f"Provider {ai.provider}.",
            )
        )

    if automation is not None:
        services.append(
            ServiceStatus(
                service="automation",
                status=(
                    ServiceState.ONLINE
                    if automation.status is HealthStatus.HEALTHY
                    else ServiceState.ATTENTION
                    if automation.status is HealthStatus.ATTENTION
                    else ServiceState.OFFLINE
                ),
                detail=automation.reasons[0] if automation.reasons else "Sem execuções.",
            )
        )

    if backlog is not None:
        depth = backlog["awaiting_review"]
        services.append(
            ServiceStatus(
                service="queue",
                status=(
                    ServiceState.OFFLINE
                    if depth >= QUEUE_BACKLOG_CRITICAL
                    else ServiceState.ATTENTION
                    if depth >= QUEUE_BACKLOG_WARNING
                    else ServiceState.ONLINE
                ),
                detail=(
                    f"{depth} candidatura(s) aguardando revisão · "
                    f"{backlog['active_runs']} execução(ões) ativa(s)."
                ),
            )
        )

    # An honest signal rather than a guess: in development the SPA is served by
    # Vite and this build legitimately does not exist.
    built = (PROJECT_ROOT / "frontend" / "dist" / "index.html").is_file()
    services.append(
        ServiceStatus(
            service="frontend",
            status=ServiceState.ONLINE if built else ServiceState.ATTENTION,
            detail=(
                "Build servido por esta API."
                if built
                else "Sem build em frontend/dist — servido pelo servidor de desenvolvimento."
            ),
        )
    )

    worst = HealthStatus.HEALTHY
    for service in services:
        if service.status is ServiceState.OFFLINE:
            worst = HealthStatus.PROBLEM
            break
        if service.status is ServiceState.ATTENTION:
            worst = HealthStatus.ATTENTION

    return SystemHealth(
        status=worst,
        version=__version__,
        environment=settings.environment,
        services=services,
    )


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #


def _alerts(
    *,
    applications: dict[str, int],
    backlog: dict[str, int],
    automation: AutomationHealth,
    ai: AIHealth,
    health: SystemHealth,
    errors_now: int,
    errors_before: int,
    jobs: dict[str, Any],
) -> list[Alert]:
    """Only conditions a real number crossed. No alert is scheduled or invented."""
    alerts: list[Alert] = []

    attempts = applications["submitted"] + applications["failed"]
    failure_rate = _rate(applications["failed"], attempts) or 0.0
    if attempts >= MIN_ATTEMPTS_FOR_RATE and failure_rate >= FAILURE_RATE_WARNING:
        alerts.append(
            Alert(
                key="application_failures",
                severity=(
                    AlertSeverity.CRITICAL
                    if failure_rate >= FAILURE_RATE_CRITICAL
                    else AlertSeverity.WARNING
                ),
                title="Candidaturas falhando acima do normal",
                detail=(
                    f"{applications['failed']} de {attempts} tentativas terminaram em erro "
                    f"({failure_rate:.0%}) no período."
                ),
                metric="applications_failed",
            )
        )

    if (
        errors_now >= MIN_ERRORS_FOR_SPIKE
        and errors_before > 0
        and errors_now >= errors_before * ERROR_SPIKE_FACTOR
    ):
        alerts.append(
            Alert(
                key="error_spike",
                severity=AlertSeverity.WARNING,
                title="Aumento anormal de erros",
                detail=(
                    f"{errors_now} erros no período contra {errors_before} no período anterior."
                ),
                metric="errors",
            )
        )

    if ai.status is HealthStatus.PROBLEM:
        alerts.append(
            Alert(
                key="ai_failing",
                severity=AlertSeverity.CRITICAL,
                title="Provider de IA com falhas",
                detail=ai.reasons[0],
                metric="ai_failed",
            )
        )
    elif not ai.configured:
        alerts.append(
            Alert(
                key="ai_not_configured",
                severity=AlertSeverity.INFO,
                title="IA sem credencial configurada",
                detail=ai.reasons[0],
                metric="ai_calls",
            )
        )
    elif ai.avg_latency_ms is not None and ai.avg_latency_ms >= AI_SLOW_LATENCY_MS:
        alerts.append(
            Alert(
                key="ai_slow",
                severity=AlertSeverity.WARNING,
                title="Tempo de processamento da IA subindo",
                detail=f"Média de {ai.avg_latency_ms / 1000:.1f}s por chamada no período.",
                metric="ai_latency",
            )
        )

    depth = backlog["awaiting_review"]
    if depth >= QUEUE_BACKLOG_WARNING:
        alerts.append(
            Alert(
                key="review_backlog",
                severity=(
                    AlertSeverity.CRITICAL
                    if depth >= QUEUE_BACKLOG_CRITICAL
                    else AlertSeverity.WARNING
                ),
                title="Fila de revisão crescendo",
                detail=f"{depth} candidaturas preenchidas esperando aprovação humana.",
                metric="awaiting_review",
            )
        )

    if backlog["blocked_runs"]:
        alerts.append(
            Alert(
                key="automation_blocked",
                severity=AlertSeverity.CRITICAL,
                title="Automação parada por verificação",
                detail=(
                    f"{backlog['blocked_runs']} execução(ões) aguardando um humano resolver "
                    "a verificação no navegador."
                ),
                metric="automation_blocked",
            )
        )
    elif automation.runs_in_period == 0 and jobs["queued"] > 0:
        alerts.append(
            Alert(
                key="automation_idle",
                severity=AlertSeverity.WARNING,
                title="Automação parada com vagas na fila",
                detail=(
                    f"{jobs['queued']} vaga(s) aprovada(s) para preparo e nenhuma execução "
                    "no período."
                ),
                metric="jobs_queued",
            )
        )

    for service in health.services:
        if service.status is ServiceState.OFFLINE and service.service == "database":
            alerts.append(
                Alert(
                    key="database_down",
                    severity=AlertSeverity.CRITICAL,
                    title="Banco apresentando erro",
                    detail=service.detail,
                    metric=None,
                )
            )

    order = {AlertSeverity.CRITICAL: 0, AlertSeverity.WARNING: 1, AlertSeverity.INFO: 2}
    alerts.sort(key=lambda alert: order[alert.severity])
    return alerts


# --------------------------------------------------------------------------- #
# Recent errors and activity
# --------------------------------------------------------------------------- #


def _summarise(message: str | None, fallback: str) -> str:
    text_value = (message or "").strip().splitlines()
    first = text_value[0].strip() if text_value else ""
    if not first:
        return fallback
    return first if len(first) <= SUMMARY_CHARS else f"{first[:SUMMARY_CHARS - 1]}…"


async def count_errors(session: AsyncSession, start: datetime, end: datetime) -> int:
    """How many failures the three sources recorded in one window."""
    runs = await _row(
        session,
        select(func.count())
        .select_from(AutomationRun)
        .where(
            AutomationRun.status.in_(
                (AutomationRunStatus.FAILED, AutomationRunStatus.BLOCKED)
            ),
            _within(AutomationRun.created_at, start, end),
        ),
    )
    analyses = await _row(
        session,
        select(func.count())
        .select_from(AIAnalysis)
        .where(
            or_(AIAnalysis.error_message.is_not(None), AIAnalysis.was_refusal.is_(True)),
            _within(AIAnalysis.created_at, start, end),
        ),
    )
    events = await _row(
        session,
        select(func.count())
        .select_from(ApplicationEvent)
        .where(
            ApplicationEvent.is_error.is_(True),
            _within(ApplicationEvent.created_at, start, end),
        ),
    )
    return _int(runs[0]) + _int(analyses[0]) + _int(events[0])


async def list_errors(
    session: AsyncSession, window: Window, *, limit: int = ERRORS_LIMIT
) -> list[ErrorEntry]:
    """The most recent failures across automation, AI and application trails.

    Each source is queried with the same `limit` and the merged list is trimmed:
    reading `3 * limit` rows is what makes "newest across all three" correct
    without a UNION that three different backends spell three different ways.
    """
    entries: list[ErrorEntry] = []

    runs = (
        await session.execute(
            select(AutomationRun)
            .where(
                AutomationRun.status.in_(
                    (AutomationRunStatus.FAILED, AutomationRunStatus.BLOCKED)
                ),
                _within(AutomationRun.created_at, window.start, window.end),
            )
            .order_by(AutomationRun.created_at.desc(), AutomationRun.id.desc())
            .limit(limit)
        )
    ).scalars()
    for run in runs:
        blocked = run.status == AutomationRunStatus.BLOCKED
        entries.append(
            ErrorEntry(
                id=f"automation:{run.id}",
                occurred_at=run.finished_at or run.created_at,
                source="automation",
                kind=str(run.kind),
                summary=_summarise(
                    run.blocked_reason if blocked else run.error_message,
                    "Execução bloqueada." if blocked else "Execução falhou.",
                ),
                detail=f"Execução #{run.id} · {run.status}",
            )
        )

    analyses = (
        await session.execute(
            select(AIAnalysis)
            .where(
                or_(
                    AIAnalysis.error_message.is_not(None), AIAnalysis.was_refusal.is_(True)
                ),
                _within(AIAnalysis.created_at, window.start, window.end),
            )
            .order_by(AIAnalysis.created_at.desc(), AIAnalysis.id.desc())
            .limit(limit)
        )
    ).scalars()
    for analysis in analyses:
        entries.append(
            ErrorEntry(
                id=f"ai:{analysis.id}",
                occurred_at=analysis.created_at,
                source="ai",
                kind=str(analysis.kind),
                summary=_summarise(
                    analysis.error_message,
                    "O modelo recusou a solicitação."
                    if analysis.was_refusal
                    else "Falha na chamada.",
                ),
                detail=analysis.model,
            )
        )

    events = (
        await session.execute(
            select(ApplicationEvent)
            .where(
                ApplicationEvent.is_error.is_(True),
                _within(ApplicationEvent.created_at, window.start, window.end),
            )
            .order_by(ApplicationEvent.created_at.desc(), ApplicationEvent.id.desc())
            .limit(limit)
        )
    ).scalars()
    for event in events:
        entries.append(
            ErrorEntry(
                id=f"application:{event.id}",
                occurred_at=event.created_at,
                source="application",
                kind=str(event.event_type),
                summary=_summarise(event.message, "Erro durante a candidatura."),
                detail=f"Candidatura #{event.application_id}",
            )
        )

    entries.sort(key=lambda entry: entry.occurred_at, reverse=True)
    return entries[:limit]


def _mask_email(email: str) -> str:
    """`alex@example.com` -> `a***@example.com`.

    The timeline says that somebody signed up, which is the operational fact.
    The full address is one click away in Usuários, where it is the point.
    """
    local, _, domain = email.partition("@")
    if not domain:
        return "conta nova"
    head = local[:1] or "?"
    return f"{head}***@{domain}"


_ACTIVITY_EVENTS: dict[str, tuple[str, str]] = {
    "submitted": ("Candidatura enviada", "success"),
    "awaiting_review": ("Candidatura aguardando revisão", "info"),
    "user_approved": ("Candidatura aprovada", "success"),
    "job_analyzed": ("Vaga analisada", "info"),
    "error": ("Erro durante a candidatura", "error"),
}


async def list_activity(
    session: AsyncSession, window: Window, *, limit: int = ACTIVITY_LIMIT
) -> list[ActivityEntry]:
    """Notable platform events, newest first — a timeline, not a log."""
    entries: list[ActivityEntry] = []

    signups = (
        await session.execute(
            select(User.id, User.email, User.created_at)
            .where(_within(User.created_at, window.start, window.end))
            .order_by(User.created_at.desc())
            .limit(limit)
        )
    ).all()
    for user_id, email, created_at in signups:
        entries.append(
            ActivityEntry(
                id=f"user:{user_id}",
                occurred_at=created_at,
                kind="user_registered",
                summary=f"Novo usuário cadastrado ({_mask_email(email)})",
                level="success",
            )
        )

    events = (
        await session.execute(
            select(ApplicationEvent)
            .where(
                ApplicationEvent.event_type.in_(tuple(_ACTIVITY_EVENTS)),
                _within(ApplicationEvent.created_at, window.start, window.end),
            )
            .order_by(ApplicationEvent.created_at.desc(), ApplicationEvent.id.desc())
            .limit(limit)
        )
    ).scalars()
    for event in events:
        label, level = _ACTIVITY_EVENTS.get(str(event.event_type), ("Evento", "info"))
        entries.append(
            ActivityEntry(
                id=f"event:{event.id}",
                occurred_at=event.created_at,
                kind=str(event.event_type),
                summary=f"{label} · candidatura #{event.application_id}",
                level=level,
            )
        )

    runs = (
        await session.execute(
            select(AutomationRun)
            .where(
                AutomationRun.status.in_(
                    (
                        AutomationRunStatus.COMPLETED,
                        AutomationRunStatus.STOPPED,
                        AutomationRunStatus.FAILED,
                        AutomationRunStatus.BLOCKED,
                    )
                ),
                _within(AutomationRun.created_at, window.start, window.end),
            )
            .order_by(AutomationRun.created_at.desc(), AutomationRun.id.desc())
            .limit(limit)
        )
    ).scalars()
    _RUN_LEVEL = {
        AutomationRunStatus.COMPLETED: "success",
        AutomationRunStatus.STOPPED: "warning",
        AutomationRunStatus.FAILED: "error",
        AutomationRunStatus.BLOCKED: "error",
    }
    for run in runs:
        entries.append(
            ActivityEntry(
                id=f"run:{run.id}",
                occurred_at=run.finished_at or run.created_at,
                kind=f"run_{run.status}",
                summary=(
                    f"Execução de {run.kind} #{run.id} · {run.status} "
                    f"({run.jobs_found} vagas, {run.applications_prepared} preparos)"
                ),
                level=_RUN_LEVEL.get(run.status, "info"),
            )
        )

    entries.sort(key=lambda entry: entry.occurred_at, reverse=True)
    return entries[:limit]


# --------------------------------------------------------------------------- #
# Usage
# --------------------------------------------------------------------------- #


async def list_usage(session: AsyncSession, *, limit: int = USAGE_LIMIT) -> list[UsageRow]:
    """The accounts using the product most, by number of applications.

    Ordered by a grouped count over `applications` rather than a correlated
    subquery per user: the group-by touches only accounts that have applied at
    all, and the follow-up queries run for at most `limit` ids.
    """
    top = (
        await session.execute(
            select(Application.user_id, func.count(Application.id))
            .group_by(Application.user_id)
            .order_by(func.count(Application.id).desc())
            .limit(limit)
        )
    ).all()
    if not top:
        return []

    user_ids = [int(user_id) for user_id, _ in top]
    application_counts = {int(user_id): _int(count) for user_id, count in top}

    submitted = {
        int(user_id): _int(count)
        for user_id, count in (
            await session.execute(
                select(Application.user_id, func.count(Application.id))
                .where(
                    Application.user_id.in_(user_ids),
                    Application.status == ApplicationStatus.SUBMITTED,
                )
                .group_by(Application.user_id)
            )
        ).all()
    }
    job_counts = {
        int(user_id): _int(count)
        for user_id, count in (
            await session.execute(
                select(Job.user_id, func.count(Job.id))
                .where(Job.user_id.in_(user_ids))
                .group_by(Job.user_id)
            )
        ).all()
    }
    last_activity = {
        int(user_id): moment
        for user_id, moment in (
            await session.execute(
                select(Application.user_id, func.max(Application.updated_at))
                .where(Application.user_id.in_(user_ids))
                .group_by(Application.user_id)
            )
        ).all()
    }
    users = (
        await session.execute(select(User).where(User.id.in_(user_ids)))
    ).scalars()
    by_id = {user.id: user for user in users}

    rows: list[UsageRow] = []
    for user_id in user_ids:
        user = by_id.get(user_id)
        if user is None:
            continue
        rows.append(
            UsageRow(
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                jobs=job_counts.get(user_id, 0),
                applications=application_counts.get(user_id, 0),
                submitted=submitted.get(user_id, 0),
                last_activity_at=last_activity.get(user_id) or user.last_login_at,
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #


def _escape_like(term: str) -> str:
    """Neutralise the `LIKE` wildcards inside a term the admin typed.

    Not an injection defence — the value is bound as a parameter either way —
    but a correctness one: searching for `100%` or `a_b` otherwise matches
    everything, which reads as a broken search rather than as a wildcard nobody
    asked for. The backslash is escaped first, or it would escape the escapes.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _user_filter(statement: Select[Any], choice: AdminUserFilter, window: Window) -> Select[Any]:
    has_application = (
        select(Application.id).where(Application.user_id == User.id).exists()
    )
    if choice is AdminUserFilter.ACTIVE:
        return statement.where(User.is_active.is_(True))
    if choice is AdminUserFilter.INACTIVE:
        return statement.where(User.is_active.is_(False))
    if choice is AdminUserFilter.NEW:
        return statement.where(_within(User.created_at, window.start, window.end))
    if choice is AdminUserFilter.WITH_APPLICATIONS:
        return statement.where(has_application)
    if choice is AdminUserFilter.WITHOUT_APPLICATIONS:
        return statement.where(~has_application)
    return statement


async def list_users(
    session: AsyncSession,
    window: Window,
    *,
    search: str | None = None,
    user_filter: AdminUserFilter = AdminUserFilter.ALL,
    limit: int = 25,
    offset: int = 0,
) -> Page[AdminUserRow]:
    """One page of accounts with their counters.

    The counters are *not* correlated subqueries in the main statement: that
    would evaluate two counts for every account in the table just to sort by
    registration date. The page is selected first, then three grouped counts run
    for the handful of ids it contains.
    """
    statement = select(User)
    if search:
        pattern = f"%{_escape_like(search.strip().lower())}%"
        statement = statement.where(
            or_(
                func.lower(User.email).like(pattern, escape="\\"),
                func.lower(func.coalesce(User.full_name, "")).like(pattern, escape="\\"),
            )
        )
    statement = _user_filter(statement, user_filter, window)

    total = _int(
        (
            await session.execute(
                select(func.count()).select_from(statement.subquery())
            )
        ).scalar_one()
    )
    users = list(
        (
            await session.execute(
                statement.order_by(User.created_at.desc(), User.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    if not users:
        return Page[AdminUserRow](items=[], total=total, limit=limit, offset=offset)

    user_ids = [user.id for user in users]
    job_counts = {
        int(user_id): _int(count)
        for user_id, count in (
            await session.execute(
                select(Job.user_id, func.count(Job.id))
                .where(Job.user_id.in_(user_ids))
                .group_by(Job.user_id)
            )
        ).all()
    }
    application_rows = (
        await session.execute(
            select(
                Application.user_id,
                func.count(Application.id),
                _count_if(Application.status == ApplicationStatus.SUBMITTED),
            )
            .where(Application.user_id.in_(user_ids))
            .group_by(Application.user_id)
        )
    ).all()
    applications = {int(row[0]): (_int(row[1]), _int(row[2])) for row in application_rows}

    items = [
        AdminUserRow(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            jobs=job_counts.get(user.id, 0),
            applications=applications.get(user.id, (0, 0))[0],
            submitted=applications.get(user.id, (0, 0))[1],
        )
        for user in users
    ]
    return Page[AdminUserRow](items=items, total=total, limit=limit, offset=offset)


# --------------------------------------------------------------------------- #
# Job insights
# --------------------------------------------------------------------------- #


async def _top(
    session: AsyncSession, column: Any, window: Window, *, limit: int = TOP_LABELS
) -> list[LabelCount]:
    rows = (
        await session.execute(
            select(column, func.count(Job.id))
            .select_from(Job)
            .where(_within(Job.created_at, window.start, window.end), column.is_not(None))
            .group_by(column)
            .order_by(func.count(Job.id).desc())
            .limit(limit)
        )
    ).all()
    return [
        LabelCount(label=str(label).strip() or "(não informado)", count=_int(count))
        for label, count in rows
        if str(label).strip()
    ]


async def build_job_insights(session: AsyncSession, window: Window) -> JobInsights:
    """What the platform is finding, in aggregate.

    Everything but `top_technologies` is a grouped count. That one reads posting
    text, because no column stores a technology list — so it is capped at
    `TECHNOLOGY_SAMPLE` of the most recent postings in the window and reports how
    many it read. If this ever needs to be exact, the fix is a `job_technologies`
    column written at discovery time, not a bigger sample here.
    """
    counts = await _row(
        session,
        select(
            func.count(Job.id),
            _count_if(Job.status.in_(RECOMMENDED_STATUSES)),
            _count_if(Job.status == JobStatus.SKIPPED),
            _count_if(Job.status == JobStatus.APPLIED),
            _count_if(Job.expired_at.is_not(None)),
            func.avg(Job.score),
            _count_if(Job.easy_apply.is_(True)),
        )
        .select_from(Job)
        .where(_within(Job.created_at, window.start, window.end)),
    )
    total = _int(counts[0])

    rows = (
        await session.execute(
            select(Job.title, Job.description)
            .where(_within(Job.created_at, window.start, window.end))
            .order_by(Job.id.desc())
            .limit(TECHNOLOGY_SAMPLE)
        )
    ).all()
    tally: dict[str, int] = {}
    for title, description in rows:
        text_value = f"{title or ''}\n{description or ''}"
        # `job_technologies` returns each term once per posting, so this counts
        # postings mentioning a technology, not mentions of it.
        for term in job_technologies(text_value):
            tally[term] = tally.get(term, 0) + 1
    technologies = [
        LabelCount(label=term, count=count)
        for term, count in sorted(tally.items(), key=lambda item: (-item[1], item[0]))[:TOP_LABELS]
    ]

    return JobInsights(
        total=total,
        recommended=_int(counts[1]),
        discarded=_int(counts[2]),
        applied=_int(counts[3]),
        expired=_int(counts[4]),
        average_score=round(float(counts[5]), 1) if counts[5] is not None else None,
        easy_apply_share=_rate(_int(counts[6]), total),
        top_titles=await _top(session, Job.title, window),
        top_companies=await _top(session, Job.company, window),
        top_locations=await _top(session, Job.location, window),
        top_sources=await _top(session, Job.source, window),
        top_technologies=technologies,
        technologies_sampled=len(rows),
    )


# --------------------------------------------------------------------------- #
# The overview
# --------------------------------------------------------------------------- #

_cache: dict[tuple[Any, ...], tuple[float, AdminOverview]] = {}


def _cache_key(window: Window) -> tuple[Any, ...]:
    """Identify a window without its moving edge.

    A preset window always ends at "now", so putting `end` in the key gives every
    request a fresh timestamp and the cache never hits — which is how the first
    version of this managed to memoise nothing at all. Freshness is the TTL's
    job; the key only has to say *which* window. A custom range has a fixed end,
    and that one is part of its identity.
    """
    end = window.end.isoformat() if window.period is AdminPeriod.CUSTOM else "now"
    return (window.period.value, window.start.isoformat(), end)


def clear_cache() -> None:
    """Drop every memoised overview. Called by the tests and by `refresh=True`."""
    _cache.clear()


async def build_overview(
    session: AsyncSession, window: Window, *, refresh: bool = False
) -> AdminOverview:
    """Everything the dashboard's first screen shows, in ~18 aggregate queries.

    Memoised for `CACHE_TTL_SECONDS` per resolved window. The cache is
    process-local, which matches how this application is deployed (one uvicorn
    process); behind several workers it would simply mean each worker warms its
    own copy, never a wrong number.
    """
    key = _cache_key(window)
    now = time.monotonic()
    if not refresh:
        hit = _cache.get(key)
        if hit is not None and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]

    users = await _user_counts(session, window)
    jobs = await _job_counts(session, window)
    applications = await _application_counts(session, window)
    backlog = await _backlog_counts(session)
    interviews = await _interview_counts(session, window)
    automation_counts = await _automation_counts(session, window)
    ai_counts = await _ai_counts(session, window)

    automation = _automation_health(
        automation_counts,
        backlog,
        await _last_run(session),
        await _run_durations(session, window),
    )
    ai = _ai_health(ai_counts)
    health = await build_system_health(
        session, automation=automation, ai=ai, backlog=backlog
    )

    attempts = applications["submitted"] + applications["failed"]
    attempts_previous = applications["submitted_previous"] + applications["failed_previous"]
    success_rate = _rate(applications["submitted"], attempts)
    success_rate_previous = _rate(applications["submitted_previous"], attempts_previous)

    headline = [
        build_metric("users", users["total"], previous=users["total_previous"]),
        build_metric("jobs_found", jobs["found"], previous=jobs["found_previous"]),
        build_metric(
            "applications", applications["created"], previous=applications["created_previous"]
        ),
        build_metric(
            "success_rate",
            success_rate,
            previous=success_rate_previous,
            unit=MetricUnit.PERCENT,
            has_data=attempts > 0,
        ),
    ]

    operational = [
        build_metric(
            "applications_submitted",
            applications["submitted"],
            previous=applications["submitted_previous"],
        ),
        build_metric("awaiting_review", backlog["awaiting_review"]),
        build_metric(
            "applications_failed",
            applications["failed"],
            previous=applications["failed_previous"],
        ),
        build_metric(
            "interviews", interviews["interviews"], previous=interviews["interviews_previous"]
        ),
        build_metric("active_runs", backlog["active_runs"]),
        build_metric("active_users", users["active"], previous=users["active_previous"]),
    ]

    errors_now = await count_errors(session, window.start, window.end)
    errors_before = await count_errors(session, window.previous_start, window.previous_end)

    overview = AdminOverview(
        period=window.to_info(),
        generated_at=utcnow(),
        headline=headline,
        operational=operational,
        product=await _product_metrics(session, window, applications),
        funnel=_funnel(jobs, applications, interviews["interviews"]),
        growth=await _growth(session, window),
        automation=automation,
        ai=ai,
        health=health,
        alerts=_alerts(
            applications=applications,
            backlog=backlog,
            automation=automation,
            ai=ai,
            health=health,
            errors_now=errors_now,
            errors_before=errors_before,
            jobs=jobs,
        ),
        usage=await list_usage(session),
        errors=await list_errors(session, window),
        activity=await list_activity(session, window),
    )

    if len(_cache) >= _CACHE_MAX_ENTRIES:
        _cache.clear()
    _cache[key] = (now, overview)
    return overview


# --------------------------------------------------------------------------- #
# Auditing the panel itself
# --------------------------------------------------------------------------- #

# Which admins already have an access row for which UTC day, so a page that
# refreshes every thirty seconds writes one row, not two thousand. Process-local:
# a restart may write one extra row for the day, which is harmless, and the
# alternative (a lookup query per request) buys nothing.
_access_recorded: dict[int, date] = {}


async def record_panel_access(session: AsyncSession, admin: User) -> None:
    """Record that an administrator opened the panel — once per admin per day.

    Read access is audited here and nowhere else in the area: the fact worth
    keeping is that the account with platform-wide visibility used it. Auditing
    every request would drown the same trail that records a loosened guardrail.
    """
    today = utcnow().date()
    if _access_recorded.get(admin.id) == today:
        return
    _access_recorded[admin.id] = today
    await record_audit_event(
        session,
        user_id=admin.id,
        action=AuditAction.ADMIN_ACCESS,
        subject_type="admin_panel",
        after={"date": today.isoformat()},
    )


async def list_admin_audit(
    session: AsyncSession, *, limit: int = 50
) -> list[AuditEvent]:
    """Administrative actions recorded so far, newest first."""
    result = await session.execute(
        select(AuditEvent)
        .where(AuditEvent.action == AuditAction.ADMIN_ACCESS)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
