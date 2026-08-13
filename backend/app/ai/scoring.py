"""AI orchestration that touches the database.

Each function takes an `AsyncSession`, records what the model did in `AIAnalysis`
for audit and cost tracking, and updates the job when relevant. The caller owns
the transaction: these functions `flush()` and never `commit()`.

An AI failure is always degraded into "needs manual review" — it never propagates
far enough to abort an automation run. The one exception is
`AINotConfiguredError`, which is a configuration problem the API layer reports to
the user directly.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import (
    AIClient,
    AINotConfiguredError,
    detect_language,
    estimate_cost_usd,
    get_ai_client,
)
from app.ai.schemas import AIUsage, CoverLetter, JobAnalysis, ScreeningAnswer, TailoredResume
from app.automation.contracts import FormQuestion, ProfileContext
from app.models.enums import AnalysisKind, AnswerConfidence, JobStatus
from app.models.job import AIAnalysis
from app.observability import get_logger

logger = get_logger(__name__)

# An answer-bank key must be at least this long before it is allowed to match a
# question label by containment; shorter keys ("id", "cpf") produce false hits.
_MIN_CONTAINMENT_KEY_LENGTH = 5

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize(text: str) -> str:
    """Fold to lowercase, strip accents, and collapse punctuation to spaces."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NON_ALNUM.sub(" ", stripped).strip()


def _persist_analysis(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int | None,
    kind: AnalysisKind,
    model: str,
    result: dict[str, Any],
    usage: AIUsage | None = None,
    error_message: str | None = None,
) -> AIAnalysis:
    """Append one row to the AI audit trail."""
    analysis = AIAnalysis(
        user_id=user_id,
        job_id=job_id,
        kind=kind,
        model=usage.model if usage else model,
        result=result,
        input_tokens=usage.input_tokens if usage else None,
        output_tokens=usage.output_tokens if usage else None,
        latency_ms=usage.latency_ms if usage else None,
        was_refusal=bool(usage and usage.refused),
        error_message=error_message,
        cost_usd=estimate_cost_usd(usage) if usage else None,
    )
    session.add(analysis)
    return analysis


async def analyze_job(
    session: AsyncSession,
    *,
    user: Any,
    job: Any,
    profile_ctx: ProfileContext,
    settings_row: Any,
    client: AIClient | None = None,
) -> JobAnalysis:
    """Score a job, persist the analysis, and update the job row.

    Sets the job to `ANALYZED`, or to `SKIPPED` with a `skip_reason` when the
    score is below `settings_row.min_score`. On a refusal or an API failure the
    job keeps its current status so it can be retried or triaged by hand.
    """
    ai = client or get_ai_client_for(settings_row)

    # Detected before scoring so the language is recorded even if the call fails.
    detected = detect_language(getattr(job, "description", None) or getattr(job, "title", None))
    job.detected_language = detected

    try:
        score, usage = await ai.score_job(profile_ctx, job)
    except AINotConfiguredError:
        raise
    except (anthropic.APIError, ValueError, RuntimeError) as exc:
        logger.error(
            "Job scoring failed for job_id=%s: %s",
            getattr(job, "id", None),
            exc,
            extra={"action": "ai.analyze_job.failed", "job_id": getattr(job, "id", None)},
        )
        _persist_analysis(
            session,
            user_id=user.id,
            job_id=getattr(job, "id", None),
            kind=AnalysisKind.SCORING,
            model=ai.model,
            result={},
            error_message=str(exc),
        )
        await session.flush()
        return JobAnalysis(
            refused=True,
            refusal_reason=f"Scoring failed: {exc}",
            cover_letter_language=detected,
        )

    _persist_analysis(
        session,
        user_id=user.id,
        job_id=getattr(job, "id", None),
        kind=AnalysisKind.SCORING,
        model=ai.model,
        result=score.model_dump(mode="json"),
        usage=usage,
    )

    if usage.refused:
        # No score was produced, so writing one would misrepresent the job as
        # analyzed (and a zero would silently skip it). Leave it for a human.
        await session.flush()
        return JobAnalysis(
            refused=True,
            refusal_reason=usage.refusal_category or "The model declined to score this job.",
            cover_letter_language=detected,
        )

    job.score = score.score
    job.score_reasons = list(score.reasons)
    job.missing_requirements = list(score.missing_requirements)
    job.score_breakdown = [dimension.model_dump(mode="json") for dimension in score.breakdown]
    job.score_gates = [gate.model_dump(mode="json") for gate in score.gates]

    failed_gate = next((gate for gate in score.gates if gate.status == "fail"), None)
    min_score = getattr(settings_row, "min_score", 0) or 0
    if failed_gate is not None:
        # A failed gate is decisive whatever the number says: skipping with the
        # posting's own wording beats surfacing a misleading "82" the user would
        # waste an application on.
        job.status = JobStatus.SKIPPED
        job.skip_reason = f"Gate {failed_gate.gate}: {failed_gate.evidence}"[:300]
    elif score.score < min_score:
        job.status = JobStatus.SKIPPED
        job.skip_reason = f"Score {score.score} is below the minimum of {min_score}."
    else:
        job.status = JobStatus.ANALYZED
        job.skip_reason = None

    await session.flush()

    return JobAnalysis(
        score=score.score,
        reasons=list(score.reasons),
        missing_requirements=list(score.missing_requirements),
        recommend_apply=score.recommend_apply,
        summary=score.summary,
        cover_letter_language=detected,
    )


async def generate_cover_letter(
    session: AsyncSession,
    *,
    user: Any,
    job: Any,
    profile_ctx: ProfileContext,
    settings_row: Any,
    client: AIClient | None = None,
) -> CoverLetter | None:
    """Write a cover letter when the user's settings ask for one.

    Returns `None` when generation is disabled, refused, or failed — the caller
    proceeds without a letter rather than blocking the application.
    """
    if not getattr(settings_row, "generate_cover_letter", False):
        return None

    ai = client or get_ai_client_for(settings_row)
    tone = getattr(settings_row, "cover_letter_tone", "professional") or "professional"
    language = getattr(settings_row, "content_language", "job") or "job"

    try:
        letter, usage = await ai.write_cover_letter(profile_ctx, job, tone=tone, language=language)
    except AINotConfiguredError:
        raise
    except (anthropic.APIError, ValueError, RuntimeError) as exc:
        logger.error(
            "Cover letter generation failed for job_id=%s: %s",
            getattr(job, "id", None),
            exc,
            extra={
                "action": "ai.cover_letter.failed",
                "job_id": getattr(job, "id", None),
            },
        )
        _persist_analysis(
            session,
            user_id=user.id,
            job_id=getattr(job, "id", None),
            kind=AnalysisKind.COVER_LETTER,
            model=ai.model,
            result={},
            error_message=str(exc),
        )
        await session.flush()
        return None

    _persist_analysis(
        session,
        user_id=user.id,
        job_id=getattr(job, "id", None),
        kind=AnalysisKind.COVER_LETTER,
        model=ai.model,
        result=letter.model_dump(mode="json"),
        usage=usage,
    )
    await session.flush()

    if usage.refused or not letter.content.strip():
        return None
    return letter


async def tailor_resume(
    session: AsyncSession,
    *,
    user: Any,
    job: Any,
    profile_ctx: ProfileContext,
    settings_row: Any,
    client: AIClient | None = None,
) -> TailoredResume | None:
    """Adapt the resume to one job, persisting the call for audit and cost.

    Returns `None` when the model refuses, fails, or returns nothing — the caller
    surfaces that as "generate again or edit by hand". The invention guard runs in
    the service layer, on the returned text.
    """
    ai = client or get_ai_client_for(settings_row)
    try:
        result, usage = await ai.tailor_resume(profile_ctx, job)
    except AINotConfiguredError:
        raise
    except (anthropic.APIError, ValueError, RuntimeError) as exc:
        logger.error(
            "Resume tailoring failed for job_id=%s: %s",
            getattr(job, "id", None),
            exc,
            extra={"action": "ai.tailor.failed", "job_id": getattr(job, "id", None)},
        )
        _persist_analysis(
            session,
            user_id=user.id,
            job_id=getattr(job, "id", None),
            kind=AnalysisKind.CV_TAILORING,
            model=ai.model,
            result={},
            error_message=str(exc),
        )
        await session.flush()
        return None

    _persist_analysis(
        session,
        user_id=user.id,
        job_id=getattr(job, "id", None),
        kind=AnalysisKind.CV_TAILORING,
        model=ai.model,
        result=result.model_dump(mode="json"),
        usage=usage,
    )
    await session.flush()

    if usage.refused or not result.tailored_markdown.strip():
        return None
    return result


async def answer_screening(
    session: AsyncSession,
    *,
    user: Any,
    job: Any,
    profile_ctx: ProfileContext,
    questions: list[FormQuestion],
    client: AIClient | None = None,
) -> list[ScreeningAnswer]:
    """Answer screening questions, preferring the profile's answer bank.

    Stored answers are used directly — no AI call, no cost, no risk of invention.
    Only the remaining questions reach the model. Answers come back in the same
    order as `questions`; anything unanswered is simply absent, and the caller
    surfaces it for human input.
    """
    if not questions:
        return []

    answers: dict[str, ScreeningAnswer] = {}
    remaining: list[FormQuestion] = []
    for question in questions:
        stored = _answer_from_bank(question, profile_ctx.answer_bank)
        if stored is not None:
            answers[question.field_id] = stored
        else:
            remaining.append(question)

    if remaining:
        ai = client or get_ai_client_for(None)
        try:
            drafted, usage = await ai.answer_questions(profile_ctx, job, remaining)
        except AINotConfiguredError:
            raise
        except (anthropic.APIError, ValueError, RuntimeError) as exc:
            logger.error(
                "Screening answers failed for job_id=%s: %s",
                getattr(job, "id", None),
                exc,
                extra={
                    "action": "ai.screening.failed",
                    "job_id": getattr(job, "id", None),
                },
            )
            _persist_analysis(
                session,
                user_id=user.id,
                job_id=getattr(job, "id", None),
                kind=AnalysisKind.SCREENING,
                model=ai.model,
                result={},
                error_message=str(exc),
            )
            await session.flush()
            drafted = []
        else:
            _persist_analysis(
                session,
                user_id=user.id,
                job_id=getattr(job, "id", None),
                kind=AnalysisKind.SCREENING,
                model=ai.model,
                result={"answers": [answer.model_dump(mode="json") for answer in drafted]},
                usage=usage,
            )
            await session.flush()

        for answer in drafted:
            if answer.field_id:
                answers[answer.field_id] = answer

    return [answers[q.field_id] for q in questions if q.field_id in answers]


def _answer_from_bank(
    question: FormQuestion, answer_bank: dict[str, Any]
) -> ScreeningAnswer | None:
    """Look a question up in the stored answer bank.

    An exact (normalized) label match is treated as high confidence; a
    containment match is medium. A value that a `select`/`radio` field does not
    offer is returned flagged for review rather than dropped, so the user sees
    that a stored answer exists but does not fit.
    """
    if not answer_bank:
        return None

    label = _normalize(question.label)
    if not label:
        return None

    normalized_bank = {
        _normalize(str(key)): (str(key), value)
        for key, value in answer_bank.items()
        if value is not None and str(value).strip()
    }

    match = normalized_bank.get(label)
    confidence = AnswerConfidence.HIGH
    if match is None:
        # Longest key first: a more specific stored key should win over a
        # shorter one that also happens to appear in the label.
        padded_label = f" {label} "
        for key_norm, entry in sorted(
            normalized_bank.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if len(key_norm) < _MIN_CONTAINMENT_KEY_LENGTH:
                continue
            if f" {key_norm} " in padded_label:
                match = entry
                confidence = AnswerConfidence.MEDIUM
                break
    if match is None:
        return None

    original_key, raw_value = match
    value = str(raw_value).strip()
    needs_review = False

    if question.options:
        exact = next((opt for opt in question.options if opt == value), None)
        if exact is None:
            folded = _normalize(value)
            recovered = next((opt for opt in question.options if _normalize(opt) == folded), None)
            if recovered is not None:
                value = recovered
            else:
                needs_review = True
                confidence = AnswerConfidence.LOW

    return ScreeningAnswer(
        question=question.label,
        answer=value,
        question_type=question.kind,
        confidence=confidence,
        needs_review=needs_review,
        reasoning=f"From the profile answer bank (key: {original_key}).",
        source="answer_bank",
        field_id=question.field_id,
    )


def get_ai_client_for(settings_row: Any) -> AIClient:
    """Build a client honoring the user's per-account model override."""
    return get_ai_client(getattr(settings_row, "ai_model", None) if settings_row else None)


__all__ = [
    "analyze_job",
    "answer_screening",
    "generate_cover_letter",
    "tailor_resume",
]
