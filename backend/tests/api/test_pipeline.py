"""The pipeline board, outcome transitions, and the score-vs-interview analytics."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.models import (
    Application,
    ApplicationEvent,
    ApplicationEventType,
    ApplicationOutcome,
    ApplicationStatus,
    JobStatus,
    User,
)
from app.services import application_service
from tests.fixtures.factories import create_application, create_job


async def _submit(
    session: AsyncSession,
    user: User,
    *,
    score: int,
    outcome: ApplicationOutcome,
) -> Application:
    """A submitted application on a scored job, at a given outcome."""
    job = await create_job(session, user, score=score, status=JobStatus.APPLIED)
    return await create_application(
        session,
        user,
        job,
        status=ApplicationStatus.SUBMITTED,
        outcome=outcome,
        submitted_at=utcnow(),
        outcome_updated_at=utcnow(),
    )


class TestBoard:
    async def test_lists_only_submitted_applications(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await _submit(session, user, score=90, outcome=ApplicationOutcome.INTERVIEW)
        # An application still awaiting review must not appear on the board.
        await create_application(session, user, await create_job(session, user))

        response = await client.get("/api/applications/board", headers=auth_headers)

        assert response.status_code == 200, response.text
        board = response.json()
        assert len(board) == 1
        assert board[0]["outcome"] == "interview"
        assert board[0]["score"] == 90

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get("/api/applications/board")).status_code == 401

    async def test_is_scoped_to_the_user(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        other_auth_headers: dict[str, str],
    ) -> None:
        await _submit(session, user, score=88, outcome=ApplicationOutcome.APPLIED)

        board = (await client.get("/api/applications/board", headers=other_auth_headers)).json()

        assert board == []


class TestSetOutcome:
    async def test_moves_a_submitted_application(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await _submit(session, user, score=80, outcome=ApplicationOutcome.APPLIED)

        response = await client.patch(
            f"/api/applications/{application.id}/outcome",
            headers=auth_headers,
            json={"outcome": "interview"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["outcome"] == "interview"

    async def test_records_the_change_in_the_audit_trail(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await _submit(session, user, score=80, outcome=ApplicationOutcome.APPLIED)

        await client.patch(
            f"/api/applications/{application.id}/outcome",
            headers=auth_headers,
            json={"outcome": "offer"},
        )

        events = (
            (
                await session.execute(
                    select(ApplicationEvent).where(
                        ApplicationEvent.application_id == application.id,
                        ApplicationEvent.event_type == ApplicationEventType.OUTCOME_CHANGED,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert events and events[0].payload.get("to") == "offer"

    async def test_an_unsubmitted_application_has_no_outcome_to_set(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        # A draft awaiting review is not on the board and cannot take an outcome.
        application = await create_application(session, user, await create_job(session, user))

        response = await client.patch(
            f"/api/applications/{application.id}/outcome",
            headers=auth_headers,
            json={"outcome": "interview"},
        )

        assert response.status_code == 412

    async def test_is_scoped_to_the_user(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        other_auth_headers: dict[str, str],
    ) -> None:
        application = await _submit(session, user, score=80, outcome=ApplicationOutcome.APPLIED)

        response = await client.patch(
            f"/api/applications/{application.id}/outcome",
            headers=other_auth_headers,
            json={"outcome": "interview"},
        )

        assert response.status_code == 404


class TestSubmitStartsAtApplied:
    async def test_marking_submitted_sets_the_outcome_to_applied(
        self, session: AsyncSession, user: Any
    ) -> None:
        job = await create_job(session, user)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )
        assert application.outcome is None

        updated = await application_service.mark_submitted(session, user, application.id)

        assert updated.outcome == ApplicationOutcome.APPLIED
        assert updated.outcome_updated_at is not None


class TestAnalytics:
    async def test_interview_rate_climbs_with_the_score(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        await _submit(session, user, score=95, outcome=ApplicationOutcome.OFFER)
        await _submit(session, user, score=92, outcome=ApplicationOutcome.INTERVIEW)
        await _submit(session, user, score=85, outcome=ApplicationOutcome.APPLIED)
        await _submit(session, user, score=78, outcome=ApplicationOutcome.REJECTED)

        stats = (await client.get("/api/stats/outcomes", headers=auth_headers)).json()

        assert stats["total_submitted"] == 4
        assert stats["interviews"] == 2  # offer + interview
        assert stats["offers"] == 1
        bands = {band["label"]: band for band in stats["interview_rate_by_band"]}
        assert bands["90-100"]["interviews"] == 2
        assert bands["90-100"]["total"] == 2
        assert bands["90-100"]["rate"] == 1.0
        assert bands["80-89"]["interviews"] == 0
        assert bands["70-79"]["interviews"] == 0

    async def test_is_empty_with_nothing_submitted(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        stats = (await client.get("/api/stats/outcomes", headers=auth_headers)).json()

        assert stats["total_submitted"] == 0
        assert stats["interview_rate"] is None

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get("/api/stats/outcomes")).status_code == 401
