"""The applications endpoints — and the gate in front of `submit`.

This is where assisted mode is enforced over HTTP. Four independent conditions all
have to hold before anything is sent: the caller owns the application, it is
`AWAITING_REVIEW`, `dry_run` is off, and `confirm` is explicitly true. Each of them
is tested on its own, and each rejection is checked against
`FakeLinkedInService.submit`.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_access_token
from app.models import ApplicationEventType, ApplicationStatus, JobStatus
from tests.fixtures.factories import (
    create_application,
    create_job,
    create_user,
    days_ago,
)
from tests.fixtures.fake_linkedin import FakeLinkedInService

# Statuses from which submitting must be refused. `AWAITING_REVIEW` is the only
# state a submission may start from.
NON_REVIEWABLE = [
    ApplicationStatus.DRAFT,
    ApplicationStatus.PREPARING,
    ApplicationStatus.SUBMITTING,
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.DISCARDED,
    ApplicationStatus.FAILED,
]


async def live_user(session: AsyncSession, email: str, **settings: Any) -> tuple[Any, dict[str, str]]:
    """A user with `dry_run` off — the only user who could ever submit."""
    values = {"dry_run": False}
    values.update(settings)
    user = await create_user(session, email=email, settings=values)
    return user, {"Authorization": f"Bearer {create_access_token(user.id)}"}


class TestListAndRead:
    async def test_lists_with_a_page_envelope(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)
        await create_application(session, user, job)

        response = await client.get("/api/applications", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1

    async def test_filters_by_status(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        first = await create_job(session, user)
        second = await create_job(session, user)
        awaiting = await create_application(
            session, user, first, status=ApplicationStatus.AWAITING_REVIEW
        )
        await create_application(session, user, second, status=ApplicationStatus.SUBMITTED)

        body = (
            await client.get(
                "/api/applications", headers=auth_headers, params={"status": "awaiting_review"}
            )
        ).json()

        assert [item["id"] for item in body["items"]] == [awaiting.id]

    async def test_the_detail_carries_the_job_and_the_event_trail(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)
        application = await create_application(session, user, job)

        response = await client.get(f"/api/applications/{application.id}", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["job"]["id"] == job.id
        assert isinstance(body["events"], list)

    async def test_an_unknown_id_is_a_404(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get("/api/applications/999999", headers=auth_headers)

        assert response.status_code == 404


class TestSubmitRequiresExplicitConfirmation:
    async def test_confirm_false_is_refused(
        self, client: AsyncClient, session: AsyncSession, fake_linkedin: FakeLinkedInService
    ) -> None:
        user, headers = await live_user(session, "confirm-false@example.com")
        job = await create_job(session, user, status=JobStatus.QUEUED)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        response = await client.post(
            f"/api/applications/{application.id}/submit",
            headers=headers,
            json={"confirm": False},
        )

        assert 400 <= response.status_code < 500, response.text
        assert fake_linkedin.submit_called is False
        await session.refresh(application)
        assert application.status == ApplicationStatus.AWAITING_REVIEW

    async def test_a_missing_confirm_field_is_refused(
        self, client: AsyncClient, session: AsyncSession, fake_linkedin: FakeLinkedInService
    ) -> None:
        user, headers = await live_user(session, "confirm-absent@example.com")
        job = await create_job(session, user, status=JobStatus.QUEUED)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        response = await client.post(
            f"/api/applications/{application.id}/submit", headers=headers, json={}
        )

        assert response.status_code == 422, response.text
        assert fake_linkedin.submit_called is False

    async def test_an_empty_body_is_refused(
        self, client: AsyncClient, session: AsyncSession, fake_linkedin: FakeLinkedInService
    ) -> None:
        user, headers = await live_user(session, "confirm-empty@example.com")
        job = await create_job(session, user, status=JobStatus.QUEUED)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        response = await client.post(
            f"/api/applications/{application.id}/submit", headers=headers
        )

        assert 400 <= response.status_code < 500, response.text
        assert fake_linkedin.submit_called is False


class TestSubmitRefusesInDryRun:
    async def test_dry_run_blocks_the_submission(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str],
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        """`dry_run` is the default; it must not be bypassable by confirming."""
        job = await create_job(session, user, status=JobStatus.QUEUED)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW, was_dry_run=True
        )

        response = await client.post(
            f"/api/applications/{application.id}/submit",
            headers=auth_headers,
            json={"confirm": True},
        )

        assert 400 <= response.status_code < 500, response.text
        assert fake_linkedin.submit_called is False
        await session.refresh(application)
        assert application.status != ApplicationStatus.SUBMITTED
        assert application.submitted_at is None


class TestSubmitRequiresAwaitingReview:
    @pytest.mark.parametrize("status", NON_REVIEWABLE, ids=[s.value for s in NON_REVIEWABLE])
    async def test_only_a_reviewed_application_may_be_submitted(
        self,
        client: AsyncClient,
        session: AsyncSession,
        fake_linkedin: FakeLinkedInService,
        status: ApplicationStatus,
    ) -> None:
        user, headers = await live_user(session, f"status-{status.value}@example.com")
        job = await create_job(session, user)
        application = await create_application(session, user, job, status=status)

        response = await client.post(
            f"/api/applications/{application.id}/submit",
            headers=headers,
            json={"confirm": True},
        )

        assert 400 <= response.status_code < 500, response.text
        assert fake_linkedin.submit_called is False

    async def test_an_already_submitted_application_is_not_resubmitted(
        self, client: AsyncClient, session: AsyncSession, fake_linkedin: FakeLinkedInService
    ) -> None:
        user, headers = await live_user(session, "resubmit@example.com")
        job = await create_job(session, user, status=JobStatus.APPLIED)
        application = await create_application(
            session,
            user,
            job,
            status=ApplicationStatus.SUBMITTED,
            submitted_at=days_ago(1),
        )
        submitted_at = application.submitted_at

        await client.post(
            f"/api/applications/{application.id}/submit",
            headers=headers,
            json={"confirm": True},
        )

        await session.refresh(application)
        assert application.submitted_at == submitted_at
        assert fake_linkedin.submit_called is False


class TestSubmitHappyPath:
    async def test_a_reviewed_application_with_dry_run_off_is_accepted(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user, headers = await live_user(session, "approved@example.com")
        job = await create_job(session, user, status=JobStatus.QUEUED)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        response = await client.post(
            f"/api/applications/{application.id}/submit",
            headers=headers,
            json={"confirm": True},
        )

        assert response.status_code in (200, 202), response.text
        await session.refresh(application)
        assert application.status != ApplicationStatus.AWAITING_REVIEW
        assert application.approved_at is not None


class TestEditBeforeApproval:
    async def test_the_user_can_rewrite_the_cover_letter(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        response = await client.patch(
            f"/api/applications/{application.id}",
            headers=auth_headers,
            json={"cover_letter": "My own words, thank you."},
        )

        assert response.status_code == 200, response.text
        assert response.json()["cover_letter"] == "My own words, thank you."
        await session.refresh(application)
        assert application.cover_letter == "My own words, thank you."

    async def test_the_user_can_correct_a_screening_answer(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        response = await client.patch(
            f"/api/applications/{application.id}",
            headers=auth_headers,
            json={
                "screening_answers": [
                    {
                        "question": "Years of Python experience?",
                        "answer": "9",
                        "question_type": "number",
                        "confidence": "high",
                        "field_id": "q-years",
                    }
                ]
            },
        )

        assert response.status_code == 200, response.text
        await session.refresh(application)
        assert application.screening_answers[0]["answer"] == "9"

    async def test_editing_records_the_change_in_the_trail(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        await client.patch(
            f"/api/applications/{application.id}",
            headers=auth_headers,
            json={"cover_letter": "Edited."},
        )

        events = (
            await client.get(f"/api/applications/{application.id}/events", headers=auth_headers)
        ).json()
        assert any(
            event["event_type"] == ApplicationEventType.USER_EDITED.value for event in events
        )

    async def test_a_submitted_application_can_no_longer_be_edited(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user, status=JobStatus.APPLIED)
        application = await create_application(
            session, user, job, status=ApplicationStatus.SUBMITTED
        )

        response = await client.patch(
            f"/api/applications/{application.id}",
            headers=auth_headers,
            json={"cover_letter": "Too late."},
        )

        assert 400 <= response.status_code < 500, response.text


class TestDiscard:
    async def test_discarding_marks_the_application_and_never_submits(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_linkedin: FakeLinkedInService,
    ) -> None:
        job = await create_job(session, user)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        response = await client.post(
            f"/api/applications/{application.id}/discard", headers=auth_headers
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == ApplicationStatus.DISCARDED.value
        assert fake_linkedin.submit_called is False

    async def test_a_discarded_application_cannot_then_be_submitted(
        self, client: AsyncClient, session: AsyncSession, fake_linkedin: FakeLinkedInService
    ) -> None:
        user, headers = await live_user(session, "discarded@example.com")
        job = await create_job(session, user)
        application = await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW
        )

        await client.post(f"/api/applications/{application.id}/discard", headers=headers)
        response = await client.post(
            f"/api/applications/{application.id}/submit",
            headers=headers,
            json={"confirm": True},
        )

        assert 400 <= response.status_code < 500, response.text
        assert fake_linkedin.submit_called is False


class TestEvents:
    async def test_returns_the_trail_in_order(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        from app.observability.audit import record_event

        job = await create_job(session, user)
        application = await create_application(session, user, job)
        for event_type in (
            ApplicationEventType.FORM_OPENED,
            ApplicationEventType.QUESTION_ANSWERED,
            ApplicationEventType.AWAITING_REVIEW,
        ):
            await record_event(
                session, application_id=application.id, event_type=event_type, message="step"
            )
        await session.commit()

        response = await client.get(
            f"/api/applications/{application.id}/events", headers=auth_headers
        )

        assert response.status_code == 200
        types = [event["event_type"] for event in response.json()]
        assert types == [
            ApplicationEventType.FORM_OPENED.value,
            ApplicationEventType.QUESTION_ANSWERED.value,
            ApplicationEventType.AWAITING_REVIEW.value,
        ]
