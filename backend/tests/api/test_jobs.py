"""The jobs endpoints: listing, filtering, detail, skip and analyze."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIAnalysis, JobStatus
from tests.fixtures.factories import create_job, create_search, create_user
from tests.fixtures.fake_ai import FakeAIClient


class TestListJobs:
    async def test_returns_a_page_envelope(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await create_job(session, user)

        response = await client.get("/api/jobs", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert {"limit", "offset"} <= body.keys()

    async def test_filters_by_status(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await create_job(session, user, status=JobStatus.DISCOVERED)
        analyzed = await create_job(session, user, status=JobStatus.ANALYZED, score=88)

        body = (
            await client.get("/api/jobs", headers=auth_headers, params={"status": "analyzed"})
        ).json()

        assert [item["id"] for item in body["items"]] == [analyzed.id]

    async def test_filters_by_minimum_score(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await create_job(session, user, status=JobStatus.ANALYZED, score=40)
        strong = await create_job(session, user, status=JobStatus.ANALYZED, score=91)

        body = (
            await client.get("/api/jobs", headers=auth_headers, params={"min_score": 80})
        ).json()

        assert [item["id"] for item in body["items"]] == [strong.id]

    async def test_filters_by_search(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        search = await create_search(session, user)
        mine = await create_job(session, user, search_id=search.id)
        await create_job(session, user)

        body = (
            await client.get(
                "/api/jobs", headers=auth_headers, params={"search_id": search.id}
            )
        ).json()

        assert [item["id"] for item in body["items"]] == [mine.id]

    async def test_paginates(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        for _ in range(5):
            await create_job(session, user)

        first = (
            await client.get(
                "/api/jobs", headers=auth_headers, params={"limit": 2, "offset": 0}
            )
        ).json()
        second = (
            await client.get(
                "/api/jobs", headers=auth_headers, params={"limit": 2, "offset": 2}
            )
        ).json()

        assert first["total"] == 5
        assert len(first["items"]) == 2
        assert len(second["items"]) == 2
        assert {item["id"] for item in first["items"]}.isdisjoint(
            item["id"] for item in second["items"]
        )

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get("/api/jobs")).status_code == 401


class TestJobDetail:
    async def test_includes_the_description(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user, description="The full posting text.")

        response = await client.get(f"/api/jobs/{job.id}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["description"] == "The full posting text."

    async def test_an_unknown_id_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        assert (await client.get("/api/jobs/999999", headers=auth_headers)).status_code == 404


class TestSkipJob:
    async def test_marks_the_job_skipped(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)

        response = await client.post(f"/api/jobs/{job.id}/skip", headers=auth_headers)

        assert response.status_code == 200, response.text
        assert response.json()["status"] == JobStatus.SKIPPED.value
        await session.refresh(job)
        assert job.status == JobStatus.SKIPPED

    async def test_records_why_it_was_skipped(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=88)

        await client.post(f"/api/jobs/{job.id}/skip", headers=auth_headers)

        await session.refresh(job)
        assert job.skip_reason, "a skipped job should say why, for the history view"

    async def test_never_touches_the_browser(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_linkedin: Any,
    ) -> None:
        job = await create_job(session, user)

        await client.post(f"/api/jobs/{job.id}/skip", headers=auth_headers)

        assert fake_linkedin.browser_calls == []


class TestAnalyzeJob:
    async def test_scores_the_job_with_the_ai_client(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_ai: FakeAIClient,
    ) -> None:
        job = await create_job(session, user, status=JobStatus.DISCOVERED)

        response = await client.post(f"/api/jobs/{job.id}/analyze", headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["score"] == fake_ai.score
        assert body["status"] == JobStatus.ANALYZED.value

    async def test_stores_the_reasons_and_gaps(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user, status=JobStatus.DISCOVERED)

        await client.post(f"/api/jobs/{job.id}/analyze", headers=auth_headers)

        await session.refresh(job)
        assert job.score_reasons
        assert job.missing_requirements

    async def test_records_the_call_for_audit(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user, status=JobStatus.DISCOVERED)

        await client.post(f"/api/jobs/{job.id}/analyze", headers=auth_headers)

        analyses = (
            (await session.execute(select(AIAnalysis).where(AIAnalysis.job_id == job.id)))
            .scalars()
            .all()
        )
        assert analyses
        assert analyses[0].model

    async def test_a_score_below_the_minimum_skips_the_job(
        self,
        client: AsyncClient,
        session: AsyncSession,
        auth_headers: dict[str, str],
        monkeypatch: Any,
    ) -> None:
        """The user's `min_score` is the gate; nothing weak reaches the queue."""
        from app.auth.security import create_access_token

        picky = await create_user(
            session, email="picky@example.com", settings={"min_score": 90}
        )
        headers = {"Authorization": f"Bearer {create_access_token(picky.id)}"}
        job = await create_job(session, picky, status=JobStatus.DISCOVERED)

        # The fake scores 85, which is under this user's 90.
        response = await client.post(f"/api/jobs/{job.id}/analyze", headers=headers)

        assert response.status_code == 200, response.text
        assert response.json()["status"] == JobStatus.SKIPPED.value
        await session.refresh(job)
        assert job.skip_reason

    async def test_analyzing_never_opens_the_application_form(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_linkedin: Any,
    ) -> None:
        job = await create_job(session, user, status=JobStatus.DISCOVERED)

        await client.post(f"/api/jobs/{job.id}/analyze", headers=auth_headers)

        assert fake_linkedin.call_count("open_easy_apply") == 0
        assert fake_linkedin.submit_called is False

    async def test_an_unknown_id_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post("/api/jobs/999999/analyze", headers=auth_headers)

        assert response.status_code == 404


class TestSearches:
    async def test_creates_lists_updates_and_deletes(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        created = await client.post(
            "/api/searches",
            headers=auth_headers,
            json={"name": "Remote Python", "keywords": "python", "max_results": 10},
        )
        assert created.status_code in (200, 201), created.text
        search_id = created.json()["id"]

        listed = await client.get("/api/searches", headers=auth_headers)
        assert [item["id"] for item in listed.json()] == [search_id]

        patched = await client.patch(
            f"/api/searches/{search_id}", headers=auth_headers, json={"is_active": False}
        )
        assert patched.status_code == 200
        assert patched.json()["is_active"] is False

        deleted = await client.delete(f"/api/searches/{search_id}", headers=auth_headers)
        assert deleted.status_code == 204
        assert (await client.get("/api/searches", headers=auth_headers)).json() == []

    async def test_rejects_an_empty_keyword_list(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/api/searches", headers=auth_headers, json={"name": "Broken", "keywords": ""}
        )

        assert response.status_code == 422

    async def test_caps_the_results_per_run(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """A huge sweep is what gets an account noticed, so the schema caps it."""
        response = await client.post(
            "/api/searches",
            headers=auth_headers,
            json={"name": "Too broad", "keywords": "python", "max_results": 5000},
        )

        assert response.status_code == 422
