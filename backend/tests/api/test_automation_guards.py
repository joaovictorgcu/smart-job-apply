"""Guards on the automation endpoints.

Preview is read-only, prepare needs an explicit confirmation, stop is the kill
switch, and no endpoint on this router may ever cause a submission.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_access_token
from app.database.base import utcnow
from app.models import (
    Application,
    ApplicationStatus,
    AutomationRun,
    AutomationRunKind,
    AutomationRunStatus,
    JobStatus,
)
from tests.fixtures.factories import (
    create_application,
    create_job,
    create_run,
    create_search,
    create_user,
)
from tests.fixtures.fake_linkedin import FakeLinkedInService


async def spent_cap_user(session: AsyncSession, email: str) -> Any:
    """A user whose daily cap of one has already been used today."""
    user = await create_user(
        session, email=email, settings={"daily_cap": 1, "dry_run": False}
    )
    spent = await create_job(session, user, status=JobStatus.APPLIED)
    await create_application(
        session,
        user,
        spent,
        status=ApplicationStatus.SUBMITTED,
        submitted_at=utcnow(),
    )
    return user


async def count_applications(session: AsyncSession, user: Any) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(Application).where(Application.user_id == user.id)
        )
    ).scalar_one()


class TestPreviewIsReadOnly:
    async def test_reports_the_volume_without_preparing_anything(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        jobs = [
            await create_job(session, user, status=JobStatus.ANALYZED, score=90) for _ in range(3)
        ]

        response = await client.post(
            "/api/automation/preview",
            headers=auth_headers,
            json={"job_ids": [job.id for job in jobs], "confirmed": False},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["jobs_to_process"] == 3
        assert body["requires_confirmation"] is True
        assert await count_applications(session, user) == 0
        assert fake_linkedin.browser_calls == []

    async def test_reports_the_cap_and_what_is_left(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
    ) -> None:
        capped = await create_user(
            session, email="cap-preview@example.com", settings={"daily_cap": 5}
        )
        headers = {"Authorization": f"Bearer {create_access_token(capped.id)}"}
        job = await create_job(session, capped, status=JobStatus.ANALYZED, score=90)

        body = (
            await client.post(
                "/api/automation/preview",
                headers=headers,
                json={"job_ids": [job.id], "confirmed": False},
            )
        ).json()

        assert body["daily_cap"] == 5
        assert body["remaining_today"] <= 5

    async def test_counts_jobs_already_applied_to_separately(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        fresh = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        done = await create_job(session, user, status=JobStatus.APPLIED, score=90)
        await create_application(session, user, done, status=ApplicationStatus.SUBMITTED)

        body = (
            await client.post(
                "/api/automation/preview",
                headers=auth_headers,
                json={"job_ids": [fresh.id, done.id], "confirmed": False},
            )
        ).json()

        assert body["already_applied"] == 1
        assert body["jobs_to_process"] == 1

    async def test_counts_jobs_under_the_threshold_separately(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
    ) -> None:
        picky = await create_user(
            session, email="picky-preview@example.com", settings={"min_score": 80}
        )
        headers = {"Authorization": f"Bearer {create_access_token(picky.id)}"}
        strong = await create_job(session, picky, status=JobStatus.ANALYZED, score=95)
        weak = await create_job(session, picky, status=JobStatus.ANALYZED, score=40)

        body = (
            await client.post(
                "/api/automation/preview",
                headers=headers,
                json={"job_ids": [strong.id, weak.id], "confirmed": False},
            )
        ).json()

        assert body["below_threshold"] == 1
        assert body["jobs_to_process"] == 1


class TestPrepareNeedsConfirmation:
    async def test_an_unconfirmed_prepare_is_refused(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)

        response = await client.post(
            "/api/automation/prepare",
            headers=auth_headers,
            json={"job_ids": [job.id], "confirmed": False},
        )

        assert 400 <= response.status_code < 500, response.text
        assert await count_applications(session, user) == 0
        assert fake_linkedin.browser_calls == []

    async def test_an_empty_job_list_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/api/automation/prepare",
            headers=auth_headers,
            json={"job_ids": [], "confirmed": True},
        )

        assert response.status_code == 422, response.text

    async def test_a_batch_beyond_the_schema_limit_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/api/automation/prepare",
            headers=auth_headers,
            json={"job_ids": list(range(1, 100)), "confirmed": True},
        )

        assert response.status_code == 422, response.text

    async def test_a_confirmed_prepare_never_submits(
        self,
        client: AsyncClient,
        session: AsyncSession,
        auth_headers: dict[str, str],
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        """Preparation is allowed to drive the form. It is never allowed to send it."""
        user = await create_user(session, email="prepare@example.com", settings={"dry_run": False})
        headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)

        response = await client.post(
            "/api/automation/prepare",
            headers=headers,
            json={"job_ids": [job.id], "confirmed": True},
        )

        assert response.status_code in (200, 201, 202), response.text
        assert fake_linkedin.submit_called is False

    async def test_preparing_beyond_the_daily_cap_is_allowed_but_warned(
        self,
        client: AsyncClient,
        session: AsyncSession,
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        """Drafts may pile up past the cap; it is *submitting* that the cap stops.

        The preview has to say so, so the user is never surprised by drafts they
        cannot send today.
        """
        capped = await spent_cap_user(session, "over-cap@example.com")
        headers = {"Authorization": f"Bearer {create_access_token(capped.id)}"}
        job = await create_job(session, capped, status=JobStatus.ANALYZED, score=95)

        preview = await client.post(
            "/api/automation/preview",
            headers=headers,
            json={"job_ids": [job.id], "confirmed": False},
        )
        prepare = await client.post(
            "/api/automation/prepare",
            headers=headers,
            json={"job_ids": [job.id], "confirmed": True},
        )

        assert preview.json()["remaining_today"] == 0
        assert any("cap" in warning.lower() for warning in preview.json()["warnings"])
        assert prepare.status_code in (200, 201, 202), prepare.text
        assert fake_linkedin.submit_called is False

    async def test_submitting_beyond_the_daily_cap_is_refused(
        self,
        client: AsyncClient,
        session: AsyncSession,
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        capped = await spent_cap_user(session, "over-cap-submit@example.com")
        headers = {"Authorization": f"Bearer {create_access_token(capped.id)}"}
        job = await create_job(session, capped, status=JobStatus.QUEUED, score=95)
        application = await create_application(
            session, capped, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        response = await client.post(
            f"/api/applications/{application.id}/submit",
            headers=headers,
            json={"confirm": True},
        )

        assert response.status_code == 429, response.text
        assert fake_linkedin.submit_called is False


class TestSearchRun:
    async def test_starts_a_run_and_reports_it(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        search = await create_search(session, user)

        response = await client.post(
            "/api/automation/search",
            headers=auth_headers,
            json={"search_id": search.id, "max_results": 5},
        )

        assert response.status_code in (200, 201, 202), response.text
        body = response.json()
        assert body["kind"] == "search"
        assert body["id"]

    async def test_a_search_never_submits(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        await client.post(
            "/api/automation/search",
            headers=auth_headers,
            json={"keywords": "python backend", "max_results": 5},
        )

        assert fake_linkedin.submit_called is False

    async def test_an_unknown_search_id_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/api/automation/search", headers=auth_headers, json={"search_id": 999999}
        )

        assert response.status_code == 404, response.text

    async def test_the_result_cap_is_enforced_by_the_schema(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/api/automation/search",
            headers=auth_headers,
            json={"keywords": "python", "max_results": 10_000},
        )

        assert response.status_code == 422, response.text


class TestKillSwitchEndpoint:
    async def test_stopping_flips_stop_requested_on_a_running_run(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        run = await create_run(session, user, status=AutomationRunStatus.RUNNING)

        response = await client.post("/api/automation/stop", headers=auth_headers)

        assert response.status_code == 200, response.text
        assert response.json()["detail"]
        await session.refresh(run)
        assert run.stop_requested is True

    async def test_stopping_with_nothing_running_still_answers_cleanly(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post("/api/automation/stop", headers=auth_headers)

        assert response.status_code == 200, response.text

    async def test_stopping_does_not_touch_another_users_run(
        self,
        client: AsyncClient,
        session: AsyncSession,
        other_user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        theirs = await create_run(session, other_user, status=AutomationRunStatus.RUNNING)

        await client.post("/api/automation/stop", headers=auth_headers)

        await session.refresh(theirs)
        assert theirs.stop_requested is False

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.post("/api/automation/stop")).status_code == 401


class TestSessionEndpoints:
    async def test_reports_the_session_status(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get("/api/automation/session", headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) >= {"browser_open", "logged_in", "blocked", "dry_run", "daily_cap"}

    async def test_defaults_to_dry_run(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """`dry_run` is on until the user turns it off, and the panel must say so."""
        body = (await client.get("/api/automation/session", headers=auth_headers)).json()

        assert body["dry_run"] is True

    async def test_starting_a_session_opens_the_browser_but_applies_to_nothing(
        self, client: AsyncClient, auth_headers: dict[str, str], fake_linkedin: FakeLinkedInService
    ) -> None:
        response = await client.post("/api/automation/session/start", headers=auth_headers)

        assert response.status_code in (200, 202), response.text
        assert fake_linkedin.submit_called is False
        assert fake_linkedin.call_count("open_easy_apply") == 0

    async def test_stopping_a_session_is_accepted(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post("/api/automation/session/stop", headers=auth_headers)

        assert response.status_code in (200, 202), response.text


class TestRunHistory:
    async def test_lists_the_most_recent_runs(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        for _ in range(3):
            await create_run(session, user, status=AutomationRunStatus.COMPLETED)

        response = await client.get(
            "/api/automation/runs", headers=auth_headers, params={"limit": 2}
        )

        assert response.status_code == 200
        assert len(response.json()) == 2

    async def test_reads_a_single_run(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        run = await create_run(session, user, status=AutomationRunStatus.BLOCKED)
        run.blocked_reason = "Security verification detected."
        await session.commit()

        response = await client.get(f"/api/automation/runs/{run.id}", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == AutomationRunStatus.BLOCKED.value
        assert body["blocked_reason"] == "Security verification detected."


class TestAIStatus:
    async def test_reports_whether_the_key_is_configured(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get("/api/ai/status", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is True
        assert body["model"]

    async def test_never_returns_the_key(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get("/api/ai/status", headers=auth_headers)

        assert "test-anthropic-key-never-sent-anywhere" not in response.text


class TestCoverLetterEndpoint:
    async def test_generates_a_letter_without_touching_the_browser(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)

        response = await client.post(f"/api/ai/cover-letter/{job.id}", headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["content"]
        assert body["language"]
        assert fake_linkedin.browser_calls == []

    async def test_an_unknown_job_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post("/api/ai/cover-letter/999999", headers=auth_headers)

        assert response.status_code == 404


class TestRunsAreRecorded:
    async def test_a_search_run_is_persisted(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await client.post(
            "/api/automation/search",
            headers=auth_headers,
            json={"keywords": "python backend", "max_results": 3},
        )

        runs = (
            (await session.execute(select(AutomationRun).where(AutomationRun.user_id == user.id)))
            .scalars()
            .all()
        )
        assert runs
        assert runs[0].kind == AutomationRunKind.SEARCH
