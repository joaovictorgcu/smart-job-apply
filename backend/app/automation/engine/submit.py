"""The only path that sends anything to LinkedIn.

`_submit_application` is the single caller of `LinkedInService.submit()`. It
refuses unless, in this order: the application belongs to the user, it is
awaiting review, it was explicitly approved, dry run is off, and the throttle
allows it — working hours first, then the daily cap. Nothing else in the engine
may reach the submit button.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.automation.engine.base import EngineBase
from app.automation.errors import AutomationError
from app.database.base import utcnow
from app.database.session import session_scope
from app.models import Application, ApplicationEventType, ApplicationStatus, Job, JobStatus
from app.observability import get_logger, to_live_event
from app.websocket.manager import manager

logger = get_logger(__name__)


class SubmitMixin(EngineBase):
    """Owns the approved submit and the discard that ends a draft instead."""

    async def submit_application(self, user_id: int, application_id: int) -> bool:
        async with self._exclusive(user_id):
            return await self._submit_application(user_id, application_id)

    async def _submit_application(self, user_id: int, application_id: int) -> bool:
        throttle = await self._throttle(user_id)

        async with session_scope() as session:
            application = await session.scalar(
                select(Application)
                .options(selectinload(Application.job))
                .where(Application.id == application_id)
            )
            if application is None or application.user_id != user_id:
                raise AutomationError(f"Application {application_id} does not belong to this user.")
            if application.status != ApplicationStatus.AWAITING_REVIEW:
                raise AutomationError(
                    "Only an application awaiting review can be submitted "
                    # Status columns are plain strings on the way back from the DB.
                    f"(current status: {application.status})."
                )
            if application.approved_at is None:
                raise AutomationError(
                    "This application has not been approved. "
                    "Approve it explicitly before submitting."
                )
            settings = await self._settings(session, user_id)
            if application.was_dry_run or (settings is not None and settings.dry_run):
                raise AutomationError(
                    "Dry run is enabled: nothing is sent to LinkedIn. "
                    "Turn dry run off in settings to submit for real."
                )
            throttle.assert_within_working_hours()
            await throttle.assert_daily_cap(session, user_id)

            application.status = ApplicationStatus.SUBMITTING
            job = application.job
            job_id = job.id
            external_id = job.external_id
            job_title = job.title

        service = self._services.get(user_id)
        if service is None or not service.has_open_draft(external_id):
            exc = AutomationError(
                "The filled Easy Apply form is no longer open in the browser. "
                "Prepare this application again before submitting."
            )
            await self._revert_to_review(user_id, application_id, job_id, exc)
            raise exc

        try:
            confirmed = await service.submit()
        except Exception as exc:
            await self._fail_application(user_id, None, job_id, application_id, exc)
            raise

        async with session_scope() as session:
            application = await session.get(Application, application_id)
            if application is not None:
                application.status = ApplicationStatus.SUBMITTED
                application.submitted_at = utcnow()
                application.needs_human_input = False
                application.error_message = (
                    None
                    if confirmed
                    else "Submitted, but LinkedIn did not show a confirmation message."
                )
            job = await session.get(Job, job_id)
            if job is not None:
                job.status = JobStatus.APPLIED
            event = await self._record(
                session,
                user_id=user_id,
                application_id=application_id,
                job_id=job_id,
                event_type=ApplicationEventType.SUBMITTED,
                message=f"Application submitted for {job_title}.",
                payload={"confirmed": confirmed},
            )
            live = to_live_event(event, job_id=job_id)

        if live is not None:
            live.level = "success"
            await manager.publish(user_id, live)

        logger.info(
            "Application submitted after explicit user approval.",
            extra={
                "action": "engine.submit",
                "status": "ok",
                "user_id": user_id,
                "application_id": application_id,
                "job_id": job_id,
            },
        )
        # Long, randomized gap before anything else touches LinkedIn.
        await throttle.wait_between_applications()
        return confirmed

    async def _revert_to_review(
        self, user_id: int, application_id: int, job_id: int, exc: Exception
    ) -> None:
        """Undo the SUBMITTING transition when a precondition fails at the browser."""
        async with session_scope() as session:
            application = await session.get(Application, application_id)
            if application is not None:
                application.status = ApplicationStatus.AWAITING_REVIEW
                application.needs_human_input = True
                application.error_message = str(exc)
            await self._record(
                session,
                user_id=user_id,
                application_id=application_id,
                job_id=job_id,
                event_type=ApplicationEventType.ERROR,
                message=str(exc),
                is_error=True,
            )

    async def discard_application(self, user_id: int, application_id: int) -> None:
        """Close the open modal (if any) and mark the application as discarded."""
        async with self._exclusive(user_id):
            service = self._services.get(user_id)
            if service is not None and service.has_open_draft():
                await service.discard()
            async with session_scope() as session:
                application = await session.get(Application, application_id)
                if application is None or application.user_id != user_id:
                    raise AutomationError(
                        f"Application {application_id} does not belong to this user."
                    )
                application.status = ApplicationStatus.DISCARDED
                application.needs_human_input = False
                await self._record(
                    session,
                    user_id=user_id,
                    application_id=application_id,
                    job_id=application.job_id,
                    event_type=ApplicationEventType.DISCARDED,
                    message="Draft discarded by the user.",
                )
