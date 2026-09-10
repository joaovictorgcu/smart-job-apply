"""What kind of vacancy the account is looking for, end to end.

Three promises are asserted here, and the third is the one with a price tag on
it: stating a preference has to spare the model call, not merely hide the
posting afterwards.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobStatus, Search
from app.services.preference_service import MANAGED_SEARCH_NAME
from tests.fixtures.factories import create_job
from tests.fixtures.fake_ai import FakeAIClient

PREFERENCES = "/api/preferences"
SEARCHES = "/api/searches"


class TestReadingAndWriting:
    async def test_a_fresh_account_states_nothing(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        body = (await client.get(PREFERENCES, headers=auth_headers)).json()

        assert body["target_role"] is None
        assert body["excluded_terms"] == []
        assert body["work_models"] == []

    async def test_only_the_fields_sent_are_touched(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await client.put(
            PREFERENCES, headers=auth_headers, json={"excluded_terms": ["call center"]}
        )
        await client.put(PREFERENCES, headers=auth_headers, json={"target_role": "Backend"})

        body = (await client.get(PREFERENCES, headers=auth_headers)).json()
        assert body["excluded_terms"] == ["call center"]
        assert body["target_role"] == "Backend"

    async def test_repeated_and_blank_entries_are_tidied_away(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.put(
            PREFERENCES,
            headers=auth_headers,
            json={"priority_technologies": ["C#", " C# ", "", "React"]},
        )

        assert response.json()["priority_technologies"] == ["C#", "React"]

    async def test_an_unknown_work_model_is_refused_rather_than_stored(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.put(
            PREFERENCES, headers=auth_headers, json={"work_models": ["anywhere"]}
        )

        assert response.status_code == 422

    async def test_preferences_are_private_to_their_account(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        other_auth_headers: dict[str, str],
    ) -> None:
        await client.put(PREFERENCES, headers=auth_headers, json={"target_role": "Backend"})

        theirs = (await client.get(PREFERENCES, headers=other_auth_headers)).json()
        assert theirs["target_role"] is None


class TestTheManagedSearch:
    async def test_stating_a_role_produces_something_to_run(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await client.put(
            PREFERENCES,
            headers=auth_headers,
            json={
                "target_role": "Full Stack Developer",
                "alternative_roles": ["Backend Developer"],
                "work_models": ["remote"],
                "seniority": ["entry"],
                "locations": ["Recife, PE"],
            },
        )

        searches = (await client.get(SEARCHES, headers=auth_headers)).json()
        managed = [row for row in searches if row["name"] == MANAGED_SEARCH_NAME]
        assert len(managed) == 1
        assert '"Full Stack Developer"' in managed[0]["keywords"]
        assert managed[0]["remote_filter"] == "remote"
        assert managed[0]["experience_levels"] == ["entry"]
        assert managed[0]["location"] == "Recife, PE"

    async def test_saving_again_updates_it_instead_of_piling_up(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await client.put(PREFERENCES, headers=auth_headers, json={"target_role": "Backend"})
        await client.put(PREFERENCES, headers=auth_headers, json={"target_role": "Full Stack"})

        rows = (
            await session.scalars(
                select(Search).where(Search.user_id == user.id, Search.name == MANAGED_SEARCH_NAME)
            )
        ).all()
        assert len(rows) == 1
        assert "Full Stack" in rows[0].keywords

    async def test_no_role_produces_no_search_rather_than_an_empty_sweep(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await client.put(PREFERENCES, headers=auth_headers, json={"excluded_terms": ["sales"]})

        searches = (await client.get(SEARCHES, headers=auth_headers)).json()
        assert [row for row in searches if row["name"] == MANAGED_SEARCH_NAME] == []


class TestScreeningBeforeScoring:
    async def test_an_excluded_posting_is_skipped_without_a_model_call(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_ai: FakeAIClient,
    ) -> None:
        await client.put(
            PREFERENCES, headers=auth_headers, json={"excluded_terms": ["call center"]}
        )
        job = await create_job(
            session,
            user,
            title="Atendente de Call Center",
            description="Atendimento telefônico.",
            status=JobStatus.DISCOVERED,
        )
        await session.commit()

        response = await client.post(f"/api/jobs/{job.id}/analyze", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == JobStatus.SKIPPED
        assert fake_ai.call_count("score_job") == 0, "the posting was already ruled out"

        await session.refresh(job)
        assert job.score is None
        assert "call center" in (job.skip_reason or "")

    async def test_a_posting_that_passes_is_still_scored(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_ai: FakeAIClient,
    ) -> None:
        await client.put(
            PREFERENCES, headers=auth_headers, json={"excluded_terms": ["call center"]}
        )
        job = await create_job(
            session,
            user,
            title="Backend Developer",
            description="Python and PostgreSQL.",
            status=JobStatus.DISCOVERED,
        )
        await session.commit()

        await client.post(f"/api/jobs/{job.id}/analyze", headers=auth_headers)

        assert fake_ai.call_count("score_job") == 1
        await session.refresh(job)
        assert job.score is not None

    async def test_another_account_s_exclusions_do_not_apply(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        other_auth_headers: dict[str, str],
        fake_ai: FakeAIClient,
    ) -> None:
        await client.put(
            PREFERENCES, headers=other_auth_headers, json={"excluded_terms": ["backend"]}
        )
        job = await create_job(
            session,
            user,
            title="Backend Developer",
            description="Python.",
            status=JobStatus.DISCOVERED,
        )
        await session.commit()

        await client.post(f"/api/jobs/{job.id}/analyze", headers=auth_headers)

        assert fake_ai.call_count("score_job") == 1
        stored = await session.get(Job, job.id)
        assert stored is not None and stored.status != JobStatus.SKIPPED
