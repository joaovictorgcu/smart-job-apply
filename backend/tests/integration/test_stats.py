"""Dashboard aggregation over a seeded dataset."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.models import AnalysisKind, ApplicationStatus, JobStatus
from tests.fixtures.factories import (
    create_analysis,
    create_application,
    create_job,
    create_user,
    days_ago,
)

DAILY_CAP = 15


async def seed(session: AsyncSession, user: Any) -> dict[str, Any]:
    """Five jobs, three applications, two AI calls — all with known numbers."""
    high = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
    mid = await create_job(session, user, status=JobStatus.ANALYZED, score=80)
    low = await create_job(
        session,
        user,
        status=JobStatus.SKIPPED,
        score=40,
        skip_reason="Score 40 is below the minimum of 70.",
    )
    applied = await create_job(session, user, status=JobStatus.APPLIED, score=95)
    await create_job(session, user, status=JobStatus.DISCOVERED, score=None)

    awaiting = await create_application(
        session, user, high, status=ApplicationStatus.AWAITING_REVIEW
    )
    submitted_today = await create_application(
        session, user, applied, status=ApplicationStatus.SUBMITTED, submitted_at=utcnow()
    )
    submitted_earlier = await create_application(
        session, user, mid, status=ApplicationStatus.SUBMITTED, submitted_at=days_ago(3)
    )

    await create_analysis(session, user, high, input_tokens=1000, output_tokens=100)
    await create_analysis(
        session,
        user,
        low,
        kind=AnalysisKind.COVER_LETTER,
        input_tokens=500,
        output_tokens=250,
    )
    return {
        "awaiting": awaiting,
        "submitted_today": submitted_today,
        "submitted_earlier": submitted_earlier,
        "unscored_job": low,
    }


class TestDashboardStats:
    async def test_counts_jobs_and_applications(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await seed(session, user)

        response = await client.get("/api/stats", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["jobs_total"] == 5
        assert body["applications_total"] == 3
        assert body["awaiting_review"] == 1

    async def test_groups_jobs_by_status(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await seed(session, user)

        body = (await client.get("/api/stats", headers=auth_headers)).json()

        by_status = body["jobs_by_status"]
        assert by_status.get(JobStatus.ANALYZED.value) == 2
        assert by_status.get(JobStatus.SKIPPED.value) == 1
        assert by_status.get(JobStatus.APPLIED.value) == 1
        assert by_status.get(JobStatus.DISCOVERED.value) == 1

    async def test_averages_only_the_scored_jobs(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await seed(session, user)

        body = (await client.get("/api/stats", headers=auth_headers)).json()

        # (90 + 80 + 40 + 95) / 4 — the unscored job must not drag it toward zero.
        assert body["average_score"] == 76.25

    async def test_reports_the_daily_cap_and_what_is_left_of_it(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
    ) -> None:
        from tests.fixtures.factories import create_user as _create_user

        capped = await _create_user(
            session, email="capped@example.com", settings={"daily_cap": DAILY_CAP}
        )
        from app.auth.security import create_access_token

        headers = {"Authorization": f"Bearer {create_access_token(capped.id)}"}
        await seed(session, capped)

        body = (await client.get("/api/stats", headers=headers)).json()

        assert body["daily_cap"] == DAILY_CAP
        assert body["remaining_today"] == max(0, DAILY_CAP - body["applications_today"])
        assert body["applications_today"] >= 1

    async def test_sums_ai_token_usage(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await seed(session, user)

        body = (await client.get("/api/stats", headers=auth_headers)).json()

        assert body["ai_calls_total"] == 2
        assert body["ai_tokens_input"] == 1500
        assert body["ai_tokens_output"] == 350

    async def test_reports_a_seven_day_series(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await seed(session, user)

        body = (await client.get("/api/stats", headers=auth_headers)).json()

        series = body["applications_last_7_days"]
        assert isinstance(series, list)
        assert sum(point["count"] for point in series) >= 1

    async def test_an_empty_account_reports_zeroes_not_an_error(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get("/api/stats", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["jobs_total"] == 0
        assert body["applications_total"] == 0
        assert body["average_score"] is None

    async def test_never_counts_another_users_data(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        other_user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        await seed(session, other_user)

        body = (await client.get("/api/stats", headers=auth_headers)).json()

        assert body["jobs_total"] == 0
        assert body["applications_total"] == 0
        assert body["ai_calls_total"] == 0

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get("/api/stats")).status_code == 401
