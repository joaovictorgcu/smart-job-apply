"""The CSV export of the application history."""

from __future__ import annotations

import csv
import io
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.models import ApplicationOutcome, ApplicationStatus, JobStatus, User
from tests.fixtures.factories import create_application, create_job


def _rows(payload: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(payload)))


class TestExport:
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get("/api/applications/export")).status_code == 401

    async def test_returns_a_csv_attachment_with_job_columns(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user, score=88, status=JobStatus.APPLIED)
        await create_application(
            session,
            user,
            job,
            status=ApplicationStatus.SUBMITTED,
            outcome=ApplicationOutcome.INTERVIEW,
            submitted_at=utcnow(),
        )

        response = await client.get("/api/applications/export", headers=auth_headers)

        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/csv")
        assert 'filename="applications.csv"' in response.headers["content-disposition"]
        rows = _rows(response.text)
        assert len(rows) == 1
        assert rows[0]["job_title"] == job.title
        assert rows[0]["score"] == "88"
        assert rows[0]["status"] == "submitted"
        assert rows[0]["outcome"] == "interview"
        assert rows[0]["submitted_at"] != ""

    async def test_is_scoped_to_the_user(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: User,
        other_user: User,
        auth_headers: dict[str, str],
    ) -> None:
        await create_application(
            session, user, await create_job(session, user, company="Own Co")
        )
        await create_application(
            session, other_user, await create_job(session, other_user, company="Other Co")
        )

        response = await client.get("/api/applications/export", headers=auth_headers)

        assert "Own Co" in response.text
        assert "Other Co" not in response.text

    async def test_an_empty_history_is_just_the_header(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get("/api/applications/export", headers=auth_headers)

        assert response.status_code == 200
        assert _rows(response.text) == []
