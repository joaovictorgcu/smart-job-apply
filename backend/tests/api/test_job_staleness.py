"""Deadlines, expiry, and the score history endpoint.

A posting is not forever. Past its deadline, or gone from the portal, preparing it
would spend one of the day's submissions on a form nobody will read — so both the
preview and the prepare endpoint have to treat it like an application already sent.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.models import AutomationRun, Job, JobScore, JobStatus
from app.services import job_service
from tests.fixtures.factories import create_job


async def add_score(
    session: AsyncSession, user: Any, job: Job, overall: int, **overrides: Any
) -> JobScore:
    """One history row, written directly: the API only ever reads them."""
    values: dict[str, Any] = {
        "verdict": "good",
        "dimensions": [{"dimension": "skills", "score": overall, "evidence": "Python."}],
        "gates": [{"gate": "language", "status": "pass", "evidence": "English."}],
        "model": "claude-opus-5",
        "depth": "deep",
        "profile_fingerprint": "f" * 64,
    }
    values.update(overrides)
    row = JobScore(job_id=job.id, user_id=user.id, overall=overall, **values)
    session.add(row)
    await session.flush()
    await session.commit()
    return row


async def count_runs(session: AsyncSession, user: Any) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(AutomationRun).where(AutomationRun.user_id == user.id)
        )
    ).scalar_one()


class TestScoreHistoryEndpoint:
    async def test_returns_the_verdicts_newest_first(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user, score=81)
        await add_score(session, user, job, 62, created_at=utcnow() - timedelta(days=2))
        await add_score(session, user, job, 81)

        response = await client.get(f"/api/jobs/{job.id}/scores", headers=auth_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert [item["overall"] for item in body] == [81, 62]
        assert body[0]["dimensions"][0]["dimension"] == "skills"
        assert body[0]["depth"] == "deep"

    async def test_another_users_job_is_not_found(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        other_auth_headers: dict[str, str],
    ) -> None:
        job = await create_job(session, user)
        await add_score(session, user, job, 81)

        response = await client.get(f"/api/jobs/{job.id}/scores", headers=other_auth_headers)

        assert response.status_code == 404

    async def test_a_job_never_scored_returns_an_empty_list(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)

        response = await client.get(f"/api/jobs/{job.id}/scores", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []


class TestDeadlinePatch:
    async def test_the_deadline_round_trips(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user)
        deadline = (utcnow() + timedelta(days=5)).replace(microsecond=0)

        patched = await client.patch(
            f"/api/jobs/{job.id}",
            headers=auth_headers,
            json={"deadline": deadline.isoformat()},
        )

        assert patched.status_code == 200, patched.text
        assert patched.json()["deadline"].startswith(deadline.date().isoformat())
        detail = await client.get(f"/api/jobs/{job.id}", headers=auth_headers)
        assert detail.json()["deadline"] == patched.json()["deadline"]

    async def test_an_explicit_null_clears_it(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user, deadline=utcnow() + timedelta(days=5))

        response = await client.patch(
            f"/api/jobs/{job.id}", headers=auth_headers, json={"deadline": None}
        )

        assert response.json()["deadline"] is None

    async def test_an_empty_body_changes_nothing(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        """Omission is not an edit: only a key that is present may overwrite."""
        job = await create_job(session, user, deadline=utcnow() + timedelta(days=5))

        response = await client.patch(f"/api/jobs/{job.id}", headers=auth_headers, json={})

        assert response.json()["deadline"] is not None

    async def test_another_users_job_is_not_found(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user: Any,
        other_auth_headers: dict[str, str],
    ) -> None:
        job = await create_job(session, user)

        response = await client.patch(
            f"/api/jobs/{job.id}", headers=other_auth_headers, json={"deadline": None}
        )

        assert response.status_code == 404


class TestStaleJobsAreNotPrepared:
    async def test_the_preview_excludes_and_warns_about_an_expired_job(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        fresh = await create_job(session, user, status=JobStatus.ANALYZED, score=90)
        gone = await create_job(
            session, user, status=JobStatus.ANALYZED, score=90, expired_at=utcnow()
        )

        body = (
            await client.post(
                "/api/automation/preview",
                headers=auth_headers,
                json={"job_ids": [fresh.id, gone.id], "confirmed": False},
            )
        ).json()

        assert [item["id"] for item in body["jobs"]] == [fresh.id]
        assert body["jobs_to_process"] == 1
        assert any("no longer" in warning for warning in body["warnings"])

    async def test_the_preview_warns_about_a_passed_deadline(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        late = await create_job(
            session,
            user,
            status=JobStatus.ANALYZED,
            score=90,
            deadline=utcnow() - timedelta(days=1),
        )

        body = (
            await client.post(
                "/api/automation/preview",
                headers=auth_headers,
                json={"job_ids": [late.id], "confirmed": False},
            )
        ).json()

        assert body["jobs_to_process"] == 0
        assert any("deadline" in warning for warning in body["warnings"])

    async def test_prepare_refuses_a_stale_job(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(
            session, user, status=JobStatus.ANALYZED, score=90, expired_at=utcnow()
        )

        response = await client.post(
            "/api/automation/prepare",
            headers=auth_headers,
            json={"job_ids": [job.id], "confirmed": True},
        )

        assert 400 <= response.status_code < 500, response.text
        assert await count_runs(session, user) == 0

    async def test_a_stale_job_is_flagged_on_read(
        self, client: AsyncClient, session: AsyncSession, user: Any, auth_headers: dict[str, str]
    ) -> None:
        job = await create_job(session, user, deadline=utcnow() - timedelta(hours=1))

        body = (await client.get(f"/api/jobs/{job.id}", headers=auth_headers)).json()

        assert body["is_stale"] is True


class TestExpireMissing:
    async def test_it_marks_the_job_and_takes_it_out_of_the_queue(
        self, session: AsyncSession, user: Any
    ) -> None:
        job = await create_job(session, user, status=JobStatus.ANALYZED, score=90)

        await job_service.expire_missing(session, user, job.id)

        assert job.expired_at is not None
        assert job.status == JobStatus.SKIPPED
        assert job_service.is_stale(job)

    async def test_a_second_sighting_does_not_move_the_timestamp(
        self, session: AsyncSession, user: Any
    ) -> None:
        job = await create_job(session, user, status=JobStatus.ANALYZED)

        first = await job_service.expire_missing(session, user, job.id)
        stamped = first.expired_at
        again = await job_service.expire_missing(session, user, job.id)

        assert again.expired_at == stamped

    async def test_an_applied_job_keeps_its_status(self, session: AsyncSession, user: Any) -> None:
        """Postings vanish after a successful application; that is not a skip."""
        job = await create_job(session, user, status=JobStatus.APPLIED)

        await job_service.expire_missing(session, user, job.id)

        assert job.expired_at is not None
        assert job.status == JobStatus.APPLIED
