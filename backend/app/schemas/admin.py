"""Platform-wide metrics for the administrative panel.

Everything here is *aggregate*: counts, rates and health verdicts across every
account. No endpoint in `app.api.routes.admin` returns a resume, a cover letter,
a screening answer or a stored credential, and these schemas are the reason —
there is no field to put them in.

The metric list is deliberately generic (`key` + value + comparison) rather than
one named field per number. The panel renders a grid of tiles from it, so adding
an indicator is a service change and a label, not a schema migration plus a
frontend refactor.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class AdminPeriod(StrEnum):
    """The windows the panel filters by.

    `CUSTOM` requires explicit `start`/`end` query parameters; every other value
    is resolved against "now" by `admin_service.resolve_period`.
    """

    TODAY = "today"
    LAST_7_DAYS = "7d"
    LAST_30_DAYS = "30d"
    LAST_90_DAYS = "90d"
    CUSTOM = "custom"


class MetricTrend(StrEnum):
    """Which way a metric moved, once "moved at all" was decided.

    `NONE` is not a synonym for `FLAT`: it means the comparison is not
    answerable (no previous period, or a previous value of zero, where a
    percentage change is either infinite or meaningless).
    """

    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    NONE = "none"


class MetricUnit(StrEnum):
    COUNT = "count"
    PERCENT = "percent"  # 0..1
    SECONDS = "seconds"
    MILLISECONDS = "milliseconds"
    USD = "usd"


class HealthStatus(StrEnum):
    """One vocabulary for every "is this part working" verdict on the panel."""

    HEALTHY = "healthy"
    ATTENTION = "attention"
    PROBLEM = "problem"


class ServiceState(StrEnum):
    ONLINE = "online"
    ATTENTION = "attention"
    OFFLINE = "offline"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class PeriodInfo(BaseModel):
    """The window the numbers were computed over, and what they compare against.

    Returned rather than assumed: the panel prints "vs. período anterior", and
    that claim is only honest if the client can see which window that was.
    """

    period: AdminPeriod
    start: datetime
    end: datetime
    previous_start: datetime
    previous_end: datetime
    days: int


class Metric(BaseModel):
    """One number, with the comparison the panel needs to show a trend.

    `value` is period-scoped for flow metrics (jobs found, applications created)
    and a running total for stock metrics (registered users); `key` tells the
    client which it is, because the two want different wording.
    """

    key: str
    value: float
    unit: MetricUnit = MetricUnit.COUNT
    previous: float | None = None
    # How much it moved, and the meaning depends on the unit — see
    # `admin_service.build_metric`. For a COUNT it is the relative change
    # ((new - old) / old), e.g. 0.142 for +14.2%. For a PERCENT it is the
    # difference in *points* (0.62 vs 0.54 -> 0.08), because reporting a rate's
    # relative change turns "54% to 62%" into a flattering "+14.8%". Null
    # whenever `trend` is NONE.
    delta_pct: float | None = None
    trend: MetricTrend = MetricTrend.NONE
    # A metric whose value nobody can act on yet (no data at all) is still
    # returned, so the tile can say "sem dados" instead of vanishing.
    has_data: bool = True


class FunnelStage(BaseModel):
    """One step of found -> selected -> prepared -> approved -> sent -> interview.

    Conversions are null until there is something to divide by, which is what
    keeps a fresh install from reporting a 0% funnel as if it were a problem.
    """

    key: str
    count: int
    conversion_from_previous: float | None = None
    conversion_from_start: float | None = None


class GrowthPoint(BaseModel):
    """One day of the growth chart. All three series share the x axis."""

    date: str  # ISO (YYYY-MM-DD)
    users: int = 0
    jobs: int = 0
    applications: int = 0


class AutomationHealth(BaseModel):
    """Whether the automation is running, and whether it is finishing.

    `next_run_at` is always null and `scheduling` says why: this deployment has
    no scheduler — every run is started by a user, which is the assisted-mode
    guarantee, not a missing feature. Reporting a made-up "next run" would be
    the one number on this panel that could not be checked.
    """

    status: HealthStatus
    active_runs: int = 0
    runs_in_period: int = 0
    runs_today: int = 0
    completed: int = 0
    failed: int = 0
    blocked: int = 0
    stopped: int = 0
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    next_run_at: None = None
    scheduling: str = "on_demand"
    avg_duration_seconds: float | None = None
    # Plain-language reasons behind `status`, so the verdict can be argued with.
    reasons: list[str] = Field(default_factory=list)


class AIHealth(BaseModel):
    """Whether the AI provider is answering, and what it cost.

    `cost_usd` is null when no analysis carried a price: the field exists on
    `ai_analyses` but only some providers report one, and summing nulls to zero
    would read as "free".
    """

    status: HealthStatus
    provider: str
    model: str
    configured: bool
    calls: int = 0
    succeeded: int = 0
    failed: int = 0
    refusals: int = 0
    avg_latency_ms: float | None = None
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float | None = None
    reasons: list[str] = Field(default_factory=list)


class ServiceStatus(BaseModel):
    """One row of the "Status do sistema" strip."""

    service: str  # api | database | ai | automation | queue | frontend
    status: ServiceState
    detail: str


class SystemHealth(BaseModel):
    status: HealthStatus
    version: str
    environment: str
    services: list[ServiceStatus] = Field(default_factory=list)


class Alert(BaseModel):
    """A problem worth an administrator's attention, derived from a real metric.

    `metric` names the number that triggered it so the alert can be verified
    against the tile it came from, rather than being taken on faith.
    """

    key: str
    severity: AlertSeverity
    title: str
    detail: str
    metric: str | None = None


class ErrorEntry(BaseModel):
    """One recent failure, summarised.

    Never a stack trace and never a payload: `summary` is the message the
    application itself wrote for a human, truncated. The three sources
    (automation runs, AI analyses, application events) are merged and sorted by
    time, which is how an administrator reads them anyway.
    """

    id: str  # "<source>:<row id>" — unique across the merged sources
    occurred_at: datetime
    source: str  # automation | ai | application
    kind: str
    summary: str
    detail: str | None = None
    count: int = 1


class ActivityEntry(BaseModel):
    """One notable platform event, for the timeline."""

    id: str
    occurred_at: datetime
    kind: str
    summary: str
    level: str = "info"  # info | success | warning | error


class UsageRow(BaseModel):
    """How much of the product one account is actually using.

    Ordered by activity so the panel can answer "is anyone using this", never
    presented as a ranking: the label is usage, and no position is shown.
    """

    user_id: int
    email: str
    full_name: str | None = None
    jobs: int = 0
    applications: int = 0
    submitted: int = 0
    last_activity_at: datetime | None = None


class AdminUserRow(BaseModel):
    """Administrative view of one account.

    Contact details and counters only. The profile, the resume, the answer bank
    and the LinkedIn session are all absent on purpose: the panel exists to
    answer "who is using this and how much", and none of that is needed for it.
    """

    id: int
    email: str
    full_name: str | None = None
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    jobs: int = 0
    applications: int = 0
    submitted: int = 0


class AdminUserFilter(StrEnum):
    ALL = "all"
    ACTIVE = "active"
    INACTIVE = "inactive"
    NEW = "new"  # registered inside the selected period
    WITH_APPLICATIONS = "with_applications"
    WITHOUT_APPLICATIONS = "without_applications"


class LabelCount(BaseModel):
    label: str
    count: int


class JobInsights(BaseModel):
    """What the platform is finding, in aggregate.

    `top_technologies` is extracted from the postings' own text with the
    existing `app.domain.technologies` vocabulary. It is the one metric here
    that reads rows instead of aggregating them, so it is capped
    (`technologies_sampled` says how many postings were read) — see the
    docstring on `admin_service.build_job_insights`.
    """

    total: int = 0
    recommended: int = 0
    discarded: int = 0
    applied: int = 0
    expired: int = 0
    average_score: float | None = None
    easy_apply_share: float | None = None
    top_titles: list[LabelCount] = Field(default_factory=list)
    top_companies: list[LabelCount] = Field(default_factory=list)
    top_locations: list[LabelCount] = Field(default_factory=list)
    top_sources: list[LabelCount] = Field(default_factory=list)
    top_technologies: list[LabelCount] = Field(default_factory=list)
    technologies_sampled: int = 0


class AdminOverview(BaseModel):
    """Everything the dashboard's first screen needs, in one response.

    One composite payload rather than nine endpoints: the panel would otherwise
    fan out nine requests that each re-derive the same period bounds, and the
    numbers on screen could come from different instants. `generated_at` is when
    this snapshot was computed — it may predate the request by up to the service's
    cache TTL.
    """

    period: PeriodInfo
    generated_at: datetime
    headline: list[Metric] = Field(default_factory=list)
    operational: list[Metric] = Field(default_factory=list)
    product: list[Metric] = Field(default_factory=list)
    funnel: list[FunnelStage] = Field(default_factory=list)
    growth: list[GrowthPoint] = Field(default_factory=list)
    automation: AutomationHealth
    ai: AIHealth
    health: SystemHealth
    alerts: list[Alert] = Field(default_factory=list)
    usage: list[UsageRow] = Field(default_factory=list)
    errors: list[ErrorEntry] = Field(default_factory=list)
    activity: list[ActivityEntry] = Field(default_factory=list)
