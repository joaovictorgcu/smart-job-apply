"""The prepare run: fill the Easy Apply form and stop at the review step.

This is where assisted mode is enforced. A prepared application always lands in
`AWAITING_REVIEW` with everything the reviewer needs — the answers, their
confidence, what the form left blank — and never touches the submit button. In
dry-run mode the real modal is not opened at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.ai.schemas import ScreeningAnswer
from app.automation.contracts import ApplicationDraft, FormQuestion, ProfileContext
from app.automation.engine.answers import _build_answers, _merge_draft_answers
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
            application_id = application.id
            resume_filename = profile.resume_path
            cover_letter_existing = application.cover_letter

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

            if dry_run:
                await self._store_draft(
                    user_id=user_id,
                    run_id=run_id,
                    job_id=job_id,
                    application_id=application_id,
                    draft=None,
                    cover_letter=cover_letter,
                    screening=[],
                    resume_filename=resume_filename,
                    dry_run=True,
                )
                return application_id

            if not easy_apply:
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
            answers, enriched = _build_answers(questions, screening, profile)
            draft = await service.fill_and_advance(answers, cover_letter=cover_letter)
            enriched = _merge_draft_answers(enriched, draft)

            await self._store_draft(
                user_id=user_id,
                run_id=run_id,
                job_id=job_id,
                application_id=application_id,
                draft=draft,
                cover_letter=cover_letter,
                screening=enriched,
                resume_filename=resume_filename,
                dry_run=False,
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
        draft: ApplicationDraft | None,
        cover_letter: str | None,
        screening: list[dict[str, Any]],
        resume_filename: str | None,
        dry_run: bool,
    ) -> None:
        """Persist the filled draft and park it in AWAITING_REVIEW."""
        unanswered = [question.label for question in (draft.unanswered if draft else [])]
        low_confidence = [
            entry["question"]
            for entry in screening
            if entry.get("needs_review") or entry.get("confidence") == AnswerConfidence.LOW.value
        ]
        needs_human = bool(unanswered or low_confidence) or (
            draft is not None and not draft.ready_to_submit
        )

        async with session_scope() as session:
            application = await session.get(Application, application_id)
            if application is None:
                return
            application.cover_letter = cover_letter
            application.screening_answers = screening
            application.resume_filename = (
                Path(resume_filename).name if resume_filename else application.resume_filename
            )
            application.total_steps = draft.total_steps if draft else None
            application.current_step = draft.current_step if draft else None
            application.needs_human_input = needs_human
            application.was_dry_run = dry_run
            application.status = ApplicationStatus.AWAITING_REVIEW

            job = await session.get(Job, job_id)
            if job is not None and job.status not in {JobStatus.APPLIED, JobStatus.SKIPPED}:
                job.status = JobStatus.QUEUED

            message = (
                "Dry run: content generated without opening the LinkedIn form."
                if dry_run
                else "Form filled and stopped at the review step. Waiting for your approval."
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
                    "unanswered": unanswered,
                    "needs_review": low_confidence,
                    "ready_to_submit": bool(draft.ready_to_submit) if draft else False,
                    "screenshot": draft.screenshot_path if draft else None,
                    "notes": list(draft.notes) if draft else [],
                    "total_steps": draft.total_steps if draft else None,
                    "current_step": draft.current_step if draft else None,
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
