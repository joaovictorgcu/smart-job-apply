"""The prepare run: read the Easy Apply form, draft the answers, close it again.

This is where assisted mode is enforced. A prepared application always lands in
`AWAITING_REVIEW` with everything the reviewer needs — the answers, their
confidence, what was left blank — and never touches the submit button. In
dry-run mode the real modal is not opened at all.

Preparing is an *inspection* pass: it opens the form to see what it asks, drafts
the answers, records a fingerprint of the form's shape, and closes it. Nothing
is typed in and nothing is left open, because a browser tab is the wrong place
to keep a draft the user may only look at tomorrow — and because the service
holds exactly one open modal, so leaving it open meant only the last job of a
batch was ever really submittable. `SubmitMixin` re-opens, fills and sends in
one uninterrupted sequence once the human has approved.

A job on the EXTERNAL channel — a portal posting, or any job without an Easy
Apply button — has no form on this side at all, so preparing it is content only:
the letter is drafted and the draft waits for the user to apply on the company's
own page and record it. The channel is read off the job, never asked for.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.ai.schemas import ScreeningAnswer
from app.automation.contracts import FormQuestion, ProfileContext
from app.automation.engine.answers import _build_answers, _form_fingerprint
from app.automation.engine.base import EngineBase
from app.automation.errors import (
    AutomationError,
    EasyApplyUnavailableError,
    SecurityCheckpointError,
    StopRequestedError,
)
from app.database.session import session_scope
from app.models import (
    AnswerConfidence,
    Application,
    ApplicationChannel,
    ApplicationEventType,
    ApplicationStatus,
    AutomationRunStatus,
    Job,
    JobStatus,
    User,
)
from app.observability import EventName, get_logger, to_live_event
from app.websocket.manager import manager

logger = get_logger(__name__)


class PrepareMixin(EngineBase):
    """Owns everything between a scored job and a draft awaiting human review."""

    async def prepare_application(self, user_id: int, run_id: int, job_id: int) -> int | None:
        async with self._exclusive(user_id):
            return await self._prepare_application(user_id, run_id, job_id)

    async def prepare_applications(
        self, user_id: int, run_id: int, job_ids: Sequence[int]
    ) -> list[int]:
        """Prepare several drafts in one run, stopping cleanly on request."""
        prepared: list[int] = []
        try:
            await self._start_run(run_id)
            await self._publish(
                user_id,
                EventName.AUTOMATION_STARTED,
                run_id=run_id,
                message=f"Preparing {len(job_ids)} application(s) for review.",
                data={"kind": "prepare", "job_ids": list(job_ids)},
            )
            throttle = await self._throttle(user_id)
            checkpoint = await self._checkpoint(run_id)
            # Resuming this run must not touch a job it already handled.
            processed: set[int] = {int(value) for value in checkpoint.get("processed_ids") or []}

            async with self._exclusive(user_id):
                for index, job_id in enumerate(job_ids, start=1):
                    await self._check_stop(user_id, run_id)
                    if job_id in processed:
                        continue
                    try:
                        application_id = await self._prepare_application(user_id, run_id, job_id)
                    except (StopRequestedError, SecurityCheckpointError):
                        raise
                    except AutomationError as exc:
                        logger.warning(
                            "Could not prepare an application.",
                            extra={
                                "action": "engine.prepare",
                                "status": "failed",
                                "user_id": user_id,
                                "job_id": job_id,
                                "error": str(exc),
                            },
                        )
                        continue
                    if application_id is not None:
                        prepared.append(application_id)
                    processed.add(job_id)
                    # Merged so the run's `job_ids` input survives progress writes.
                    await self._update_run(
                        run_id,
                        applications_prepared=len(prepared),
                        checkpoint={**checkpoint, "processed_ids": sorted(processed)},
                    )
                    await self._publish(
                        user_id,
                        EventName.AUTOMATION_PROGRESS,
                        run_id=run_id,
                        job_id=job_id,
                        application_id=application_id,
                        message=f"Prepared {index} of {len(job_ids)} application(s).",
                        data={"processed": index, "total": len(job_ids)},
                    )
                    await throttle.wait_action()

            await self._finish_run(
                run_id, AutomationRunStatus.COMPLETED, applications_prepared=len(prepared)
            )
            await self._publish(
                user_id,
                EventName.AUTOMATION_STOPPED,
                run_id=run_id,
                level="success",
                message=f"{len(prepared)} application(s) are waiting for your review.",
                data={"applications_prepared": len(prepared)},
            )
        except StopRequestedError as exc:
            await self._finish_run(
                run_id,
                AutomationRunStatus.STOPPED,
                error=str(exc),
                applications_prepared=len(prepared),
            )
            await self._publish(
                user_id,
                EventName.AUTOMATION_STOPPED,
                run_id=run_id,
                level="warning",
                message="Preparation stopped by the user.",
            )
        except SecurityCheckpointError as exc:
            await self._handle_checkpoint(user_id, run_id, exc, applications_prepared=len(prepared))
        except Exception as exc:
            await self._fail_run(user_id, run_id, exc, applications_prepared=len(prepared))
            raise
        return prepared

    async def _prepare_application(
        self, user_id: int, run_id: int | None, job_id: int
    ) -> int | None:
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None or job.user_id != user_id:
                raise AutomationError(f"Job {job_id} does not belong to this user.")
            settings = await self._settings(session, user_id)
            profile = await self._profile_context(session, user_id)
            dry_run = bool(settings.dry_run) if settings else True
            external_id = job.external_id
            job_title = job.title
            job_company = job.company
            easy_apply = job.easy_apply
            # Read off the posting, not off the request: the app already knows
            # whether there is a form here it can drive.
            channel = ApplicationChannel.for_job(source=job.source, easy_apply=job.easy_apply)

            application = await session.scalar(
                select(Application).where(Application.job_id == job_id)
            )
            if application is None:
                application = Application(
                    user_id=user_id, job_id=job_id, status=ApplicationStatus.PREPARING
                )
                session.add(application)
                await session.flush()
            elif application.status in {
                ApplicationStatus.SUBMITTED,
                ApplicationStatus.SUBMITTING,
            }:
                raise AutomationError(
                    f"Application {application.id} was already submitted; nothing to prepare."
                )
            application.status = ApplicationStatus.PREPARING
            application.error_message = None
            application.was_dry_run = dry_run
            application.channel = channel
            application_id = application.id
            resume_filename = profile.resume_path
            cover_letter_existing = application.cover_letter
            # The application carries its own copy of the resume, adapted to this
            # posting and pinned to the master resume as it stands now — the same
            # rule the API path follows, because a draft prepared by the engine and
            # one created by hand must present the same document. Idempotent, so
            # re-preparing a draft keeps the copy the user may already have edited.
            #
            # Imported here, not at module scope: `resume_service` raises the API
            # layer's errors, and `app.api.errors` imports `app.automation` for
            # its exception mapping — so the module-level edge closes a cycle that
            # only shows up as an ImportError at startup.
            from app.services import resume_service

            await resume_service.ensure_application_resume(session, user_id, application_id)

        await self._publish(
            user_id,
            EventName.APPLICATION_STARTED,
            run_id=run_id,
            job_id=job_id,
            application_id=application_id,
            message=f"Preparing an application for {job_title} at {job_company}.",
            data={"dry_run": dry_run},
        )

        try:
            cover_letter = cover_letter_existing
            if not cover_letter:
                # Whether a letter is wanted at all is the AI layer's call: it
                # reads `generate_cover_letter` from the same settings row.
                cover_letter = await self._ai_cover_letter(user_id, job_id, profile)

            if channel is ApplicationChannel.EXTERNAL:
                # There is no form on this side to inspect: the posting is applied
                # to on the company's own page. So preparing is content only —
                # the letter (and the tailored CV, drafted elsewhere) are what the
                # user carries over there by hand.
                #
                # Kept as its own branch rather than folded into the dry-run one
                # below. They do the same work today, but they answer different
                # questions: dry run is a setting the user can switch off, while
                # this is a permanent property of the posting. Merging them would
                # make turning dry run off look like it enabled something here.
                await self._store_draft(
                    user_id=user_id,
                    run_id=run_id,
                    job_id=job_id,
                    application_id=application_id,
                    cover_letter=cover_letter,
                    screening=[],
                    resume_filename=resume_filename,
                    dry_run=dry_run,
                    channel=channel,
                )
                return application_id

            if dry_run:
                await self._store_draft(
                    user_id=user_id,
                    run_id=run_id,
                    job_id=job_id,
                    application_id=application_id,
                    cover_letter=cover_letter,
                    screening=[],
                    resume_filename=resume_filename,
                    dry_run=True,
                )
                return application_id

            if not easy_apply:
                # Unreachable while `for_job` sends every non-Easy-Apply posting
                # down the external branch, and kept anyway: this is the engine's
                # own last word on never opening a form that is not there.
                raise EasyApplyUnavailableError(
                    f"Job {external_id} does not offer Easy Apply; apply manually on LinkedIn."
                )

            service = await self._ready_service(user_id)
            questions = await service.open_easy_apply(external_id)
            async with session_scope() as session:
                await self._record(
                    session,
                    user_id=user_id,
                    application_id=application_id,
                    job_id=job_id,
                    run_id=run_id,
                    event_type=ApplicationEventType.FORM_OPENED,
                    message=f"Easy Apply form opened with {len(questions)} field(s).",
                    payload={"fields": [question.label for question in questions]},
                )

            screening = await self._ai_screening(user_id, job_id, profile, questions)
            # Only the records are kept. The values to type are rebuilt at submit
            # time from the records as the user left them, which is the whole
            # point of the review step.
            _, enriched = _build_answers(questions, screening, profile)

            # Nothing stays open: the draft lives in the database from here on.
            await service.discard()

            await self._store_draft(
                user_id=user_id,
                run_id=run_id,
                job_id=job_id,
                application_id=application_id,
                cover_letter=cover_letter,
                screening=enriched,
                resume_filename=resume_filename,
                dry_run=False,
                fingerprint=_form_fingerprint(questions),
            )
            return application_id

        except StopRequestedError:
            # The kill switch is not a failure; the run records the stop.
            raise
        except Exception as exc:
            await self._fail_application(user_id, run_id, job_id, application_id, exc)
            raise

    async def _store_draft(
        self,
        *,
        user_id: int,
        run_id: int | None,
        job_id: int,
        application_id: int,
        cover_letter: str | None,
        screening: list[dict[str, Any]],
        resume_filename: str | None,
        dry_run: bool,
        fingerprint: str | None = None,
        channel: ApplicationChannel = ApplicationChannel.EASY_APPLY,
    ) -> None:
        """Persist the drafted content and park the application in AWAITING_REVIEW.

        There is no browser draft to interrogate any more, so whether a human is
        needed is decided from the answers themselves: a required question left
        empty, an answer the model was unsure of, or one it flagged for review.
        `_build_answers` already marks required-with-no-value as needing review;
        `unanswered` names those separately, because "the form demands this and we
        have nothing" is a different conversation from "check this wording".
        """
        unanswered = [
            entry["question"]
            for entry in screening
            if entry.get("required") and not str(entry.get("answer") or "").strip()
        ]
        low_confidence = [
            entry["question"]
            for entry in screening
            if entry.get("needs_review") or entry.get("confidence") == AnswerConfidence.LOW.value
        ]
        needs_human = bool(unanswered or low_confidence)

        async with session_scope() as session:
            application = await session.get(Application, application_id)
            if application is None:
                return
            application.cover_letter = cover_letter
            application.screening_answers = screening
            application.resume_filename = (
                Path(resume_filename).name if resume_filename else application.resume_filename
            )
            # Both are only knowable once the form is walked, which now happens at
            # submit time; a stale count from an earlier attempt would be a lie.
            application.total_steps = None
            application.current_step = None
            # Always written, including the None of a dry run: a fingerprint left
            # over from an earlier live prepare would authorize submitting content
            # that was reviewed against a different form.
            application.form_fingerprint = fingerprint
            application.needs_human_input = needs_human
            application.was_dry_run = dry_run
            application.status = ApplicationStatus.AWAITING_REVIEW

            job = await session.get(Job, job_id)
            if job is not None and job.status not in {JobStatus.APPLIED, JobStatus.SKIPPED}:
                job.status = JobStatus.QUEUED

            if channel is ApplicationChannel.EXTERNAL:
                message = (
                    "Content prepared for a posting that is applied to on the company's "
                    "own site. Nothing is sent from here — apply there, then record it."
                )
            elif dry_run:
                message = "Dry run: content generated without opening the LinkedIn form."
            else:
                message = (
                    "Form inspected and closed. The answers are saved here and are "
                    "typed into LinkedIn only when you approve the submission."
                )
            event = await self._record(
                session,
                user_id=user_id,
                application_id=application_id,
                job_id=job_id,
                run_id=run_id,
                event_type=ApplicationEventType.AWAITING_REVIEW,
                message=message,
                payload={
                    "dry_run": dry_run,
                    "channel": channel.value,
                    "unanswered": unanswered,
                    "needs_review": low_confidence,
                    # Nothing is filled in yet, so nothing is ready to send, and
                    # no step counter or review screenshot exists to report.
                    "ready_to_submit": False,
                    "screenshot": None,
                    "notes": [],
                    "total_steps": None,
                    "current_step": None,
                    "form_fingerprint": fingerprint,
                },
            )
            live = to_live_event(event, job_id=job_id, needs_human_input=needs_human)

        if live is not None:
            await manager.publish(user_id, live)

    async def _fail_application(
        self,
        user_id: int,
        run_id: int | None,
        job_id: int,
        application_id: int,
        exc: Exception,
    ) -> None:
        async with session_scope() as session:
            application = await session.get(Application, application_id)
            if application is not None:
                application.status = ApplicationStatus.FAILED
                application.error_message = str(exc)
            await self._record(
                session,
                user_id=user_id,
                application_id=application_id,
                job_id=job_id,
                run_id=run_id,
                event_type=ApplicationEventType.ERROR,
                message=str(exc),
                is_error=True,
                payload={"error_type": type(exc).__name__},
            )
        await self._publish(
            user_id,
            EventName.AUTOMATION_ERROR,
            run_id=run_id,
            job_id=job_id,
            application_id=application_id,
            level="error",
            message=str(exc),
            data={"error_type": type(exc).__name__},
        )

    # --- AI layer calls ---------------------------------------------------
    #
    # Nothing is caught around these two calls. `app.ai.scoring` already
    # degrades internally — an API error or a refusal becomes an `AIAnalysis` row
    # with an error message and a refused result — and it deliberately re-raises
    # `AINotConfiguredError`, which the API layer renders as 503. A catch here
    # would only hide the next signature mismatch, which is what broke this seam.

    async def _ai_cover_letter(
        self, user_id: int, job_id: int, profile: ProfileContext
    ) -> str | None:
        """Draft a letter, in a scope holding the ORM `Job` the audit row needs."""
        async with session_scope() as session:
            user = await session.get(User, user_id)
            job = await session.get(Job, job_id)
            if user is None or job is None:
                return None
            settings = await self._settings(session, user_id)
            letter = await self._ai.generate_cover_letter(
                session, user=user, job=job, profile_ctx=profile, settings_row=settings
            )
        return letter.content if letter is not None else None

    async def _ai_screening(
        self, user_id: int, job_id: int, profile: ProfileContext, questions: list[FormQuestion]
    ) -> list[ScreeningAnswer]:
        """Answer the form's questions, in a scope holding the ORM `Job`."""
        async with session_scope() as session:
            user = await session.get(User, user_id)
            job = await session.get(Job, job_id)
            if user is None or job is None:
                return []
            return await self._ai.answer_screening(
                session, user=user, job=job, profile_ctx=profile, questions=questions
            )
