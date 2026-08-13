"""The second-pass AI review of a drafted application."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIAnalysis, User
from app.models.enums import AnalysisKind
from tests.fixtures.factories import create_application, create_job


async def _draft(session: AsyncSession, user: User) -> Any:
    job = await create_job(session, user, score=85)
    return await create_application(session, user, job)


class TestReviewRoute:
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.post("/api/ai/review/1")).status_code == 401

    async def test_returns_edits_critique_and_coverage(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await _draft(session, user)

        response = await client.post(f"/api/ai/review/{application.id}", headers=auth_headers)

        assert response.status_code == 200, response.text
        review = response.json()
        assert review["edits"][0]["old_string"] == "I am excited about this role"
        # Four mandatory categories, always present.
        assert [note["category"] for note in review["critique"]] == [
            "missed_keywords",
            "company_angle",
            "reframing",
            "tone",
        ]
        statuses = {row["status"] for row in review["coverage"]}
        assert "missing_have_it" in statuses and "missing_gap" in statuses

    async def test_is_persisted_in_the_ai_audit_trail(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await _draft(session, user)

        await client.post(f"/api/ai/review/{application.id}", headers=auth_headers)

        rows = (
            (
                await session.execute(
                    select(AIAnalysis).where(AIAnalysis.kind == AnalysisKind.REVIEW)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].result["summary"] == "Deterministic test review."

    async def test_a_refusal_degrades_to_manual_review(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_ai: Any,
    ) -> None:
        fake_ai.refused = True
        application = await _draft(session, user)

        response = await client.post(f"/api/ai/review/{application.id}", headers=auth_headers)

        assert response.status_code == 502

    async def test_is_scoped_to_the_user(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: User,
        other_auth_headers: dict[str, str],
    ) -> None:
        application = await _draft(session, user)

        response = await client.post(
            f"/api/ai/review/{application.id}", headers=other_auth_headers
        )

        assert response.status_code == 404
