"""Submission snapshot, interview stages, and the prep pack."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.models import ApplicationStatus, User
from app.services import application_service
from tests.fixtures.factories import create_application, create_job


async def _submitted(session: AsyncSession, user: User) -> Any:
    job = await create_job(session, user, score=85)
    application = await create_application(
        session, user, job, status=ApplicationStatus.AWAITING_REVIEW
    )
    application = await application_service.mark_submitted(session, user, application.id)
    # Release the fixture session's write lock: the routes under test write
    # through their own connection.
    await session.commit()
    return application


class TestSubmissionSnapshot:
    async def test_submitting_freezes_the_posting_and_the_materials(
        self, session: AsyncSession, user: Any
    ) -> None:
        application = await _submitted(session, user)

        snapshot = application.submitted_snapshot
        assert snapshot is not None
        assert snapshot["job_title"] == application.job.title
        assert snapshot["description"] == application.job.description
        assert snapshot["cover_letter"] == application.cover_letter
        assert snapshot["screening_answers"] == application.screening_answers

    async def test_later_edits_do_not_rewrite_the_snapshot(
        self, session: AsyncSession, user: Any
    ) -> None:
        application = await _submitted(session, user)
        original_letter = application.submitted_snapshot["cover_letter"]

        # A direct mutation after submit (the draft can no longer be PATCHed,
        # but nothing else should touch the frozen copy either).
        application.cover_letter = "rewritten afterwards"
        await session.flush()

        assert application.submitted_snapshot["cover_letter"] == original_letter


class TestInterviewStages:
    async def test_full_stage_lifecycle(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await _submitted(session, user)

        created = await client.post(
            f"/api/applications/{application.id}/stages",
            headers=auth_headers,
            json={"stage_type": "phone_screen", "note": "Recruiter call"},
        )
        assert created.status_code == 200, created.text
        stage_id = created.json()["id"]

        listed = (
            await client.get(f"/api/applications/{application.id}/stages", headers=auth_headers)
        ).json()
        assert [stage["stage_type"] for stage in listed] == ["phone_screen"]

        completed = await client.patch(
            f"/api/applications/{application.id}/stages/{stage_id}",
            headers=auth_headers,
            json={"mark_completed": True, "note": "Went well"},
        )
        assert completed.json()["completed_at"] is not None
        assert completed.json()["note"] == "Went well"

        deleted = await client.delete(
            f"/api/applications/{application.id}/stages/{stage_id}", headers=auth_headers
        )
        assert deleted.status_code == 204

    async def test_an_unsubmitted_application_has_no_process(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)
        application = await create_application(session, user, job)

        response = await client.post(
            f"/api/applications/{application.id}/stages",
            headers=auth_headers,
            json={"stage_type": "technical"},
        )

        assert response.status_code == 412

    async def test_rejects_an_unknown_stage_type(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await _submitted(session, user)

        response = await client.post(
            f"/api/applications/{application.id}/stages",
            headers=auth_headers,
            json={"stage_type": "vibes"},
        )

        assert response.status_code == 422

    async def test_is_scoped_to_the_user(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: User,
        other_auth_headers: dict[str, str],
    ) -> None:
        application = await _submitted(session, user)

        response = await client.get(
            f"/api/applications/{application.id}/stages", headers=other_auth_headers
        )

        assert response.status_code == 404


class TestInterviewPrep:
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.post("/api/ai/interview-prep/1")).status_code == 401

    async def test_returns_the_prep_pack(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        application = await _submitted(session, user)

        response = await client.post(
            f"/api/ai/interview-prep/{application.id}", headers=auth_headers
        )

        assert response.status_code == 200, response.text
        assert "## Provaveis perguntas" in response.json()["content"]

    async def test_a_refusal_degrades_cleanly(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        auth_headers: dict[str, str],
        fake_ai: Any,
    ) -> None:
        fake_ai.refused = True
        application = await _submitted(session, user)

        response = await client.post(
            f"/api/ai/interview-prep/{application.id}", headers=auth_headers
        )

        assert response.status_code == 502

    async def test_snapshot_wins_over_a_changed_job(
        self, session: AsyncSession, user: Any, fake_ai: Any
    ) -> None:
        from app.ai import scoring
        from app.automation.contracts import ProfileContext

        application = await _submitted(session, user)
        application.job.description = "posting text replaced after submission"
        await session.flush()

        captured: dict[str, Any] = {}
        original = fake_ai.interview_prep

        async def spy(profile: Any = None, job: Any = None, **kwargs: Any) -> Any:
            captured["description"] = job.description
            return await original(profile, job, **kwargs)

        fake_ai.interview_prep = spy
        await scoring.prepare_interview(
            session,
            user=user,
            job=application.job,
            application=application,
            profile_ctx=ProfileContext(headline="dev"),
            settings_row=None,
            client=fake_ai,
        )

        assert captured["description"] == application.submitted_snapshot["description"]
        assert captured["description"] != "posting text replaced after submission"

    async def test_stage_timestamp_helper(self, session: AsyncSession, user: Any) -> None:
        # Guard: utcnow-based completion stamps are timezone-aware.
        application = await _submitted(session, user)
        stage = await application_service.add_stage(
            session, user, application.id, stage_type="technical", scheduled_at=utcnow()
        )
        updated = await application_service.update_stage(
            session, user, application.id, stage.id, mark_completed=True
        )
        assert updated.completed_at is not None and updated.completed_at.tzinfo is not None
