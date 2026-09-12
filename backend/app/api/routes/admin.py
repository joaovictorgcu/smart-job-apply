"""Administrative API — platform-wide, admin-only.

Authorization is declared **once**, on the router, as a dependency every route
inherits. Putting it on each endpoint would work until somebody adds the tenth
one and forgets, and the thing being protected here is every account's data at
once. A normal session that calls any path below gets 403 from
`get_current_admin`, whether it arrives through the panel or with curl.

Every response is an aggregate or a counter. Nothing in `app.schemas.admin` has
a field for a resume, a cover letter, a screening answer or a credential, so
there is no version of this router that leaks one by accident.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import AdminUser, SessionDep
from app.auth.dependencies import get_current_admin
from app.schemas.admin import (
    ActivityEntry,
    AdminOverview,
    AdminPeriod,
    AdminUserFilter,
    AdminUserRow,
    ErrorEntry,
    JobInsights,
    SystemHealth,
)
from app.schemas.common import Page
from app.schemas.user import AuditEventRead
from app.services import admin_service
from app.services.admin_service import Window

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin)],
    responses={403: {"description": "The account is not an administrator."}},
)

PeriodDep = Annotated[AdminPeriod, Query(description="Window the metrics cover.")]
StartDep = Annotated[date | None, Query(description="First day, for period=custom.")]
EndDep = Annotated[date | None, Query(description="Last day (inclusive), for period=custom.")]
RefreshDep = Annotated[
    bool, Query(description="Skip the short-lived cache and recompute now.")
]


def _window(period: AdminPeriod, start: date | None, end: date | None) -> Window:
    """Resolve the query parameters into concrete bounds, or reject them (422)."""
    return admin_service.resolve_period(period, start=start, end=end)


@router.get("/overview", response_model=AdminOverview)
async def read_overview(
    admin: AdminUser,
    session: SessionDep,
    period: PeriodDep = AdminPeriod.LAST_7_DAYS,
    start: StartDep = None,
    end: EndDep = None,
    refresh: RefreshDep = False,
) -> AdminOverview:
    """The whole first screen: headline and operational metrics, product rates,
    the funnel, the growth series, automation and AI health, system status,
    alerts, platform usage, recent errors and the activity timeline.

    One request rather than nine so every number on screen shares one instant.
    The result is cached briefly per window; `refresh=true` is what the
    "Atualizar dados" button sends.
    """
    window = _window(period, start, end)
    # Recorded once per admin per day, not per request — see the service.
    await admin_service.record_panel_access(session, admin)
    return await admin_service.build_overview(session, window, refresh=refresh)


@router.get("/users", response_model=Page[AdminUserRow])
async def read_users(
    session: SessionDep,
    period: PeriodDep = AdminPeriod.LAST_30_DAYS,
    start: StartDep = None,
    end: EndDep = None,
    search: Annotated[str | None, Query(max_length=200, description="Email or name.")] = None,
    user_filter: Annotated[AdminUserFilter, Query(alias="filter")] = AdminUserFilter.ALL,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AdminUserRow]:
    """Accounts with their activity counters, paginated.

    `period` only affects the `new` filter — "registered in the selected window".
    The counters are lifetime totals, which is what "quantas vagas / quantas
    candidaturas" means for an account.
    """
    window = _window(period, start, end)
    return await admin_service.list_users(
        session,
        window,
        search=search,
        user_filter=user_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/jobs", response_model=JobInsights)
async def read_job_insights(
    session: SessionDep,
    period: PeriodDep = AdminPeriod.LAST_30_DAYS,
    start: StartDep = None,
    end: EndDep = None,
) -> JobInsights:
    """What the platform found in the window: volumes, scores, and the leading
    titles, companies, locations, sources and technologies."""
    window = _window(period, start, end)
    return await admin_service.build_job_insights(session, window)


@router.get("/errors", response_model=list[ErrorEntry])
async def read_errors(
    session: SessionDep,
    period: PeriodDep = AdminPeriod.LAST_7_DAYS,
    start: StartDep = None,
    end: EndDep = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ErrorEntry]:
    """Recent failures from the automation runs, the AI calls and the application
    trails, merged and newest first.

    Summaries only: the messages these tables store are the ones the application
    wrote for a human. Tracebacks go to the logs with `exc_info` and are never
    persisted, so none can surface here.
    """
    window = _window(period, start, end)
    return await admin_service.list_errors(session, window, limit=limit)


@router.get("/activity", response_model=list[ActivityEntry])
async def read_activity(
    session: SessionDep,
    period: PeriodDep = AdminPeriod.LAST_7_DAYS,
    start: StartDep = None,
    end: EndDep = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[ActivityEntry]:
    """Notable platform events as a timeline. Signup addresses are masked."""
    window = _window(period, start, end)
    return await admin_service.list_activity(session, window, limit=limit)


@router.get("/health", response_model=SystemHealth)
async def read_health(session: SessionDep) -> SystemHealth:
    """Per-service status for the operator.

    Distinct from the unauthenticated `/api/health`, which stays a liveness probe
    for a load balancer. This one probes the database and reports the AI provider
    and the frontend build, which is not information a public endpoint should
    carry.
    """
    return await admin_service.build_system_health(session)


@router.get("/audit", response_model=list[AuditEventRead])
async def read_admin_audit(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[AuditEventRead]:
    """Administrative accesses recorded so far, newest first."""
    events = await admin_service.list_admin_audit(session, limit=limit)
    return [AuditEventRead.model_validate(event) for event in events]
