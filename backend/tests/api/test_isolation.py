"""User isolation.

Reading or acting on another user's row must answer 404, never 403: a 403 confirms
that the id exists, which is itself a leak. Collections must never contain another
user's rows.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApplicationStatus, AutomationRunKind, JobStatus
from tests.fixtures.factories import (
    create_application,
    create_job,
    create_run,
    create_search,
    create_user,
)


@pytest.fixture
async def stranger_data(session: AsyncSession, other_user: Any) -> dict[str, Any]:
    """Rows that belong to `other_user` and must be invisible to `user`."""
    search = await create_search(session, other_user, name="Their search")
    job = await create_job(
        session, other_user, search_id=search.id, status=JobStatus.ANALYZED, score=91
    )
    application = await create_application(
        session, other_user, job, status=ApplicationStatus.AWAITING_REVIEW
    )
    run = await create_run(session, other_user, kind=AutomationRunKind.SEARCH)
    return {"search": search, "job": job, "application": application, "run": run}


class TestJobsAreInvisible:
    async def test_reading_another_users_job_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        response = await client.get(
            f"/api/jobs/{stranger_data['job'].id}", headers=auth_headers
        )

        assert response.status_code == 404, response.text

    async def test_skipping_another_users_job_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        response = await client.post(
            f"/api/jobs/{stranger_data['job'].id}/skip", headers=auth_headers
        )

        assert response.status_code == 404, response.text

    async def test_analyzing_another_users_job_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        response = await client.post(
            f"/api/jobs/{stranger_data['job'].id}/analyze", headers=auth_headers
        )

        assert response.status_code == 404, response.text

    async def test_the_job_list_holds_only_your_own(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        stranger_data: dict[str, Any],
    ) -> None:
        mine = await create_job(session, user, title="Mine")

        body = (await client.get("/api/jobs", headers=auth_headers)).json()

        assert [item["id"] for item in body["items"]] == [mine.id]
        assert body["total"] == 1


class TestApplicationsAreInvisible:
    async def test_reading_another_users_application_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        response = await client.get(
            f"/api/applications/{stranger_data['application'].id}", headers=auth_headers
        )

        assert response.status_code == 404, response.text

    async def test_editing_another_users_application_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/applications/{stranger_data['application'].id}",
            headers=auth_headers,
            json={"cover_letter": "Injected by someone else."},
        )

        assert response.status_code == 404, response.text

    async def test_submitting_another_users_application_is_a_404(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        stranger_data: dict[str, Any],
        fake_linkedin: Any,
    ) -> None:
        """The worst case: submitting an application on someone else's behalf."""
        response = await client.post(
            f"/api/applications/{stranger_data['application'].id}/submit",
            headers=auth_headers,
            json={"confirm": True},
        )

        assert response.status_code == 404, response.text
        assert fake_linkedin.submit_called is False

    async def test_discarding_another_users_application_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        response = await client.post(
            f"/api/applications/{stranger_data['application'].id}/discard", headers=auth_headers
        )

        assert response.status_code == 404, response.text

    async def test_reading_another_users_event_trail_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        response = await client.get(
            f"/api/applications/{stranger_data['application'].id}/events", headers=auth_headers
        )

        assert response.status_code == 404, response.text

    async def test_the_application_list_holds_only_your_own(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        body = (await client.get("/api/applications", headers=auth_headers)).json()

        assert body["items"] == []
        assert body["total"] == 0


class TestSearchesAreInvisible:
    async def test_updating_another_users_search_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/searches/{stranger_data['search'].id}",
            headers=auth_headers,
            json={"name": "Renamed by a stranger"},
        )

        assert response.status_code == 404, response.text

    async def test_deleting_another_users_search_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        response = await client.delete(
            f"/api/searches/{stranger_data['search'].id}", headers=auth_headers
        )

        assert response.status_code == 404, response.text

    async def test_the_search_list_holds_only_your_own(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        body = (await client.get("/api/searches", headers=auth_headers)).json()

        assert body == []


class TestRunsAreInvisible:
    async def test_reading_another_users_run_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        response = await client.get(
            f"/api/automation/runs/{stranger_data['run'].id}", headers=auth_headers
        )

        assert response.status_code == 404, response.text

    async def test_the_run_list_holds_only_your_own(
        self, client: AsyncClient, auth_headers: dict[str, str], stranger_data: dict[str, Any]
    ) -> None:
        body = (await client.get("/api/automation/runs", headers=auth_headers)).json()

        assert body == []


class TestPreparingAnotherUsersJob:
    async def test_is_a_404_and_prepares_nothing(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        stranger_data: dict[str, Any],
        fake_linkedin: Any,
    ) -> None:
        response = await client.post(
            "/api/automation/prepare",
            headers=auth_headers,
            json={"job_ids": [stranger_data["job"].id], "confirmed": True},
        )

        assert response.status_code == 404, response.text
        assert fake_linkedin.call_count("open_easy_apply") == 0
        assert fake_linkedin.submit_called is False


class TestProfileAndSettingsAreScoped:
    async def test_each_user_reads_their_own_profile(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        other_auth_headers: dict[str, str],
    ) -> None:
        await client.put(
            "/api/profile", headers=auth_headers, json={"headline": "Mine only"}
        )

        theirs = (await client.get("/api/profile", headers=other_auth_headers)).json()

        assert theirs["headline"] != "Mine only"

    async def test_each_user_reads_their_own_settings(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        other_auth_headers: dict[str, str],
    ) -> None:
        await client.put("/api/settings", headers=auth_headers, json={"daily_cap": 3})

        theirs = (await client.get("/api/settings", headers=other_auth_headers)).json()

        assert theirs["daily_cap"] != 3
