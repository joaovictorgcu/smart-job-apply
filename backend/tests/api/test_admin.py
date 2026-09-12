"""The administrative area: who may read it, and whether the numbers are real.

Two groups of tests, and the first matters more. Authorization is asserted
against *every* path the router exposes, collected from the app itself rather
than typed out here — a new endpoint that forgets the dependency fails these
tests instead of shipping.

The metric tests each seed rows with explicit timestamps and then assert the
aggregate, because the whole value of the panel is that its numbers can be
trusted. A dashboard that is merely plausible is worse than none.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalysisKind,
    ApplicationEvent,
    ApplicationEventType,
    ApplicationOutcome,
    ApplicationStatus,
    AuditAction,
    AuditEvent,
    AutomationRunKind,
    AutomationRunStatus,
    JobStatus,
)
from app.schemas.admin import AdminPeriod
from app.services import admin_service
from tests.fixtures.factories import (
    create_analysis,
    create_application,
    create_job,
    create_run,
    create_user,
    days_ago,
)

# `asyncio_mode = "auto"` (pyproject) runs the async tests below without a mark.

# Every GET the router exposes. Read off the app so the authorization tests
# cover endpoints that do not exist yet.
ADMIN_PATHS = (
    "/api/admin/overview",
    "/api/admin/users",
    "/api/admin/jobs",
    "/api/admin/errors",
    "/api/admin/activity",
    "/api/admin/health",
    "/api/admin/audit",
)


@pytest.fixture(autouse=True)
def clean_admin_module_state() -> Any:
    """The overview cache and the once-a-day audit memo are module-level.

    Both are process-local by design (see the service), which means a test could
    otherwise read another test's numbers. Cleared on both sides so ordering
    never matters.
    """
    admin_service.clear_cache()
    admin_service._access_recorded.clear()
    yield
    admin_service.clear_cache()
    admin_service._access_recorded.clear()


def _metric(payload: dict[str, Any], group: str, key: str) -> dict[str, Any]:
    for metric in payload[group]:
        if metric["key"] == key:
            return metric
    raise AssertionError(f"No '{key}' metric in '{group}': {[m['key'] for m in payload[group]]}")


def _funnel(payload: dict[str, Any], key: str) -> dict[str, Any]:
    for stage in payload["funnel"]:
        if stage["key"] == key:
            return stage
    raise AssertionError(f"No '{key}' funnel stage.")


# --------------------------------------------------------------------------- #
# Authorization — the part that must not regress
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", ADMIN_PATHS)
async def test_anonymous_request_is_rejected(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.parametrize("path", ADMIN_PATHS)
async def test_normal_account_is_forbidden(
    client: AsyncClient, auth_headers: dict[str, str], path: str
) -> None:
    """A valid session without the role gets 403 — not 404, and not data.

    This is the test that matters: the frontend hiding the area is convenience,
    and someone typing the URL or using curl bypasses it entirely.
    """
    response = await client.get(path, headers=auth_headers)
    assert response.status_code == 403
    assert "administrator" in response.json()["detail"].lower()


@pytest.mark.parametrize("path", ADMIN_PATHS)
async def test_admin_account_is_allowed(
    client: AsyncClient, admin_auth_headers: dict[str, str], path: str
) -> None:
    response = await client.get(path, headers=admin_auth_headers)
    assert response.status_code == 200


async def test_every_admin_route_carries_the_dependency(app: Any) -> None:
    """No /api/admin route may be reachable without `get_current_admin`.

    Asserted against the app's own route table, so adding an endpoint that
    forgets the dependency fails here rather than in production.
    """
    from app.auth.dependencies import get_current_admin

    checked = 0
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/admin"):
            continue
        checked += 1
        callables = [
            dependency.call for dependency in route.dependant.dependencies  # type: ignore[attr-defined]
        ]
        assert get_current_admin in callables, f"{path} is not admin-gated"
    assert checked == len(ADMIN_PATHS)


async def test_a_disabled_admin_cannot_read_the_panel(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Deactivating an account revokes the panel too — `get_current_user` first."""
    from app.auth.security import create_access_token

    disabled = await create_user(
        session, email="ex-admin@example.com", is_admin=True, is_active=False
    )
    response = await client.get(
        "/api/admin/overview",
        headers={"Authorization": f"Bearer {create_access_token(disabled.id)}"},
    )
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"].lower()


# --------------------------------------------------------------------------- #
# Period resolution
# --------------------------------------------------------------------------- #


def test_preset_windows_and_their_comparison() -> None:
    now = datetime(2026, 3, 15, 14, 30, tzinfo=UTC)
    window = admin_service.resolve_period(AdminPeriod.LAST_7_DAYS, now=now)

    assert window.start == datetime(2026, 3, 9, 0, 0, tzinfo=UTC)
    assert window.end == now
    assert window.days == 7
    # The comparison window is the same duration immediately before, so nothing
    # is counted in both.
    assert window.previous_end == window.start
    assert window.end - window.start == window.start - window.previous_start


def test_today_compares_against_the_same_hours_yesterday() -> None:
    now = datetime(2026, 3, 15, 9, 0, tzinfo=UTC)
    window = admin_service.resolve_period(AdminPeriod.TODAY, now=now)

    assert window.start == datetime(2026, 3, 15, 0, 0, tzinfo=UTC)
    assert window.previous_start == datetime(2026, 3, 14, 15, 0, tzinfo=UTC)
    assert window.previous_end == window.start


def test_custom_period_is_inclusive_of_its_last_day() -> None:
    now = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
    window = admin_service.resolve_period(
        AdminPeriod.CUSTOM,
        start=datetime(2026, 3, 1, tzinfo=UTC).date(),
        end=datetime(2026, 3, 10, tzinfo=UTC).date(),
        now=now,
    )
    assert window.start == datetime(2026, 3, 1, tzinfo=UTC)
    assert window.end == datetime(2026, 3, 11, tzinfo=UTC)
    assert window.days == 11


async def test_custom_period_without_bounds_is_rejected(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    response = await client.get(
        "/api/admin/overview", params={"period": "custom"}, headers=admin_auth_headers
    )
    assert response.status_code == 422
    assert "start" in response.json()["detail"]


async def test_reversed_custom_period_is_rejected(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    response = await client.get(
        "/api/admin/overview",
        params={"period": "custom", "start": "2026-03-10", "end": "2026-03-01"},
        headers=admin_auth_headers,
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


async def test_overview_counts_rows_from_every_account(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
    other_user: Any,
) -> None:
    """The panel is platform-wide: two accounts' rows add up into one number."""
    for owner in (user, other_user):
        job = await create_job(session, owner, status=JobStatus.APPLIED)
        await create_application(
            session,
            owner,
            job,
            status=ApplicationStatus.SUBMITTED,
            submitted_at=datetime.now(UTC),
        )
    await create_job(session, user, status=JobStatus.SKIPPED)

    response = await client.get("/api/admin/overview", headers=admin_auth_headers)
    assert response.status_code == 200
    payload = response.json()

    assert _metric(payload, "headline", "jobs_found")["value"] == 3
    assert _metric(payload, "headline", "applications")["value"] == 2
    assert _metric(payload, "operational", "applications_submitted")["value"] == 2
    # admin + user + other_user
    assert _metric(payload, "headline", "users")["value"] == 3


async def test_period_filter_excludes_older_rows(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    await create_job(session, user, created_at=days_ago(40))
    await create_job(session, user, created_at=days_ago(1))

    recent = await client.get(
        "/api/admin/overview", params={"period": "7d"}, headers=admin_auth_headers
    )
    admin_service.clear_cache()
    wide = await client.get(
        "/api/admin/overview", params={"period": "90d"}, headers=admin_auth_headers
    )

    assert _metric(recent.json(), "headline", "jobs_found")["value"] == 1
    assert _metric(wide.json(), "headline", "jobs_found")["value"] == 2


async def test_previous_period_drives_the_trend(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    """Four jobs this week against two the week before is +100%, trending up."""
    for _ in range(4):
        await create_job(session, user, created_at=days_ago(1))
    for _ in range(2):
        await create_job(session, user, created_at=days_ago(9))

    response = await client.get(
        "/api/admin/overview", params={"period": "7d"}, headers=admin_auth_headers
    )
    metric = _metric(response.json(), "headline", "jobs_found")

    assert metric["value"] == 4
    assert metric["previous"] == 2
    assert metric["delta_pct"] == pytest.approx(1.0)
    assert metric["trend"] == "up"


def test_a_rate_is_compared_in_points_not_relatively() -> None:
    """54% -> 62% is +8 points, never the flattering "+14.8%"."""
    from app.schemas.admin import MetricUnit

    metric = admin_service.build_metric(
        "success_rate", 0.62, previous=0.54, unit=MetricUnit.PERCENT
    )
    assert metric.delta_pct == pytest.approx(0.08)
    assert metric.trend == "up"


def test_a_metric_without_a_baseline_reports_no_trend() -> None:
    metric = admin_service.build_metric("jobs_found", 12, previous=0)
    assert metric.previous == 0
    assert metric.delta_pct is None
    assert metric.trend == "none"


async def test_success_rate_says_it_has_no_data_before_any_attempt(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    """An empty install must say "sem dados", not report a 0% success rate."""
    response = await client.get("/api/admin/overview", headers=admin_auth_headers)
    metric = _metric(response.json(), "headline", "success_rate")
    assert metric["has_data"] is False


async def test_awaiting_review_is_the_current_backlog(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    """Counted as it stands, not by period: a queue is only interesting now."""
    old_job = await create_job(session, user, created_at=days_ago(60))
    await create_application(
        session,
        user,
        old_job,
        status=ApplicationStatus.AWAITING_REVIEW,
        created_at=days_ago(60),
    )

    response = await client.get(
        "/api/admin/overview", params={"period": "today"}, headers=admin_auth_headers
    )
    assert _metric(response.json(), "operational", "awaiting_review")["value"] == 1


async def test_funnel_narrows_and_reports_conversions(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    for index in range(4):
        job = await create_job(
            session,
            user,
            status=JobStatus.QUEUED if index < 2 else JobStatus.DISCOVERED,
        )
        if index < 2:
            await create_application(
                session,
                user,
                job,
                status=(
                    ApplicationStatus.SUBMITTED if index == 0 else ApplicationStatus.AWAITING_REVIEW
                ),
                approved_at=datetime.now(UTC) if index == 0 else None,
                submitted_at=datetime.now(UTC) if index == 0 else None,
            )

    payload = (await client.get("/api/admin/overview", headers=admin_auth_headers)).json()

    assert _funnel(payload, "jobs_found")["count"] == 4
    assert _funnel(payload, "jobs_selected")["count"] == 2
    assert _funnel(payload, "applications_prepared")["count"] == 2
    assert _funnel(payload, "applications_approved")["count"] == 1
    assert _funnel(payload, "applications_submitted")["count"] == 1
    assert _funnel(payload, "jobs_selected")["conversion_from_previous"] == pytest.approx(0.5)
    assert _funnel(payload, "applications_submitted")["conversion_from_start"] == pytest.approx(
        0.25
    )


async def test_growth_series_has_one_dense_point_per_day(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    """A quiet day plots as zero. A gap in the array would be a lying chart."""
    await create_job(session, user, created_at=days_ago(2))

    payload = (
        await client.get(
            "/api/admin/overview", params={"period": "7d"}, headers=admin_auth_headers
        )
    ).json()
    growth = payload["growth"]

    assert len(growth) == 7
    assert [point["date"] for point in growth] == sorted(point["date"] for point in growth)
    assert sum(point["jobs"] for point in growth) == 1


async def test_interviews_count_the_period_they_were_recorded_in(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    job = await create_job(session, user)
    await create_application(
        session,
        user,
        job,
        status=ApplicationStatus.SUBMITTED,
        outcome=ApplicationOutcome.INTERVIEW,
        outcome_updated_at=datetime.now(UTC),
    )
    stale_job = await create_job(session, user)
    await create_application(
        session,
        user,
        stale_job,
        status=ApplicationStatus.SUBMITTED,
        outcome=ApplicationOutcome.OFFER,
        outcome_updated_at=days_ago(45),
    )

    payload = (
        await client.get(
            "/api/admin/overview", params={"period": "7d"}, headers=admin_auth_headers
        )
    ).json()
    assert _metric(payload, "operational", "interviews")["value"] == 1


# --------------------------------------------------------------------------- #
# Automation, AI and health
# --------------------------------------------------------------------------- #


async def test_automation_health_reports_failures_and_never_a_next_run(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    started = datetime.now(UTC) - timedelta(minutes=10)
    await create_run(
        session,
        user,
        kind=AutomationRunKind.SEARCH,
        status=AutomationRunStatus.COMPLETED,
        started_at=started,
        finished_at=started + timedelta(seconds=120),
    )
    for _ in range(4):
        await create_run(session, user, status=AutomationRunStatus.FAILED)

    automation = (
        await client.get("/api/admin/overview", headers=admin_auth_headers)
    ).json()["automation"]

    assert automation["runs_in_period"] == 5
    assert automation["failed"] == 4
    assert automation["status"] == "problem"
    assert automation["avg_duration_seconds"] == pytest.approx(120.0)
    # No scheduler exists, so no next run may be claimed.
    assert automation["next_run_at"] is None
    assert automation["scheduling"] == "on_demand"


async def test_a_blocked_run_is_a_problem_and_an_alert(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    await create_run(
        session,
        user,
        status=AutomationRunStatus.BLOCKED,
        blocked_reason="Security verification detected.",
    )

    payload = (await client.get("/api/admin/overview", headers=admin_auth_headers)).json()

    assert payload["automation"]["status"] == "problem"
    assert "automation_blocked" in {alert["key"] for alert in payload["alerts"]}


async def test_ai_health_aggregates_calls_without_exposing_a_key(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    job = await create_job(session, user)
    await create_analysis(session, user, job, latency_ms=500, input_tokens=100, output_tokens=20)
    await create_analysis(
        session,
        user,
        job,
        kind=AnalysisKind.COVER_LETTER,
        latency_ms=1500,
        input_tokens=40,
        output_tokens=0,
        error_message="Provider timed out.",
    )

    ai = (await client.get("/api/admin/overview", headers=admin_auth_headers)).json()["ai"]
    body = (await client.get("/api/admin/overview", headers=admin_auth_headers)).text

    assert ai["calls"] == 2
    assert ai["failed"] == 1
    assert ai["succeeded"] == 1
    assert ai["avg_latency_ms"] == pytest.approx(1000.0)
    # A failed call still burned its input tokens, so both are counted.
    assert ai["tokens_input"] == 140
    # Only some providers price a call; nulls must not sum to a reassuring zero.
    assert ai["cost_usd"] is None
    assert ai["provider"] == "anthropic"
    # The configured key is an obviously-fake test value; it must still never
    # appear in a response.
    assert "test-anthropic-key-never-sent-anywhere" not in body


async def test_health_lists_every_service(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    payload = (await client.get("/api/admin/health", headers=admin_auth_headers)).json()
    services = {entry["service"]: entry for entry in payload["services"]}

    assert {"api", "database", "frontend"} <= set(services)
    assert services["database"]["status"] == "online"
    assert services["api"]["status"] == "online"


async def test_alert_fires_on_a_real_failure_rate(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    for index in range(6):
        job = await create_job(session, user)
        await create_application(
            session,
            user,
            job,
            status=(
                ApplicationStatus.FAILED if index < 3 else ApplicationStatus.SUBMITTED
            ),
            submitted_at=datetime.now(UTC) if index >= 3 else None,
        )

    payload = (await client.get("/api/admin/overview", headers=admin_auth_headers)).json()
    alerts = {alert["key"]: alert for alert in payload["alerts"]}

    assert "application_failures" in alerts
    assert alerts["application_failures"]["severity"] == "critical"


async def test_no_alerts_on_a_quiet_platform(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    """A fresh install has no problems, so it must not manufacture any.

    Only the "AI has no credential" note is allowed, and the suite configures a
    key, so this asserts an empty list.
    """
    payload = (await client.get("/api/admin/overview", headers=admin_auth_headers)).json()
    assert [alert["key"] for alert in payload["alerts"]] == []


# --------------------------------------------------------------------------- #
# Errors, activity and users
# --------------------------------------------------------------------------- #


async def test_errors_merge_the_three_sources_newest_first(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    job = await create_job(session, user)
    application = await create_application(session, user, job)
    await create_run(
        session, user, status=AutomationRunStatus.FAILED, error_message="Form changed mid-flow."
    )
    await create_analysis(session, user, job, error_message="Timeout no provider.")
    session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=ApplicationEventType.ERROR,
            message="Falha ao processar candidatura.",
            is_error=True,
        )
    )
    await session.commit()

    entries = (await client.get("/api/admin/errors", headers=admin_auth_headers)).json()
    sources = {entry["source"] for entry in entries}

    assert sources == {"automation", "ai", "application"}
    assert [entry["occurred_at"] for entry in entries] == sorted(
        (entry["occurred_at"] for entry in entries), reverse=True
    )
    assert all(entry["id"].count(":") == 1 for entry in entries)


async def test_error_summaries_are_one_truncated_line(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    await create_run(
        session,
        user,
        status=AutomationRunStatus.FAILED,
        error_message="Primeira linha.\nSegunda linha com detalhe interno.",
    )

    entries = (await client.get("/api/admin/errors", headers=admin_auth_headers)).json()
    assert entries[0]["summary"] == "Primeira linha."
    assert "Segunda linha" not in entries[0]["summary"]


async def test_activity_masks_the_email_of_a_new_account(
    client: AsyncClient, session: AsyncSession, admin_auth_headers: dict[str, str]
) -> None:
    await create_user(session, email="recruiter@example.com")

    entries = (await client.get("/api/admin/activity", headers=admin_auth_headers)).json()
    signup = next(entry for entry in entries if entry["kind"] == "user_registered")

    assert "recruiter@example.com" not in signup["summary"]
    assert "r***@example.com" in signup["summary"]


async def test_users_list_carries_counters_and_no_personal_content(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    job = await create_job(session, user)
    await create_application(
        session, user, job, status=ApplicationStatus.SUBMITTED, submitted_at=datetime.now(UTC)
    )

    response = await client.get("/api/admin/users", headers=admin_auth_headers)
    payload = response.json()
    row = next(item for item in payload["items"] if item["id"] == user.id)

    assert row["jobs"] == 1
    assert row["applications"] == 1
    assert row["submitted"] == 1
    # The profile factory seeds a resume; none of it may appear here.
    assert "resume_text" not in row
    assert "Python, FastAPI, PostgreSQL" not in response.text
    assert "hashed_password" not in response.text


async def test_users_search_matches_email_and_name(
    client: AsyncClient, session: AsyncSession, admin_auth_headers: dict[str, str]
) -> None:
    await create_user(session, email="carla@example.com", full_name="Carla Nunes")
    await create_user(session, email="bruno@example.com", full_name="Bruno Lima")

    by_email = await client.get(
        "/api/admin/users", params={"search": "carla@"}, headers=admin_auth_headers
    )
    by_name = await client.get(
        "/api/admin/users", params={"search": "bruno l"}, headers=admin_auth_headers
    )

    assert [item["email"] for item in by_email.json()["items"]] == ["carla@example.com"]
    assert [item["email"] for item in by_name.json()["items"]] == ["bruno@example.com"]


async def test_users_search_treats_a_wildcard_as_a_character(
    client: AsyncClient, session: AsyncSession, admin_auth_headers: dict[str, str]
) -> None:
    """`%` typed into the box is part of the name, not a match-everything.

    Never an injection (the term is bound as a parameter regardless) — but an
    unescaped wildcard turns a search that found nothing into one that finds
    every account, which reads as a broken filter.
    """
    await create_user(session, email="percent@example.com", full_name="Ana 100% Silva")
    await create_user(session, email="other@example.com", full_name="Bruno Lima")

    literal = await client.get(
        "/api/admin/users", params={"search": "100%"}, headers=admin_auth_headers
    )
    # A bare "%" is a character to look for, so it finds the one name that
    # contains it — not every account, which is what an unescaped wildcard did.
    wildcard_only = await client.get(
        "/api/admin/users", params={"search": "%"}, headers=admin_auth_headers
    )
    underscore = await client.get(
        "/api/admin/users", params={"search": "a_a"}, headers=admin_auth_headers
    )

    assert [item["email"] for item in literal.json()["items"]] == ["percent@example.com"]
    assert [item["email"] for item in wildcard_only.json()["items"]] == ["percent@example.com"]
    # "_" would otherwise match any character, and "Ana" would come back.
    assert underscore.json()["items"] == []


async def test_users_filters_split_by_activity(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
    other_user: Any,
) -> None:
    job = await create_job(session, user)
    await create_application(session, user, job)
    await create_user(session, email="disabled@example.com", is_active=False)

    async def emails(**params: Any) -> set[str]:
        response = await client.get(
            "/api/admin/users", params=params, headers=admin_auth_headers
        )
        return {item["email"] for item in response.json()["items"]}

    assert await emails(filter="with_applications") == {user.email}
    assert other_user.email in await emails(filter="without_applications")
    assert await emails(filter="inactive") == {"disabled@example.com"}
    assert "disabled@example.com" not in await emails(filter="active")


async def test_users_pagination_reports_the_total(
    client: AsyncClient, session: AsyncSession, admin_auth_headers: dict[str, str]
) -> None:
    for index in range(5):
        await create_user(session, email=f"paged{index}@example.com")

    response = await client.get(
        "/api/admin/users", params={"limit": 2, "offset": 0}, headers=admin_auth_headers
    )
    payload = response.json()

    assert len(payload["items"]) == 2
    assert payload["total"] == 6  # five plus the admin
    assert payload["limit"] == 2


async def test_usage_lists_the_busiest_accounts_without_ranking_them(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
    other_user: Any,
) -> None:
    for _ in range(3):
        job = await create_job(session, user)
        await create_application(session, user, job)
    job = await create_job(session, other_user)
    await create_application(session, other_user, job)

    usage = (await client.get("/api/admin/overview", headers=admin_auth_headers)).json()["usage"]

    assert [row["email"] for row in usage] == [user.email, other_user.email]
    assert usage[0]["applications"] == 3
    assert usage[0]["jobs"] == 3
    # Usage, not a leaderboard: no position is returned for the UI to print.
    assert "rank" not in usage[0]
    assert "position" not in usage[0]


async def test_job_insights_aggregate_and_cap_the_technology_sample(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    await create_job(
        session,
        user,
        title="Python Engineer",
        description="Python, FastAPI e PostgreSQL.",
        status=JobStatus.QUEUED,
        score=88,
    )
    await create_job(
        session,
        user,
        title="Python Engineer",
        description="Python e Docker.",
        status=JobStatus.SKIPPED,
        score=42,
    )

    payload = (await client.get("/api/admin/jobs", headers=admin_auth_headers)).json()
    technologies = {entry["label"]: entry["count"] for entry in payload["top_technologies"]}

    assert payload["total"] == 2
    assert payload["discarded"] == 1
    assert payload["average_score"] == pytest.approx(65.0)
    assert payload["top_titles"][0] == {"label": "Python Engineer", "count": 2}
    # Counted once per posting, not once per mention.
    assert technologies["python"] == 2
    assert payload["technologies_sampled"] == 2


# --------------------------------------------------------------------------- #
# Auditing and caching
# --------------------------------------------------------------------------- #


async def test_panel_access_is_audited_once_per_day(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    admin_user: Any,
) -> None:
    """Two loads, one row. A page that refreshes every 30s must not flood the trail."""
    await client.get("/api/admin/overview", headers=admin_auth_headers)
    await client.get(
        "/api/admin/overview", params={"refresh": "true"}, headers=admin_auth_headers
    )

    events = (
        (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.user_id == admin_user.id,
                    AuditEvent.action == AuditAction.ADMIN_ACCESS,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].subject_type == "admin_panel"
    # A read is not a relaxed guardrail, so it must not be flagged as one.
    assert events[0].relaxed == []


async def test_audit_endpoint_returns_the_recorded_accesses(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    await client.get("/api/admin/overview", headers=admin_auth_headers)

    entries = (await client.get("/api/admin/audit", headers=admin_auth_headers)).json()
    assert entries
    assert entries[0]["action"] == "admin_access"


async def test_refresh_recomputes_instead_of_serving_the_cache(
    client: AsyncClient,
    session: AsyncSession,
    admin_auth_headers: dict[str, str],
    user: Any,
) -> None:
    first = await client.get("/api/admin/overview", headers=admin_auth_headers)
    assert _metric(first.json(), "headline", "jobs_found")["value"] == 0

    await create_job(session, user)

    cached = await client.get("/api/admin/overview", headers=admin_auth_headers)
    assert _metric(cached.json(), "headline", "jobs_found")["value"] == 0

    fresh = await client.get(
        "/api/admin/overview", params={"refresh": "true"}, headers=admin_auth_headers
    )
    assert _metric(fresh.json(), "headline", "jobs_found")["value"] == 1
