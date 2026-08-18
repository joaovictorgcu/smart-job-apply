"""The only path that sends anything to LinkedIn.

`_submit_application` is the single caller of `LinkedInService.submit()`. It
refuses unless, in this order: the application belongs to the user, it is
awaiting review, it was explicitly approved, dry run is off, and the throttle
allows it — working hours first, then the daily cap. Nothing else in the engine
may reach the submit button.

Only once all of that passes does it touch the browser, and then it opens, fills
and sends in one uninterrupted sequence. Preparing left nothing open on purpose,
so the form has to be re-opened here — and re-opening is what makes the last
check possible: the freshly read form is fingerprinted and compared against the
fingerprint recorded when the user reviewed it. A posting that changed its
questions in between means the human approved a different document than the one
about to be sent, and this refuses rather than sending it. The values typed in
come only from the stored, approved records: nothing is re-drafted, re-inferred
or asked of the model here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.automation.engine.answers import (
    _approved_answers,
    _describe_form_change,
    _form_fingerprint,
)
from app.automation.engine.base import EngineBase
from app.automation.errors import AutomationError
from app.database.base import utcnow
from app.database.session import session_scope
from app.models import Application, ApplicationEventType, ApplicationStatus, Job, JobStatus
from app.observability import get_logger, to_live_event
from app.websocket.manager import manager

if TYPE_CHECKING:
    from app.automation.contracts import ApplicationDraft, FormQuestion

logger = get_logger(__name__)


class _RefusedAtReview(AutomationError):
    """A refusal that has already put the application back in AWAITING_REVIEW.

    It travels out through the same `except` that turns a browser failure into a
    FAILED application, so it must be re-raised untouched: this is not a broken
    application, it is one whose form no longer matches what a human approved,
    and it belongs back on the review screen with the reason attached.
    """


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
            # Everything the browser sequence needs, read while the row is loaded:
            # what to type, and the form it was approved against.
            approved = list(application.screening_answers or [])
            reviewed_fingerprint = application.form_fingerprint
            cover_letter = application.cover_letter
            job = application.job
            job_id = job.id
            external_id = job.external_id
            job_title = job.title

        try:
            # The browser is usually closed by now — the review happens in the
            # user's own time. Opening it here is deliberate and visible.
            service = await self._ready_service(user_id)
            questions = await service.open_easy_apply(external_id)

            fingerprint = _form_fingerprint(questions)
            if fingerprint != reviewed_fingerprint:
                await service.discard()
                await self._refuse_changed_form(
                    user_id,
                    application_id,
                    job_id,
                    questions=questions,
                    approved=approved,
                    reviewed_fingerprint=reviewed_fingerprint,
                    fingerprint=fingerprint,
                )

            draft = await service.fill_and_advance(
                _approved_answers(questions, approved), cover_letter=cover_letter
            )
            if not draft.ready_to_submit:
                await service.discard()
                await self._refuse_unready_form(user_id, application_id, job_id, draft)

            confirmed = await service.submit()
        except _RefusedAtReview:
            raise
        except Exception as exc:
            await self._fail_application(user_id, None, job_id, application_id, exc)
            raise

        async with session_scope() as session:
            application = await session.get(Application, application_id)
            if application is not None:
                application.status = ApplicationStatus.SUBMITTED
                application.submitted_at = utcnow()
                application.needs_human_input = False
                # Known only now: the form was walked a moment ago, not at review.
                application.total_steps = draft.total_steps
                application.current_step = draft.current_step
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

    async def _refuse_changed_form(
        self,
        user_id: int,
        application_id: int,
        job_id: int,
        *,
        questions: list[FormQuestion],
        approved: list[dict[str, Any]],
        reviewed_fingerprint: str | None,
        fingerprint: str,
    ) -> NoReturn:
        """Refuse a form that is not the one the user reviewed, and say why."""
        if reviewed_fingerprint is None:
            message = (
                "There is no record of the Easy Apply form this application was "
                "reviewed against, so what was approved cannot be verified. Nothing "
                "was submitted — prepare this application again."
            )
        else:
            message = (
                "The Easy Apply form changed after this application was reviewed "
                f"({_describe_form_change(questions, approved)}). Nothing was "
                "submitted — prepare it again and review the new form."
            )
        exc = _RefusedAtReview(message)
        await self._revert_to_review(
            user_id,
            application_id,
            job_id,
            exc,
            event_type=ApplicationEventType.FORM_CHANGED,
            payload={
                "reviewed_fingerprint": reviewed_fingerprint,
                "current_fingerprint": fingerprint,
                "current_fields": [question.label for question in questions],
            },
        )
        logger.warning(
            "Submission refused: the form no longer matches the reviewed one.",
            extra={
                "action": "engine.submit",
                "status": "form_changed",
                "user_id": user_id,
                "application_id": application_id,
                "job_id": job_id,
            },
        )
        raise exc

    async def _refuse_unready_form(
        self, user_id: int, application_id: int, job_id: int, draft: ApplicationDraft
    ) -> NoReturn:
        """Refuse a form that asked for something the approved content cannot answer."""
        missing = [question.label for question in draft.unanswered]
        detail = f" It still needs: {', '.join(missing)}." if missing else ""
        exc = _RefusedAtReview(
            "The Easy Apply form did not reach its review step with the answers you "
            f"approved.{detail} Nothing was submitted."
        )
        await self._revert_to_review(
            user_id,
            application_id,
            job_id,
            exc,
            payload={"unanswered": missing, "notes": list(draft.notes)},
        )
        raise exc

    async def _revert_to_review(
        self,
        user_id: int,
        application_id: int,
        job_id: int,
        exc: Exception,
        *,
        event_type: ApplicationEventType = ApplicationEventType.ERROR,
        payload: dict[str, Any] | None = None,
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
                event_type=event_type,
                message=str(exc),
                is_error=True,
                payload=payload,
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
