"""An application made on the company's own site, from preparation to statistics.

Portal discovery (Gupy today) finds jobs that have no Easy Apply form. Before
this channel existed they were scored, tailored and then dropped: no
`Application` could be created for them, so they never reached the pipeline
board and never appeared in a single number `stats_service` produces. That
silently biased every measurement towards Easy Apply.

The arc these tests pin down is the whole point of the feature:

    prepare (content only, no browser)
        -> AWAITING_REVIEW on the EXTERNAL channel
        -> the user applies on the company's page
        -> POST /mark-applied records it
        -> SUBMITTED / APPLIED, on the board, counted in the stats.

The two refusals on the way are just as load-bearing: what this endpoint records
is a human act, so it must never be reachable for an Easy Apply draft (which has
a real submission path and would be closed out unsent), and the engine must never
be able to send an external one (there is no form there to send).
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.errors import AutomationError
from app.database.base import utcnow
from app.models import (
    ApplicationChannel,
    ApplicationEventType,
    ApplicationStatus,
    AutomationRunKind,
    AutomationRunStatus,
    JobStatus,
)
from tests.automation import application_for_job
from tests.fixtures.factories import create_application, create_job, create_run
from tests.fixtures.fake_linkedin import FakeLinkedInService


async def gupy_job(session: AsyncSession, user: Any, **overrides: Any) -> Any:
    """A job as `app.portals.gupy` stores it: no Easy Apply, not from LinkedIn."""
    values: dict[str, Any] = {
        "source": "gupy",
        "easy_apply": False,
        "url": "https://empresa.gupy.io/job/eng-backend",
        "status": JobStatus.ANALYZED,
        "score": 88,
    }
    values.update(overrides)
    return await create_job(session, user, **values)


async def external_application(session: AsyncSession, user: Any, **overrides: Any) -> Any:
    """A prepared, unsent application to a portal job."""
    job = await gupy_job(session, user)
    values: dict[str, Any] = {
        "channel": ApplicationChannel.EXTERNAL,
        "status": ApplicationStatus.AWAITING_REVIEW,
        "screening_answers": [],
        "total_steps": None,
        "current_step": None,
    }
    values.update(overrides)
    return await create_application(session, user, job, **values)


class TestPreparingAPortalJob:
    async def test_produces_content_without_ever_opening_a_browser(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        """There is no form on this side; the letter is all preparation can mean."""
        from tests.fixtures.factories import create_user

        user = await create_user(session, email="gupy1@example.com", settings={"dry_run": False})
        job = await gupy_job(session, user)
        run = await create_run(
            session, user, kind=AutomationRunKind.PREPARE, status=AutomationRunStatus.PENDING
        )

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.status == ApplicationStatus.AWAITING_REVIEW
        assert application.channel == ApplicationChannel.EXTERNAL
        assert application.cover_letter
        # Dry run is off, so nothing but the channel is keeping the browser shut.
        assert fake_linkedin.browser_calls == []
        assert fake_linkedin.submit_called is False
        # No form was read, so there is nothing to fingerprint and nothing to ask.
        assert application.form_fingerprint is None
        assert application.needs_human_input is False

    async def test_an_easy_apply_job_still_takes_the_linkedin_path(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        """The external branch must not swallow the channel it does not own."""
        from tests.fixtures.factories import create_user

        user = await create_user(session, email="gupy2@example.com", settings={"dry_run": False})
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        run = await create_run(
            session, user, kind=AutomationRunKind.PREPARE, status=AutomationRunStatus.PENDING
        )

        await automation_engine.prepare_applications(user.id, run.id, [job.id])

        application = await application_for_job(session, job.id)
        assert application is not None
        assert application.channel == ApplicationChannel.EASY_APPLY
        assert fake_linkedin.call_count("open_easy_apply") == 1
        assert fake_linkedin.submit_called is False


class TestMarkApplied:
    async def test_records_the_application_and_puts_it_on_the_board(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await external_application(session, user)

        response = await client.post(
            f"/api/applications/{application.id}/mark-applied",
            json={"confirm": True, "note": "Enviei pelo site da empresa."},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "submitted"
        assert body["outcome"] == "applied"
        assert body["submitted_at"] is not None
        assert body["was_dry_run"] is False
        assert body["outcome_note"] == "Enviei pelo site da empresa."
        # The job follows, exactly as a real submission moves it.
        assert body["job"]["status"] == "applied"

        board = await client.get("/api/applications/board", headers=auth_headers)
        assert [card["id"] for card in board.json()] == [application.id]

    async def test_freezes_the_snapshot_and_records_the_channel(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await external_application(
            session, user, cover_letter="Prezada equipe, tenho interesse na vaga."
        )

        response = await client.post(
            f"/api/applications/{application.id}/mark-applied",
            json={"confirm": True},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text

        # Two refreshes: naming attributes refreshes only those, so the columns
        # the endpoint wrote would otherwise still be the stale ones.
        await session.refresh(application)
        await session.refresh(application, ["events"])
        assert application.submitted_snapshot is not None
        assert application.submitted_snapshot["cover_letter"] == (
            "Prezada equipe, tenho interesse na vaga."
        )
        recorded = [
            event
            for event in application.events
            if event.event_type == ApplicationEventType.SUBMITTED
        ]
        assert len(recorded) == 1
        assert recorded[0].payload == {"channel": "external"}

    async def test_is_refused_without_an_explicit_confirmation(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await external_application(session, user)

        response = await client.post(
            f"/api/applications/{application.id}/mark-applied",
            json={"confirm": False},
            headers=auth_headers,
        )

        assert response.status_code == 412, response.text
        await session.refresh(application)
        assert application.status == ApplicationStatus.AWAITING_REVIEW
        assert application.outcome is None

    async def test_is_refused_for_an_easy_apply_application(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        """An unsent Easy Apply draft may not be closed out as if it had gone."""
        job = await create_job(session, user, status=JobStatus.QUEUED, score=90)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        response = await client.post(
            f"/api/applications/{application.id}/mark-applied",
            json={"confirm": True},
            headers=auth_headers,
        )

        assert response.status_code == 412, response.text
        await session.refresh(application)
        assert application.status == ApplicationStatus.AWAITING_REVIEW
        assert application.submitted_at is None

    async def test_is_refused_once_the_application_is_already_recorded(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await external_application(
            session, user, status=ApplicationStatus.SUBMITTED, submitted_at=utcnow()
        )

        response = await client.post(
            f"/api/applications/{application.id}/mark-applied",
            json={"confirm": True},
            headers=auth_headers,
        )

        assert response.status_code == 412, response.text


class TestTheTwoChannelsStayApart:
    async def test_the_engine_refuses_to_submit_an_external_application(
        self, session: AsyncSession, automation_engine: Any, fake_linkedin: FakeLinkedInService
    ) -> None:
        """There is no Easy Apply form behind it, so no state makes this path valid."""
        from tests.fixtures.factories import create_user

        user = await create_user(session, email="gupy3@example.com", settings={"dry_run": False})
        application = await external_application(session, user, approved_at=utcnow())

        with pytest.raises(AutomationError, match="company's own site"):
            await automation_engine.submit_application(user.id, application.id)

        assert fake_linkedin.submit_called is False
        assert fake_linkedin.call_count("open_easy_apply") == 0

    async def test_the_submit_endpoint_refuses_an_external_application(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        """Refused before anything is approved or scheduled, not after it fails."""
        application = await external_application(session, user)

        response = await client.post(
            f"/api/applications/{application.id}/submit",
            json={"confirm": True},
            headers=auth_headers,
        )

        assert response.status_code == 412, response.text
        await session.refresh(application)
        assert application.approved_at is None
        assert application.status == ApplicationStatus.AWAITING_REVIEW


class TestItCountsInTheStatistics:
    """The reason the whole channel exists.

    An application the user made with materials this app prepared has to be
    measurable, or the outcome analytics describe only the subset the automation
    happened to be able to send.
    """

    async def test_a_gupy_application_appears_in_the_outcome_stats(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await external_application(session, user)

        before = await client.get("/api/stats/outcomes", headers=auth_headers)
        assert before.json()["total_submitted"] == 0

        recorded = await client.post(
            f"/api/applications/{application.id}/mark-applied",
            json={"confirm": True},
            headers=auth_headers,
        )
        assert recorded.status_code == 200, recorded.text

        after = await client.get("/api/stats/outcomes", headers=auth_headers)
        body = after.json()
        assert body["total_submitted"] == 1
        applied = next(row for row in body["by_outcome"] if row["outcome"] == "applied")
        assert applied["count"] == 1
        # The job's score rides along, so score-vs-outcome finally sees this job.
        assert applied["avg_score"] == 88
        band = next(row for row in body["interview_rate_by_band"] if row["label"] == "80-89")
        assert band["total"] == 1

    async def test_it_counts_in_the_dashboard_and_segment_stats_too(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await external_application(session, user)
        await client.post(
            f"/api/applications/{application.id}/mark-applied",
            json={"confirm": True},
            headers=auth_headers,
        )

        dashboard = (await client.get("/api/stats", headers=auth_headers)).json()
        assert dashboard["applications_today"] == 1

        segments = (await client.get("/api/stats/segments", headers=auth_headers)).json()
        assert [row["label"] for row in segments["by_company"]] == ["Acme Corp"]
