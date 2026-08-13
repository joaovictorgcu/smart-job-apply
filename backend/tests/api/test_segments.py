"""Interview-rate analytics sliced by company, location and workplace."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.models import ApplicationOutcome, ApplicationStatus, JobStatus, User
from tests.fixtures.factories import create_application, create_job


async def _submit(
    session: AsyncSession, user: User, *, company: str, outcome: ApplicationOutcome
) -> None:
    job = await create_job(
        session, user, company=company, status=JobStatus.APPLIED, workplace_type="remote"
    )
    await create_application(
        session,
        user,
        job,
        status=ApplicationStatus.SUBMITTED,
        outcome=outcome,
        submitted_at=utcnow(),
    )


class TestSegments:
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get("/api/stats/segments")).status_code == 401

    async def test_groups_by_company_with_rates(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await _submit(session, user, company="Acme", outcome=ApplicationOutcome.INTERVIEW)
        await _submit(session, user, company="Acme", outcome=ApplicationOutcome.REJECTED)
        await _submit(session, user, company="Globex", outcome=ApplicationOutcome.APPLIED)

        payload = (await client.get("/api/stats/segments", headers=auth_headers)).json()

        by_company = {row["label"]: row for row in payload["by_company"]}
        assert by_company["Acme"]["total"] == 2
        assert by_company["Acme"]["interviews"] == 1
        assert by_company["Acme"]["rate"] == 0.5
        assert by_company["Globex"]["rate"] == 0.0
        # All three jobs are remote, so the workplace slice collapses to one row.
        assert payload["by_workplace"][0]["label"] == "remote"
        assert payload["by_workplace"][0]["total"] == 3

    async def test_only_counts_submitted_applications(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        # A draft must not appear anywhere in the slices.
        job = await create_job(session, user, company="DraftCo")
        await create_application(session, user, job)

        payload = (await client.get("/api/stats/segments", headers=auth_headers)).json()

        assert payload["by_company"] == []

    async def test_is_scoped_to_the_user(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: User,
        other_auth_headers: dict[str, str],
    ) -> None:
        await _submit(session, user, company="Acme", outcome=ApplicationOutcome.OFFER)

        payload = (await client.get("/api/stats/segments", headers=other_auth_headers)).json()

        assert payload["by_company"] == []
