"""Work a dead process left in flight, closed out at startup.

Every in-flight state in this app is backed by an asyncio task, not by a row:
`is_busy` asks the task registry. A process that has just started owns no
tasks, so anything still `RUNNING` or `SUBMITTING` belongs to a process that
died — and nothing will ever finish it.

The asymmetry between the two application states is what these tests are really
about. `PREPARING` never sent anything and goes back to `DRAFT`; `SUBMITTING`
has an unknown outcome and must not be handed back to the review screen, where
one click would re-send an application LinkedIn may already hold.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Application,
    ApplicationEvent,
    ApplicationEventType,
    ApplicationStatus,
    AutomationRun,
    AutomationRunKind,
    AutomationRunStatus,
)
from app.services import automation_service
from tests.fixtures.factories import create_application, create_job, create_run


async def _reload(session: AsyncSession, model: Any, row_id: int) -> Any:
    """Read a row back through a fresh identity map.

    Reconciliation commits in its own session, so the test's copy is stale by
    construction — expiring it is what makes the assertion about the database
    rather than about objects this test still holds. The id is taken as an
    argument rather than read off the stale instance: touching an expired
    attribute triggers a synchronous refresh, which is a `MissingGreenlet` on
    an async session.
    """
    session.expire_all()
    return await session.get(model, row_id)


class TestRuns:
    async def test_an_interrupted_run_is_stopped_and_explained(
        self, session: AsyncSession, user: Any
    ) -> None:
        run_id = (await create_run(session, user, status=AutomationRunStatus.RUNNING)).id

        counts = await automation_service.reconcile_interrupted_work()

        refreshed = await _reload(session, AutomationRun, run_id)
        assert counts["runs"] == 1
        assert refreshed.status == AutomationRunStatus.STOPPED
        assert refreshed.finished_at is not None
        assert "restarted" in (refreshed.error_message or "")

    async def test_it_stays_resumable(self, session: AsyncSession, user: Any) -> None:
        """STOPPED, not FAILED, and `stop_requested` untouched.

        A crash is not a kill switch: the checkpoint still holds the run's
        inputs, so the user should be able to pick it up rather than start over.
        """
        run = await create_run(
            session,
            user,
            kind=AutomationRunKind.PREPARE,
            status=AutomationRunStatus.RUNNING,
            # `_is_resumable` reads the inputs a resume would need, and they are
            # per kind: a prepare run resumes from its job ids.
            checkpoint={"job_ids": [1, 2, 3]},
        )
        run_id = run.id

        await automation_service.reconcile_interrupted_work()

        refreshed = await _reload(session, AutomationRun, run_id)
        assert refreshed.stop_requested is False
        assert automation_service._is_resumable(refreshed) is True

    async def test_every_active_status_is_closed(
        self, session: AsyncSession, user: Any
    ) -> None:
        pending = (await create_run(session, user, status=AutomationRunStatus.PENDING)).id
        paused = (await create_run(session, user, status=AutomationRunStatus.PAUSED)).id

        counts = await automation_service.reconcile_interrupted_work()

        assert counts["runs"] == 2
        for run_id in (pending, paused):
            row = await _reload(session, AutomationRun, run_id)
            assert row.status == AutomationRunStatus.STOPPED

    async def test_a_finished_run_is_left_alone(
        self, session: AsyncSession, user: Any
    ) -> None:
        completed = (await create_run(session, user, status=AutomationRunStatus.COMPLETED)).id
        blocked = (await create_run(session, user, status=AutomationRunStatus.BLOCKED)).id

        counts = await automation_service.reconcile_interrupted_work()

        assert counts["runs"] == 0
        done = await _reload(session, AutomationRun, completed)
        assert done.status == AutomationRunStatus.COMPLETED
        # A checkpoint is a decision waiting for a human, not interrupted work.
        halted = await _reload(session, AutomationRun, blocked)
        assert halted.status == AutomationRunStatus.BLOCKED


class TestApplications:
    async def test_a_half_prepared_draft_goes_back_to_draft(
        self, session: AsyncSession, user: Any
    ) -> None:
        job = await create_job(session, user)
        application_id = (
            await create_application(session, user, job, status=ApplicationStatus.PREPARING)
        ).id

        counts = await automation_service.reconcile_interrupted_work()

        refreshed = await _reload(session, Application, application_id)
        assert counts["preparing"] == 1
        # Nothing was sent, so preparing it again is safe and loses nothing.
        assert refreshed.status == ApplicationStatus.DRAFT

    async def test_an_interrupted_submission_never_returns_to_review(
        self, session: AsyncSession, user: Any
    ) -> None:
        """The guard that matters.

        `SUBMITTING` is written before the browser opens, so the outcome is
        genuinely unknown. Putting it back in front of the "approve & submit"
        button would offer a one-click re-send of something LinkedIn may already
        have — the unattended submission this product exists to prevent.
        """
        job = await create_job(session, user)
        application_id = (
            await create_application(session, user, job, status=ApplicationStatus.SUBMITTING)
        ).id

        counts = await automation_service.reconcile_interrupted_work()

        refreshed = await _reload(session, Application, application_id)
        assert counts["submitting"] == 1
        assert refreshed.status == ApplicationStatus.FAILED
        assert refreshed.status != ApplicationStatus.AWAITING_REVIEW
        assert "unknown" in (refreshed.error_message or "")

    async def test_an_interrupted_submission_is_written_to_the_trail(
        self, session: AsyncSession, user: Any
    ) -> None:
        """The detail screen reads events, not the error column."""
        job = await create_job(session, user)
        application = await create_application(
            session, user, job, status=ApplicationStatus.SUBMITTING
        )

        await automation_service.reconcile_interrupted_work()

        events = (
            (
                await session.execute(
                    select(ApplicationEvent).where(
                        ApplicationEvent.application_id == application.id,
                        ApplicationEvent.event_type == ApplicationEventType.ERROR,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].is_error is True

    async def test_a_settled_application_is_left_alone(
        self, session: AsyncSession, user: Any
    ) -> None:
        submitted = (
            await create_application(
                session, user, await create_job(session, user),
                status=ApplicationStatus.SUBMITTED,
            )
        ).id
        waiting = (
            await create_application(
                session, user, await create_job(session, user),
                status=ApplicationStatus.AWAITING_REVIEW,
            )
        ).id

        counts = await automation_service.reconcile_interrupted_work()

        assert counts["preparing"] == 0 and counts["submitting"] == 0
        sent = await _reload(session, Application, submitted)
        assert sent.status == ApplicationStatus.SUBMITTED
        assert (
            await _reload(session, Application, waiting)
        ).status == ApplicationStatus.AWAITING_REVIEW


class TestIdempotence:
    async def test_running_it_twice_changes_nothing_more(
        self, session: AsyncSession, user: Any
    ) -> None:
        """Restarting twice must not write a second event or a second message."""
        job = await create_job(session, user)
        application = await create_application(
            session, user, job, status=ApplicationStatus.SUBMITTING
        )
        await create_run(session, user, status=AutomationRunStatus.RUNNING)

        first = await automation_service.reconcile_interrupted_work()
        second = await automation_service.reconcile_interrupted_work()

        assert first == {"runs": 1, "preparing": 0, "submitting": 1}
        assert second == {"runs": 0, "preparing": 0, "submitting": 0}

        events = (
            (
                await session.execute(
                    select(ApplicationEvent).where(
                        ApplicationEvent.application_id == application.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1

    async def test_a_clean_database_is_untouched(self, session: AsyncSession) -> None:
        assert await automation_service.reconcile_interrupted_work() == {
            "runs": 0,
            "preparing": 0,
            "submitting": 0,
        }
        assert (await session.execute(select(AutomationRun))).scalars().all() == []
        assert (await session.execute(select(Application))).scalars().all() == []
