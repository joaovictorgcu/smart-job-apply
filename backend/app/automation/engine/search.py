"""The search run: discover postings, store them, score them.

One pass over the LinkedIn results for a `SearchFilters`, checkpointing after
every posting so a stop or a crash resumes where it left off. Scoring is
delegated to the AI layer, which owns the resulting `JobStatus`.
"""

from __future__ import annotations

from sqlalchemy import select

from app.automation.contracts import JobPosting, SearchFilters
from app.automation.engine.base import EngineBase
from app.automation.errors import SecurityCheckpointError, StopRequestedError
from app.automation.linkedin.search import PAGE_SIZE
from app.database.session import session_scope
from app.models import AutomationRun, AutomationRunStatus, Job, JobStatus, User
from app.observability import EventName, get_logger
from app.services.job_service import screen_by_preferences, upsert_job_from_posting

logger = get_logger(__name__)


class SearchMixin(EngineBase):
    """Owns one search run, from the first result page to the final counters."""

    async def run_search(
        self, user_id: int, run_id: int, filters: SearchFilters, *, analyze: bool = True
    ) -> None:
        async with self._exclusive(user_id):
            await self._run_search(user_id, run_id, filters, analyze=analyze)

    async def _run_search(
        self, user_id: int, run_id: int, filters: SearchFilters, *, analyze: bool
    ) -> None:
        counters = {"jobs_found": 0, "jobs_analyzed": 0, "jobs_skipped": 0}
        try:
            await self._start_run(run_id)
            await self._publish(
                user_id,
                EventName.AUTOMATION_STARTED,
                run_id=run_id,
                message=f'Searching LinkedIn for "{filters.keywords}".',
                data={"kind": "search", "analyze": analyze},
            )

            service = await self._ready_service(user_id)
            throttle = await self._throttle(user_id)
            checkpoint = await self._checkpoint(run_id)
            processed: set[str] = {str(value) for value in checkpoint.get("processed_ids") or []}
            search_id = await self._run_search_id(run_id)

            await self._check_stop(user_id, run_id)
            postings = await service.search_jobs(filters)
            counters["jobs_found"] = len(postings)
            await self._update_run(run_id, jobs_found=len(postings))

            for index, posting in enumerate(postings, start=1):
                await self._check_stop(user_id, run_id)
                if posting.external_id in processed:
                    continue

                job_id = await self._store_posting(user_id, search_id, posting)
                await self._publish(
                    user_id,
                    EventName.JOB_FOUND,
                    run_id=run_id,
                    job_id=job_id,
                    message=f"{posting.title} — {posting.company}",
                    data={"external_id": posting.external_id, "url": posting.url},
                )

                if not posting.description:
                    detail = await service.fetch_job_details(posting.external_id)
                    job_id = await self._store_posting(user_id, search_id, detail)

                if analyze:
                    outcome = await self._analyze_job(user_id, run_id, job_id)
                    if outcome is not None:
                        counters["jobs_analyzed"] += 1
                        if outcome == JobStatus.SKIPPED:
                            counters["jobs_skipped"] += 1

                processed.add(posting.external_id)
                # Merged over the stored checkpoint: the run's inputs (filters)
                # live in the same dict and must survive every progress write.
                await self._update_run(
                    run_id,
                    checkpoint={
                        **checkpoint,
                        "processed_ids": sorted(processed),
                        "page": (index - 1) // PAGE_SIZE,
                    },
                    **counters,
                )
                await self._publish(
                    user_id,
                    EventName.AUTOMATION_PROGRESS,
                    run_id=run_id,
                    job_id=job_id,
                    message=f"Processed {index} of {len(postings)} jobs.",
                    data={"processed": index, "total": len(postings), **counters},
                )
                await throttle.wait_action()

            await self._finish_run(run_id, AutomationRunStatus.COMPLETED, **counters)
            await self._publish(
                user_id,
                EventName.AUTOMATION_STOPPED,
                run_id=run_id,
                level="success",
                message=f"Search finished: {counters['jobs_found']} jobs found.",
                data=dict(counters),
            )
        except StopRequestedError as exc:
            await self._finish_run(run_id, AutomationRunStatus.STOPPED, error=str(exc), **counters)
            await self._publish(
                user_id,
                EventName.AUTOMATION_STOPPED,
                run_id=run_id,
                level="warning",
                message="Search stopped by the user.",
            )
        except SecurityCheckpointError as exc:
            await self._handle_checkpoint(user_id, run_id, exc, **counters)
        except Exception as exc:
            await self._fail_run(user_id, run_id, exc, **counters)
            raise

    async def _run_search_id(self, run_id: int) -> int | None:
        async with session_scope() as session:
            return await session.scalar(
                select(AutomationRun.search_id).where(AutomationRun.id == run_id)
            )

    @staticmethod
    async def _store_posting(user_id: int, search_id: int | None, posting: JobPosting) -> int:
        """Ingest a discovered posting through the one shared dedup rule."""
        async with session_scope() as session:
            job, _ = await upsert_job_from_posting(session, user_id, posting, search_id=search_id)
            return job.id

    async def _analyze_job(self, user_id: int, run_id: int | None, job_id: int) -> JobStatus | None:
        """Score one job with the AI layer. Returns the resulting job status.

        The AI layer owns the outcome: it writes the score, the breakdown, the
        gates and the resulting status. This method only reports what it wrote —
        a second threshold here would be a second definition of "skipped".
        """
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None or job.user_id != user_id:
                return None
            user = await session.get(User, user_id)
            if user is None:
                logger.warning(
                    "Cannot score a job for a user that no longer exists.",
                    extra={"action": "engine.analyze", "user_id": user_id, "job_id": job_id},
                )
                return None

            # A posting the user already ruled out is dropped here rather than
            # paid for: scoring is the expensive step, and the reason quotes
            # their own term instead of a number they would have to interpret.
            verdict = await screen_by_preferences(session, user_id, job)
            if not verdict.excluded:
                settings = await self._settings(session, user_id)
                profile = await self._profile_context(session, user_id)
                await self._ai.analyze_job(
                    session, user=user, job=job, profile_ctx=profile, settings_row=settings
                )

            resulting = job.status
            score = job.score
            title = job.title

        # Published after the session closes, so a dashboard that refetches on
        # the event reads the committed row rather than racing the write.
        if verdict.excluded:
            await self._publish(
                user_id,
                EventName.JOB_ANALYZED,
                run_id=run_id,
                job_id=job_id,
                message=f"{title}: {verdict.reason}",
                level="info",
                data={"skipped": True, "matched_term": verdict.matched_term},
            )
            return resulting

        await self._publish(
            user_id,
            EventName.JOB_ANALYZED,
            run_id=run_id,
            job_id=job_id,
            message=f"{title}: score {score}.",
            level="info" if resulting == JobStatus.ANALYZED else "warning",
            data={"score": score, "status": str(resulting)},
        )
        return resulting
