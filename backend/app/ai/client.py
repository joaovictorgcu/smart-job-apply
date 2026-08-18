"""Claude integration.

Everything provider-specific is confined here: SDK calls, retries, refusal
handling, and token accounting. Callers get the provider-agnostic models from
`app.ai.schemas` plus an `AIUsage` describing the call.

Two invariants matter for the rest of the app:

* A refusal is a normal outcome, not an exception. `claude-opus-5` can decline a
  request with HTTP 200 and `stop_reason == "refusal"`; every method returns a
  usable fallback with `AIUsage.refused` set so the caller degrades to manual
  input instead of crashing.
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

import anthropic
from anthropic import AsyncAnthropic

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

_NUMERIC_ANSWER = re.compile(r"^-?\d+([.,]\d+)?$")

# Version-compatibility shim state: SDK builds disagree on whether
# `output_config` may accompany `output_format`. Once a build rejects the pair we
# stop sending it and log the downgrade a single time.
_output_config_supported = True
_shim_logged = False


class AINotConfiguredError(RuntimeError):
    """No Anthropic API key is configured, so AI features are unavailable."""

    def __init__(
        self,
        message: str = (
            "AI features are not configured. Set ANTHROPIC_API_KEY to enable job "
            "scoring, cover letters, and screening answers."
        ),
    ) -> None:
        super().__init__(message)


# Common technologies whose presence in a tailored resume but absence from the
# source is the clearest, most checkable sign of invention. Lowercased; matched as
# whole words. Not exhaustive by design — the structural checks below catch the
# long tail (CamelCase and alphanumeric tokens like FastAPI, PostgreSQL, OAuth2).
_KNOWN_TECHNOLOGIES = frozenset(
    {
        "python", "java", "javascript", "typescript", "golang", "rust", "ruby",
        "php", "kotlin", "swift", "scala", "elixir", "clojure", "haskell", "perl",
        "django", "flask", "fastapi", "rails", "laravel", "spring", "express",
        "nestjs", "react", "angular", "vue", "svelte", "nextjs", "nuxt", "jquery",
        "node", "deno", "bun", "graphql", "grpc", "rest", "soap", "webpack", "vite",
        "postgresql", "postgres", "mysql", "mariadb", "sqlite", "oracle", "mongodb",
        "redis", "cassandra", "elasticsearch", "dynamodb", "snowflake", "clickhouse",
        "kafka", "rabbitmq", "celery", "airflow", "spark", "hadoop", "flink", "dbt",
        "docker", "kubernetes", "terraform", "ansible", "puppet", "chef", "helm",
        "jenkins", "gitlab", "github", "circleci", "argocd", "prometheus", "grafana",
        "aws", "azure", "gcp", "heroku", "vercel", "netlify", "cloudflare", "lambda",
        "tensorflow", "pytorch", "keras", "sklearn", "pandas", "numpy", "scipy",
        "kubeflow", "mlflow", "langchain", "opencv", "huggingface", "transformers",
        "playwright", "selenium", "cypress", "jest", "pytest", "junit", "mocha",
        "linux", "bash", "nginx", "apache", "kong", "istio", "consul", "vault",
        "git", "jira", "confluence", "figma", "tableau", "powerbi", "looker",
        "sql", "nosql", "html", "css", "sass", "tailwind", "bootstrap", "wasm",
    }
)

# CamelCase like FastAPI, PostgreSQL, JavaScript, GraphQL.
_CAMELCASE = re.compile(r"\b[A-Za-z]*[a-z][A-Z][A-Za-z]*\b")
# Alphanumeric tokens like S3, OAuth2, Python3, k8s, EC2, gpt4 — almost always tech.
_ALNUM_TOKEN = re.compile(r"\b(?:[A-Za-z]+\d+[A-Za-z\d]*|\d+[A-Za-z]+[A-Za-z\d]*)\b")
# A word token, allowing an internal `.`/`+`/`#` (node.js, asp.net) but never a
# trailing one — otherwise "Kubernetes." captures the sentence period and no longer
# matches a known technology.
_ALPHA_WORD = re.compile(r"[a-z][a-z0-9]*(?:[.+#][a-z0-9]+)*")
# Same shape, original-cased, so a flagged term keeps the casing the model wrote.
_ORIG_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[.+#][A-Za-z0-9]+)*")


def flag_unsupported_skills(source_text: str, tailored_text: str) -> list[str]:
    """Technologies present in the tailored resume but absent from the source.

    A programmatic safety net for the "never invent" rule: it does not trust the
    model to have obeyed. It targets the most checkable class of invention —
    fabricated tools and technologies — by comparing tech-shaped tokens in the
    tailored text against everything the candidate actually provided.

    It cannot catch an invented *achievement* phrased in plain words, and it errs
    toward over-flagging (a company name in CamelCase may surface). That is by
    design: every item is a "verify this yourself" prompt to the human, never an
    automatic block. Missing a real invention is the failure to avoid.
    """
    source = fold(source_text or "")
    source_words = set(_ALPHA_WORD.findall(source))

    def supported(token: str) -> bool:
        folded = fold(token)
        # Whole-word membership, or a substring for multi-part tokens the word
        # split would break apart (e.g. "node.js" folding to "node js").
        return folded in source_words or folded in source

    flagged: dict[str, str] = {}  # folded -> original casing (first seen)
    for match in _CAMELCASE.findall(tailored_text) + _ALNUM_TOKEN.findall(tailored_text):
        if not supported(match):
            flagged.setdefault(fold(match), match)

    for token in _ORIG_WORD.findall(tailored_text):
        folded = fold(token)
        if folded in _KNOWN_TECHNOLOGIES and not supported(token):
            flagged.setdefault(folded, token)

    return sorted(flagged.values(), key=str.lower)


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, anthropic.RateLimitError):
        return True
    if isinstance(error, anthropic.APIStatusError):
        return error.status_code >= 500
    # Covers APITimeoutError, which subclasses APIConnectionError.
    return isinstance(error, anthropic.APIConnectionError)


def _mentions_output_config(error: Exception) -> bool:
    message = str(error).lower()
    return "output_config" in message or "effort" in message


def _note_shim_downgrade(error: Exception) -> None:
    """Disable `output_config` for this process, logging the downgrade once."""
    global _output_config_supported, _shim_logged
    _output_config_supported = False
    if not _shim_logged:
        _shim_logged = True
        logger.warning(
            "Installed Anthropic SDK rejects output_config alongside output_format; "
            "retrying without effort control for the rest of this process (%s).",
            error,
            extra={"action": "ai.output_config_downgrade", "detail": str(error)},
        )


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
    """Async wrapper around the Anthropic Messages API."""

    def __init__(self, *, model: str | None = None) -> None:
        self._settings = get_settings()
        self.model = model or self._settings.anthropic_model
        self._client: AsyncAnthropic | None = None

    @property
    def is_configured(self) -> bool:
        return self._settings.ai_enabled

    def _require_client(self) -> AsyncAnthropic:
        if not self.is_configured:
            raise AINotConfiguredError
        if self._client is None:
            # The key comes from settings so a `.env` file works even when the
            # value is not exported into the process environment.
            self._client = AsyncAnthropic(api_key=self._settings.anthropic_api_key or None)
        return self._client

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

        `output_format` selects `messages.parse` (validated structured output)
        over `messages.create` (free text).
        """
        client = self._require_client()
        base_kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if output_format is not None:
            base_kwargs["output_format"] = output_format

        async def attempt() -> Any:
            call = client.messages.parse if output_format is not None else client.messages.create
            if effort and _output_config_supported:
                try:
                    return await call(**base_kwargs, output_config={"effort": effort})
                except TypeError as exc:
                    _note_shim_downgrade(exc)
                except anthropic.BadRequestError as exc:
                    if not _mentions_output_config(exc):
                        raise
                    _note_shim_downgrade(exc)
            return await call(**base_kwargs)

        last_error: Exception | None = None
        for attempt_number in range(1, MAX_ATTEMPTS + 1):
            try:
                return await attempt()
            except anthropic.APIError as exc:
                if not _is_retryable(exc):
                    raise
                last_error = exc
                if attempt_number == MAX_ATTEMPTS:
                    break
                delay = min(
                    _BASE_RETRY_DELAY * (2 ** (attempt_number - 1)) + random.uniform(0, 0.5),
                    _MAX_RETRY_DELAY,
                )
                logger.warning(
                    "Anthropic call failed (attempt %s/%s), retrying in %.1fs: %s",
                    attempt_number,
                    MAX_ATTEMPTS,
                    delay,
                    exc,
                    extra={
                        "action": "ai.retry",
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
    """List-price cost of a call, or `None` for a model with no known price."""
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


def get_ai_client(model: str | None = None) -> AIClient:
    """Build a client, optionally overriding the configured model."""
    return AIClient(model=model)


__all__ = [
    "AIClient",
    "AINotConfiguredError",
    "detect_language",
    "estimate_cost_usd",
    "flag_unsupported_skills",
    "get_ai_client",
]
