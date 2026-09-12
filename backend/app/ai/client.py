"""The capability layer: one method per thing the app asks a model to do.

Provider specifics live in `app.ai.providers`; this module owns what does not
change when the model does — prompt selection, token budgets, retries, refusal
handling and token accounting. Callers get the provider-agnostic models from
`app.ai.schemas` plus an `AIUsage` describing the call.

Two invariants matter for the rest of the app:

* A refusal is a normal outcome, not an exception. A model can decline a request
  with HTTP 200 and `stop_reason == "refusal"`, and a local model can return
  something that does not validate; every method returns a usable fallback with
  `AIUsage.refused` set so the caller degrades to manual input instead of
  crashing.
* An AI failure must never abort an automation run. Transient errors are retried;
  anything that survives the retries is raised for the caller to record and move on.
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

from app.ai.prompts import JobLike
from app.ai.prompts.cover_letter import (
    COVER_LETTER_SYSTEM_PROMPT,
    build_cover_letter_prompt,
)
from app.ai.prompts.interview_prep import (
    INTERVIEW_PREP_SYSTEM_PROMPT,
    build_interview_prep_prompt,
)
from app.ai.prompts.review import REVIEW_SYSTEM_PROMPT, build_review_prompt
from app.ai.prompts.scoring import SCORING_SYSTEM_PROMPT, build_scoring_prompt
from app.ai.prompts.screening import SCREENING_SYSTEM_PROMPT, build_screening_prompt
from app.ai.prompts.tailoring import TAILORING_SYSTEM_PROMPT, build_tailoring_prompt
from app.ai.providers import (
    ChatProvider,
    ProviderError,
    ProviderNotConfiguredError,
    build_provider,
    describe_provider,
)
from app.ai.providers.base import ProviderTransientError
from app.ai.schemas import (
    AIUsage,
    CoverLetter,
    DraftReview,
    JobScore,
    ScreeningAnswer,
    ScreeningAnswerSet,
    TailoredResume,
)
from app.automation.contracts import FormQuestion, ProfileContext
from app.config import get_settings

# `detect_language` is re-exported: the heuristic is pure domain, but callers
# have always reached it through this module and still do.
from app.domain.language import detect_language, fold, squash
from app.domain.technologies import (
    flag_unsupported_skills as _flag_unsupported_skills,
)
from app.models.enums import AnswerConfidence
from app.observability import get_logger

logger = get_logger(__name__)

# Thinking is on by default on Claude Opus 5 and shares `max_tokens` with the
# response, so these leave headroom rather than sitting at the answer's own size.
SCORING_MAX_TOKENS = 8192
SCREENING_MAX_TOKENS = 8192
COVER_LETTER_MAX_TOKENS = 4096
# A whole resume plus the structured change list; generous so a long CV is not
# truncated mid-document (thinking shares this budget on Opus 5).
TAILORING_MAX_TOKENS = 12288
# Edits + four critique notes + a coverage table over every stated requirement.
REVIEW_MAX_TOKENS = 8192
# A ~600-word markdown pack; headroom for thinking on Opus 5.
INTERVIEW_PREP_MAX_TOKENS = 6144

# Cover letters and screening answers are low-volume and correctness-sensitive;
# only bulk scoring uses the cheaper effort from settings.
QUALITY_EFFORT = "high"

MAX_ATTEMPTS = 3
_BASE_RETRY_DELAY = 1.0
_MAX_RETRY_DELAY = 20.0

# List prices in USD per million tokens, for the audit trail only. An unknown
# model yields `None` rather than a wrong number.
_PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

# Models that cost nothing to call because nothing left the machine. A hosted
# free tier is deliberately NOT listed: it is free only up to a quota, and
# reporting 0.00 for it would be a wrong number rather than an unknown one.
_FREE_MODELS = frozenset({"stub-offline"})

_NUMERIC_ANSWER = re.compile(r"^-?\d+([.,]\d+)?$")


_AI_NOT_CONFIGURED = (
    "AI features are not configured. Add your own free provider key under "
    "Settings, or set AI_PROVIDER for the whole deployment (ollama runs locally "
    "and needs no key)."
)


class AINotConfiguredError(RuntimeError):
    """The selected AI provider cannot run, so AI features are unavailable."""

    def __init__(self, message: str = _AI_NOT_CONFIGURED) -> None:
        super().__init__(message)


# The invention guard lives in `app.domain.technologies` — the deterministic
# derivation and the resume comparison need the same guarantee, and two copies
# of it would drift. Re-exported here because this is where callers found it.
flag_unsupported_skills = _flag_unsupported_skills


def _is_retryable(error: Exception) -> bool:
    """Whether a second attempt could plausibly succeed.

    `ProviderTransientError` is the OpenAI-compatible providers' typed signal for
    timeouts, 5xx and rate limits. The Anthropic SDK raises its own exception
    types, so that judgement is delegated to the module that imports it.
    """
    if isinstance(error, ProviderTransientError):
        return True
    if isinstance(error, ProviderError):
        # Every other ProviderError is a configuration or contract problem;
        # retrying would just repeat it three times.
        return False
    from app.ai.providers.anthropic_provider import is_retryable as anthropic_retryable

    return anthropic_retryable(error)


def _is_provider_failure(error: Exception) -> bool:
    """Errors the retry loop owns, as opposed to bugs it should let through."""
    if isinstance(error, ProviderError):
        return True
    from app.ai.providers.anthropic_provider import is_provider_api_error

    return is_provider_api_error(error)


def _refusal_category(response: Any) -> str | None:
    """Read the refusal category, which is absent or null on most responses."""
    details = getattr(response, "stop_details", None)
    if details is None:
        return None
    return getattr(details, "category", None)


def _first_text(response: Any) -> str:
    for block in response.content or []:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


# Ties a capability's empty-fallback factory to what that capability returns.
_T = TypeVar("_T")


class AIClient:
    """The app's AI capabilities, over whichever provider is configured."""

    def __init__(
        self,
        *,
        model: str | None = None,
        provider: ChatProvider | None = None,
        credentials: Any | None = None,
    ) -> None:
        # `credentials` is anything shaped like `Settings` for the provider layer
        # — in practice an `app.ai.credentials.AICredentials`, which is how one
        # account's own key reaches the provider without a branch down here.
        # Typed loosely on purpose: importing that module would be a cycle, and
        # the provider layer already reads this object by attribute name only.
        self._settings = credentials if credentials is not None else get_settings()
        self._provider = provider
        self._model_override = model

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.ai_enabled)

    @property
    def model(self) -> str:
        """The model that will answer, without building the provider to ask."""
        if self._model_override:
            return self._model_override
        if self._provider is not None:
            return self._provider.model
        return describe_provider(self._settings).split("/", 1)[-1]

    @property
    def provider_name(self) -> str:
        return describe_provider(self._settings)

    @property
    def credentials_source(self) -> str:
        """"deployment" or "account" — whose key this client would spend."""
        return str(getattr(self._settings, "source", "deployment"))

    def _require_provider(self) -> ChatProvider:
        if self._provider is None:
            if not self.is_configured:
                # The credentials say why they are unusable when they know; a
                # bare `Settings` does not, and falls back to the generic text.
                raise AINotConfiguredError(
                    str(getattr(self._settings, "reason", "") or _AI_NOT_CONFIGURED)
                )
            try:
                self._provider = build_provider(self._settings)
            except ProviderNotConfiguredError as exc:
                raise AINotConfiguredError(str(exc)) from exc
        return self._provider

    async def probe(self) -> str:
        """One minimal call, to prove these credentials actually answer.

        Exists so a user who pastes a key finds out on the settings screen, not
        on the job that needed it. Deliberately tiny and unstructured: it is
        checking a credential and an endpoint, not a model's ability to follow a
        schema, and it should cost a rounding error of anyone's free quota.
        """
        response = await self._send(
            system="Reply with the single word OK.",
            user_prompt="OK",
            max_tokens=16,
            effort=None,
        )
        return _first_text(response).strip() or str(getattr(response, "model", "")) or "OK"

    async def aclose(self) -> None:
        """Release the provider's transport. Safe to call more than once."""
        if self._provider is not None:
            await self._provider.aclose()

    # --- transport -----------------------------------------------------------

    async def _send(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
        effort: str | None,
        output_format: type[Any] | None = None,
    ) -> Any:
        """One request, retried on transient failures.

        `output_format` asks for validated structured output; the provider
        decides how to obtain it and returns `parsed_output` either way.
        """
        provider = self._require_provider()
        model = self._model_override or provider.model

        last_error: Exception | None = None
        for attempt_number in range(1, MAX_ATTEMPTS + 1):
            try:
                return await provider.send(
                    system=system,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                    effort=effort,
                    output_format=output_format,
                )
            except ProviderNotConfiguredError as exc:
                # A credential the provider itself rejected. Translated here so
                # the whole of `scoring.py` keeps working unchanged: every entry
                # point there re-raises `AINotConfiguredError` and swallows the
                # rest into a refusal, which is right for a model that declined
                # and wrong for a key that will never work. This is what makes
                # an expired key reach the user as a 503 instead of a 200 with
                # yesterday's score on it.
                raise AINotConfiguredError(str(exc)) from exc
            except Exception as exc:
                if not _is_provider_failure(exc) or not _is_retryable(exc):
                    raise
                last_error = exc
                if attempt_number == MAX_ATTEMPTS:
                    break
                delay = min(
                    _BASE_RETRY_DELAY * (2 ** (attempt_number - 1)) + random.uniform(0, 0.5),
                    _MAX_RETRY_DELAY,
                )
                logger.warning(
                    "AI call failed (attempt %s/%s), retrying in %.1fs: %s",
                    attempt_number,
                    MAX_ATTEMPTS,
                    delay,
                    exc,
                    extra={
                        "action": "ai.retry",
                        "provider": getattr(provider, "name", "unknown"),
                        "model": model,
                        "attempt": attempt_number,
                        "max_attempts": MAX_ATTEMPTS,
                        "delay_seconds": round(delay, 2),
                        "detail": str(exc),
                    },
                )
                await asyncio.sleep(delay)

        assert last_error is not None  # only reachable after a retryable failure
        raise last_error

    def _usage(
        self,
        response: Any,
        *,
        started_at: float,
        refused: bool = False,
        refusal_category: str | None = None,
    ) -> AIUsage:
        usage = getattr(response, "usage", None)
        return AIUsage(
            model=getattr(response, "model", None) or self.model,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            refused=refused,
            refusal_category=refusal_category,
        )

    # --- refusal handling ----------------------------------------------------
    #
    # Every capability degrades the same way: a refusal or an unusable answer
    # becomes an empty value plus a refused `AIUsage`, never an exception. The
    # `action` and `refusal_category` strings are the audit trail — `app.ai.scoring`
    # surfaces the category to the user as the refusal reason — so they are passed
    # in verbatim rather than derived.

    def _parsed_or_fallback(
        self,
        response: Any,
        *,
        started_at: float,
        action: str,
        refusal_log: str,
        unparsed_log: str,
        fallback: Callable[[], _T],
        refusal_fallback: Callable[[], _T] | None = None,
        usable: Callable[[Any], bool] | None = None,
    ) -> tuple[_T, AIUsage]:
        """Validated structured output, or an empty fallback.

        `stop_reason` is checked before the content: on a refusal the parsed output
        is absent and reading it would mask the reason.

        `usable` is an extra check on a value the SDK did parse, for capabilities
        whose empty answer still validates. `refusal_fallback` overrides the empty
        value when declining and failing to answer deserve different wording.
        """
        if response.stop_reason == "refusal":
            category = _refusal_category(response)
            logger.warning(
                refusal_log,
                category,
                extra={"action": f"{action}.refused", "refusal_category": category},
            )
            return (refusal_fallback or fallback)(), self._usage(
                response, started_at=started_at, refused=True, refusal_category=category
            )

        parsed = response.parsed_output
        if parsed is None or (usable is not None and not usable(parsed)):
            logger.warning(
                unparsed_log,
                response.stop_reason,
                extra={"action": f"{action}.unparsed", "stop_reason": response.stop_reason},
            )
            return fallback(), self._usage(
                response,
                started_at=started_at,
                refused=True,
                refusal_category=f"unparsed_output:{response.stop_reason}",
            )

        return parsed, self._usage(response, started_at=started_at)

    def _text_or_fallback(
        self,
        response: Any,
        *,
        started_at: float,
        action: str,
        refusal_log: str,
        empty_log: str | None = None,
    ) -> tuple[str, AIUsage]:
        """Free-text output, or `""` when the model refused or wrote nothing.

        The caller wraps the text into whatever it returns; the empty fallback is
        the same wrapping around `""`. `empty_log` is optional because interview
        prep has never logged its empty case, and adding an action to the audit
        trail is not this seam's call to make.
        """
        if response.stop_reason == "refusal":
            category = _refusal_category(response)
            logger.warning(
                refusal_log,
                category,
                extra={"action": f"{action}.refused", "refusal_category": category},
            )
            return "", self._usage(
                response, started_at=started_at, refused=True, refusal_category=category
            )

        content = _first_text(response).strip()
        if not content:
            if empty_log is not None:
                logger.warning(
                    empty_log,
                    response.stop_reason,
                    extra={"action": f"{action}.empty", "stop_reason": response.stop_reason},
                )
            return "", self._usage(
                response,
                started_at=started_at,
                refused=True,
                refusal_category=f"empty_output:{response.stop_reason}",
            )

        return content, self._usage(response, started_at=started_at)

    # --- capabilities --------------------------------------------------------

    async def score_job(
        self,
        profile: ProfileContext,
        job: JobLike,
        *,
        effort: str | None = None,
    ) -> tuple[JobScore, AIUsage]:
        """Score a job against a profile.

        On refusal or unparseable output, returns a zero score with
        `AIUsage.refused` set so the caller falls back to manual review.
        """
        started_at = time.perf_counter()
        response = await self._send(
            system=SCORING_SYSTEM_PROMPT,
            user_prompt=build_scoring_prompt(profile, job),
            max_tokens=SCORING_MAX_TOKENS,
            effort=effort or self._settings.scoring_effort,
            output_format=JobScore,
        )

        return self._parsed_or_fallback(
            response,
            started_at=started_at,
            action="ai.score",
            refusal_log="Model declined to score the job (category=%s).",
            unparsed_log="Scoring response could not be parsed (stop_reason=%s).",
            fallback=lambda: JobScore(
                score=0,
                recommend_apply=False,
                summary="The model returned no usable score; review this job manually.",
            ),
            refusal_fallback=lambda: JobScore(
                score=0,
                recommend_apply=False,
                summary="The model declined to score this job; review it manually.",
            ),
        )

    async def write_cover_letter(
        self,
        profile: ProfileContext,
        job: JobLike,
        *,
        tone: str,
        language: str,
    ) -> tuple[CoverLetter, AIUsage]:
        """Write a cover letter. `language` is `"job"` or an explicit locale."""
        started_at = time.perf_counter()
        response = await self._send(
            system=COVER_LETTER_SYSTEM_PROMPT,
            user_prompt=build_cover_letter_prompt(profile, job, tone=tone, language=language),
            max_tokens=COVER_LETTER_MAX_TOKENS,
            effort=QUALITY_EFFORT,
        )

        resolved_language = (
            detect_language(getattr(job, "description", None))
            if (language or "job").strip().lower() in {"", "job", "auto", "posting"}
            else language.strip()
        )

        content, usage = self._text_or_fallback(
            response,
            started_at=started_at,
            action="ai.cover_letter",
            refusal_log="Model declined to write the cover letter (category=%s).",
            empty_log="Cover letter response contained no text (stop_reason=%s).",
        )
        # The language is reported even when the letter is empty: the caller shows
        # it next to the "write this yourself" prompt.
        return CoverLetter(content=content, language=resolved_language), usage

    async def answer_questions(
        self,
        profile: ProfileContext,
        job: JobLike,
        questions: list[FormQuestion],
    ) -> tuple[list[ScreeningAnswer], AIUsage]:
        """Draft answers for screening questions.

        Answers come back matched to their `FormQuestion` (so `field_id` and
        `question_type` are populated) and validated against the field's options,
        because an option the form does not offer cannot be filled in.
        """
        started_at = time.perf_counter()
        response = await self._send(
            system=SCREENING_SYSTEM_PROMPT,
            user_prompt=build_screening_prompt(profile, job, questions),
            max_tokens=SCREENING_MAX_TOKENS,
            effort=QUALITY_EFFORT,
            output_format=ScreeningAnswerSet,
        )

        # An answerless set is the empty fallback: reconciling it yields no answers.
        parsed, usage = self._parsed_or_fallback(
            response,
            started_at=started_at,
            action="ai.screening",
            refusal_log="Model declined to answer the screening questions (category=%s).",
            unparsed_log="Screening response could not be parsed (stop_reason=%s).",
            fallback=ScreeningAnswerSet,
        )
        return [_reconcile_answer(answer, questions) for answer in parsed.answers], usage

    async def tailor_resume(
        self,
        profile: ProfileContext,
        job: JobLike,
    ) -> tuple[TailoredResume, AIUsage]:
        """Adapt the candidate's resume to one posting, without inventing anything.

        On refusal or unparseable output, returns an empty `TailoredResume` with
        `AIUsage.refused` set so the caller degrades to "write it by hand".
        """
        started_at = time.perf_counter()
        response = await self._send(
            system=TAILORING_SYSTEM_PROMPT,
            user_prompt=build_tailoring_prompt(profile, job),
            max_tokens=TAILORING_MAX_TOKENS,
            effort=QUALITY_EFFORT,
            output_format=TailoredResume,
        )

        return self._parsed_or_fallback(
            response,
            started_at=started_at,
            action="ai.tailor",
            refusal_log="Model declined to tailor the resume (category=%s).",
            unparsed_log="Tailoring response was empty or unparsable (stop_reason=%s).",
            fallback=lambda: TailoredResume(tailored_markdown=""),
            # A resume with no body parses fine and is still no answer.
            usable=lambda parsed: bool(parsed.tailored_markdown.strip()),
        )

    async def review_draft(
        self,
        profile: ProfileContext,
        job: JobLike,
        *,
        cover_letter: str | None,
        answers: list[dict[str, Any]],
    ) -> tuple[DraftReview, AIUsage]:
        """Second-pass review of drafted materials, from a fresh context.

        On refusal or unparseable output, returns an empty `DraftReview` with
        `AIUsage.refused` set so the caller degrades to "review it yourself".
        """
        started_at = time.perf_counter()
        response = await self._send(
            system=REVIEW_SYSTEM_PROMPT,
            user_prompt=build_review_prompt(
                profile, job, cover_letter=cover_letter, answers=answers
            ),
            max_tokens=REVIEW_MAX_TOKENS,
            effort=QUALITY_EFFORT,
            output_format=DraftReview,
        )

        return self._parsed_or_fallback(
            response,
            started_at=started_at,
            action="ai.review",
            refusal_log="Model declined to review the draft (category=%s).",
            unparsed_log="Review response could not be parsed (stop_reason=%s).",
            fallback=DraftReview,
        )

    async def interview_prep(
        self,
        profile: ProfileContext,
        job: JobLike,
        *,
        submitted_cover_letter: str | None,
        submitted_answers: list[dict[str, Any]],
        missing_requirements: list[str],
        score_summary: str | None,
    ) -> tuple[str, AIUsage]:
        """A markdown interview-prep pack grounded in the stored application.

        On refusal or empty output, returns an empty string with `AIUsage.refused`
        set so the caller degrades to "prepare by hand".
        """
        started_at = time.perf_counter()
        response = await self._send(
            system=INTERVIEW_PREP_SYSTEM_PROMPT,
            user_prompt=build_interview_prep_prompt(
                profile,
                job,
                submitted_cover_letter=submitted_cover_letter,
                submitted_answers=submitted_answers,
                missing_requirements=missing_requirements,
                score_summary=score_summary,
            ),
            max_tokens=INTERVIEW_PREP_MAX_TOKENS,
            effort=QUALITY_EFFORT,
        )

        return self._text_or_fallback(
            response,
            started_at=started_at,
            action="ai.interview_prep",
            refusal_log="Model declined the interview prep (category=%s).",
        )


def _reconcile_answer(answer: ScreeningAnswer, questions: list[FormQuestion]) -> ScreeningAnswer:
    """Attach form metadata to a drafted answer and flag anything unfillable."""
    question = _match_question(answer.question, questions)
    if question is None:
        # No matching field means the automation layer cannot fill it; a human
        # has to place this answer, so it must not pass silently.
        answer.needs_review = True
        answer.confidence = AnswerConfidence.LOW
        return answer

    answer.field_id = question.field_id
    answer.question_type = question.kind
    answer.question = question.label

    if question.options:
        exact = next((opt for opt in question.options if opt == answer.answer), None)
        if exact is None:
            # Recover a casing/whitespace mismatch; anything else is a value the
            # form does not offer and cannot be selected.
            folded = fold(answer.answer.strip())
            recovered = next(
                (opt for opt in question.options if fold(opt.strip()) == folded), None
            )
            if recovered is not None:
                answer.answer = recovered
            else:
                answer.needs_review = True
                answer.confidence = AnswerConfidence.LOW
    elif question.kind == "number" and not _NUMERIC_ANSWER.match(answer.answer.strip()):
        answer.needs_review = True
        answer.confidence = AnswerConfidence.LOW

    if question.required and not answer.answer.strip():
        answer.needs_review = True
        answer.confidence = AnswerConfidence.LOW
    return answer


def _match_question(label: str, questions: list[FormQuestion]) -> FormQuestion | None:
    """Find the question an answer refers to.

    Matching is progressively looser because the model echoes the label as prose
    and routinely drops a trailing `?` or normalizes whitespace. Losing the match
    costs a `field_id`, which makes an otherwise good answer unfillable.
    """
    for question in questions:
        if question.label == label:
            return question
    squashed = squash(label)
    if not squashed:
        return None
    for question in questions:
        if squash(question.label) == squashed:
            return question
    return None


def estimate_cost_usd(usage: AIUsage) -> float | None:
    """List-price cost of a call, or `None` for a model with no known price.

    A locally served model costs nothing, which is a real 0.00 rather than an
    unknown. Hosted free tiers still return `None`: they are free only within a
    quota, so any number we invented for them would be wrong.
    """
    if usage.model in _FREE_MODELS:
        return 0.0
    price = _PRICING_USD_PER_MTOK.get(usage.model)
    if price is None:
        return None
    input_price, output_price = price
    input_tokens = usage.input_tokens or 0
    output_tokens = usage.output_tokens or 0
    return round(
        (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price,
        6,
    )


def get_ai_client(
    model: str | None = None,
    *,
    provider: ChatProvider | None = None,
    credentials: Any | None = None,
) -> AIClient:
    """Build a client, optionally overriding the model, provider or credentials."""
    return AIClient(model=model, provider=provider, credentials=credentials)


__all__ = [
    "AIClient",
    "AINotConfiguredError",
    "detect_language",
    "estimate_cost_usd",
    "flag_unsupported_skills",
    "get_ai_client",
]
