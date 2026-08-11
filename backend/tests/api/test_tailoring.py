"""The CV-tailoring endpoints: generate, read, edit — and the invention guard.

The feature's whole promise is "reorganize, never invent", so the tests that
matter most drive a fabricated technology all the way through the API and assert
it comes back flagged. Isolation, auth, and graceful degradation are covered too.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_access_token
from app.models import AIAnalysis, AnalysisKind, TailoredResume
from tests.fixtures.factories import create_job, create_user
from tests.fixtures.fake_ai import FakeAIClient

URL = "/api/ai/tailor-cv/{job_id}"


class TestGenerate:
    async def test_generates_and_returns_a_reviewable_draft(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)

        response = await client.post(URL.format(job_id=job.id), headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["job_id"] == job.id
        assert body["content"].strip()
        assert body["changes"]
        assert body["was_edited"] is False
        assert body["is_stale"] is False

    async def test_records_the_call_for_audit(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)

        await client.post(URL.format(job_id=job.id), headers=auth_headers)

        analyses = (
            (
                await session.execute(
                    select(AIAnalysis).where(
                        AIAnalysis.job_id == job.id,
                        AIAnalysis.kind == AnalysisKind.CV_TAILORING,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert analyses and analyses[0].model

    async def test_regenerating_overwrites_rather_than_duplicating(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)

        await client.post(URL.format(job_id=job.id), headers=auth_headers)
        await client.post(URL.format(job_id=job.id), headers=auth_headers)

        count = await session.scalar(
            select(func.count()).select_from(TailoredResume).where(TailoredResume.job_id == job.id)
        )
        assert count == 1

    async def test_passes_unsupported_requirements_straight_through(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_ai: FakeAIClient,
    ) -> None:
        job = await create_job(session, user)
        fake_ai.tailor_unsupported = ["AWS Solutions Architect certification"]

        body = (await client.post(URL.format(job_id=job.id), headers=auth_headers)).json()

        assert body["unsupported_requirements"] == ["AWS Solutions Architect certification"]

    async def test_a_truthful_draft_raises_no_invention_flags(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        # The fake's default resume uses only technologies in the profile.
        job = await create_job(session, user)

        body = (await client.post(URL.format(job_id=job.id), headers=auth_headers)).json()

        assert body["invention_flags"] == []


class TestInventionGuardEndToEnd:
    async def test_a_fabricated_technology_is_flagged_all_the_way_to_the_response(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_ai: FakeAIClient,
    ) -> None:
        """The model slips in Kubernetes, which the profile does not mention.

        This is the guarantee the whole feature exists for: the guard catches it
        even though the model "returned" it as legitimate resume text.
        """
        job = await create_job(session, user)
        fake_ai.tailored_markdown = "## Skills\nPython, FastAPI, Kubernetes, PostgreSQL"

        body = (await client.post(URL.format(job_id=job.id), headers=auth_headers)).json()

        assert "Kubernetes" in body["invention_flags"]
        # The guard flags, it does not silently delete — the text is still returned.
        assert "Kubernetes" in body["content"]

    async def test_editing_in_an_invented_skill_is_re_flagged_on_save(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        job = await create_job(session, user)
        await client.post(URL.format(job_id=job.id), headers=auth_headers)

        response = await client.patch(
            URL.format(job_id=job.id),
            headers=auth_headers,
            json={"content": "I now use Rust in production every day."},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["was_edited"] is True
        assert "Rust" in body["invention_flags"]


class TestReadAndStaleness:
    async def test_reading_before_generating_is_404(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)

        response = await client.get(URL.format(job_id=job.id), headers=auth_headers)

        assert response.status_code == 404

    async def test_reading_after_generating_returns_the_draft(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)
        await client.post(URL.format(job_id=job.id), headers=auth_headers)

        response = await client.get(URL.format(job_id=job.id), headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["content"].strip()

    async def test_changing_the_profile_marks_the_draft_stale(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)
        await client.post(URL.format(job_id=job.id), headers=auth_headers)

        # The resume the draft was built from just changed underneath it.
        await client.put(
            "/api/profile",
            headers=auth_headers,
            json={"resume_text": "A completely rewritten resume with new content."},
        )

        body = (await client.get(URL.format(job_id=job.id), headers=auth_headers)).json()
        assert body["is_stale"] is True


class TestGuardrails:
    async def test_a_refusal_returns_502_and_stores_no_draft(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_ai: FakeAIClient,
    ) -> None:
        job = await create_job(session, user)
        fake_ai.refused = True

        response = await client.post(URL.format(job_id=job.id), headers=auth_headers)

        assert response.status_code == 502
        count = await session.scalar(
            select(func.count()).select_from(TailoredResume).where(TailoredResume.job_id == job.id)
        )
        assert count == 0

    async def test_an_api_failure_returns_502(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_ai: FakeAIClient,
    ) -> None:
        job = await create_job(session, user)
        fake_ai.api_error = True

        response = await client.post(URL.format(job_id=job.id), headers=auth_headers)

        assert response.status_code == 502

    async def test_a_job_without_a_description_is_a_precondition_error(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user, description=None)

        response = await client.post(URL.format(job_id=job.id), headers=auth_headers)

        assert response.status_code == 412

    async def test_a_profile_without_resume_text_is_a_precondition_error(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        thin = await create_user(session, email="thin@example.com", profile={"resume_text": ""})
        headers = {"Authorization": f"Bearer {create_access_token(thin.id)}"}
        job = await create_job(session, thin)

        response = await client.post(URL.format(job_id=job.id), headers=headers)

        assert response.status_code == 412

    async def test_patching_a_missing_draft_is_404(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)

        response = await client.patch(
            URL.format(job_id=job.id), headers=auth_headers, json={"content": "anything"}
        )

        assert response.status_code == 404


class TestAuthAndIsolation:
    async def test_requires_authentication(
        self, client: AsyncClient, session: AsyncSession, user: Any
    ) -> None:
        job = await create_job(session, user)

        assert (await client.post(URL.format(job_id=job.id))).status_code == 401
        assert (await client.get(URL.format(job_id=job.id))).status_code == 401

    async def test_a_user_cannot_tailor_another_users_job(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        other_auth_headers: dict[str, str],
    ) -> None:
        job = await create_job(session, user)

        response = await client.post(URL.format(job_id=job.id), headers=other_auth_headers)

        assert response.status_code == 404

    async def test_a_user_cannot_read_another_users_draft(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        other_auth_headers: dict[str, str],
    ) -> None:
        job = await create_job(session, user)
        await client.post(URL.format(job_id=job.id), headers=auth_headers)

        response = await client.get(URL.format(job_id=job.id), headers=other_auth_headers)

        assert response.status_code == 404
