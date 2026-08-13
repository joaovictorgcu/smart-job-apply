"""A deterministic stand-in for `app.ai.client.AIClient`.

It matches the real client's public surface exactly — three methods, each
returning `(result, AIUsage)` — so it can be dropped in wherever `get_ai_client`
is called, and no test ever reaches the Anthropic API.

Knobs cover the three outcomes that matter for safety:

* `refused`: the model declines. Not an exception — HTTP 200 with
  `stop_reason == "refusal"` — so the client returns an empty fallback with
  `AIUsage.refused` set, and the caller must degrade to manual input.
* `low_confidence`: answers come back `confidence="low"`, which the schema turns
  into `needs_review=True`.
* `api_error`: a real `anthropic.APIError`, which is what the service layer
  catches.
"""

from __future__ import annotations

from typing import Any

import anthropic
import httpx

from app.ai.schemas import (
    AIUsage,
    CoverLetter,
    CVChange,
    JobScore,
    ScoreDimension,
    ScoreGate,
    ScreeningAnswer,
    StretchFlag,
    TailoredResume,
)
from app.models.enums import AnswerConfidence

DEFAULT_MODEL = "claude-opus-5"
REFUSAL_CATEGORY = "policy"
_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


class FakeAIClient:
    """Deterministic `AIClient`."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        score: int = 85,
        reasons: list[str] | None = None,
        missing_requirements: list[str] | None = None,
        breakdown: list[dict[str, Any]] | None = None,
        gates: list[dict[str, Any]] | None = None,
        stretch_flags: list[dict[str, str]] | None = None,
        recommend_apply: bool | None = None,
        cover_letter_text: str = "I am excited about this role and my background fits it well.",
        language: str = "en",
        answer_value: str = "7",
        # Default tailored resume uses only technologies in the factory profile, so
        # the invention guard stays quiet unless a test opts into an invention.
        tailored_markdown: str = (
            "# Candidate\n\n## Skills\nPython, FastAPI, PostgreSQL\n\n"
            "## Experience\nBuilt and shipped Python APIs with FastAPI."
        ),
        tailor_changes: list[dict[str, str]] | None = None,
        tailor_unsupported: list[str] | None = None,
        refused: bool = False,
        low_confidence: bool = False,
        api_error: bool = False,
        input_tokens: int = 1200,
        output_tokens: int = 180,
        latency_ms: int = 640,
    ) -> None:
        self.model = model
        self.score = score
        self.reasons = reasons if reasons is not None else ["Matches the required Python stack"]
        self.missing_requirements = (
            missing_requirements if missing_requirements is not None else ["Kubernetes"]
        )
        self.breakdown = (
            breakdown
            if breakdown is not None
            else [
                {
                    "dimension": "skills",
                    "score": 90,
                    "weight": "hard",
                    "evidence": "Posting asks for Python and FastAPI; both are on the resume.",
                },
                {
                    "dimension": "experience",
                    "score": 80,
                    "weight": "hard",
                    "evidence": "Asks for 5+ years, resume shows 7.",
                },
            ]
        )
        # Both gates pass by default so existing tests keep their behaviour; a
        # test opts into a failure or a flag explicitly.
        self.gates = (
            gates
            if gates is not None
            else [
                {"gate": "eligibility", "status": "pass", "evidence": "No such requirement."},
                {"gate": "language", "status": "pass", "evidence": "Posting is in English."},
            ]
        )
        self.stretch_flags = stretch_flags if stretch_flags is not None else []
        self.recommend_apply = recommend_apply
        self.cover_letter_text = cover_letter_text
        self.language = language
        self.answer_value = answer_value
        self.tailored_markdown = tailored_markdown
        self.tailor_changes = (
            tailor_changes
            if tailor_changes is not None
            else [{"section": "Skills", "action": "reordered", "detail": "Led with Python."}]
        )
        self.tailor_unsupported = tailor_unsupported if tailor_unsupported is not None else []
        self.refused = refused
        self.low_confidence = low_confidence
        self.api_error = api_error
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_ms = latency_ms

        self.calls: list[str] = []
        self.last_usage: AIUsage | None = None

    # --- introspection ----------------------------------------------------

    @property
    def is_configured(self) -> bool:
        return True

    def call_count(self, name: str) -> int:
        return self.calls.count(name)

    def usage(self) -> AIUsage:
        return self.last_usage or AIUsage(model=self.model)

    @property
    def confidence(self) -> AnswerConfidence:
        return AnswerConfidence.LOW if self.low_confidence else AnswerConfidence.HIGH

    def _record(self, name: str) -> AIUsage:
        self.calls.append(name)
        if self.api_error:
            raise anthropic.APIError("Simulated Anthropic failure.", _REQUEST, body=None)
        usage = AIUsage(
            model=self.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            latency_ms=self.latency_ms,
            refused=self.refused,
            refusal_category=REFUSAL_CATEGORY if self.refused else None,
        )
        self.last_usage = usage
        return usage

    # --- AIClient surface -------------------------------------------------

    async def score_job(
        self, profile: Any = None, job: Any = None, **_kwargs: Any
    ) -> tuple[JobScore, AIUsage]:
        usage = self._record("score_job")
        if self.refused:
            return (
                JobScore(
                    score=0,
                    recommend_apply=False,
                    summary="The model declined to score this posting.",
                ),
                usage,
            )
        recommend = self.recommend_apply
        if recommend is None:
            recommend = self.score >= 70
        return (
            JobScore(
                score=self.score,
                reasons=list(self.reasons),
                missing_requirements=list(self.missing_requirements),
                breakdown=[ScoreDimension(**dimension) for dimension in self.breakdown],
                gates=[ScoreGate(**gate) for gate in self.gates],
                recommend_apply=recommend,
                summary=f"Deterministic test score of {self.score}.",
            ),
            usage,
        )

    async def write_cover_letter(
        self,
        profile: Any = None,
        job: Any = None,
        *,
        tone: str = "professional",
        language: str = "job",
        **_kwargs: Any,
    ) -> tuple[CoverLetter, AIUsage]:
        usage = self._record("write_cover_letter")
        if self.refused:
            return CoverLetter(content="", language=self.language), usage
        resolved = self.language if language in ("job", "", None) else language
        return CoverLetter(content=self.cover_letter_text, language=resolved), usage

    async def answer_questions(
        self,
        profile: Any = None,
        job: Any = None,
        questions: Any = (),
        **_kwargs: Any,
    ) -> tuple[list[ScreeningAnswer], AIUsage]:
        usage = self._record("answer_questions")
        if self.refused:
            return [], usage
        return self.build_answers(questions), usage

    async def tailor_resume(
        self, profile: Any = None, job: Any = None, **_kwargs: Any
    ) -> tuple[TailoredResume, AIUsage]:
        usage = self._record("tailor_resume")
        if self.refused:
            return TailoredResume(tailored_markdown=""), usage
        return (
            TailoredResume(
                tailored_markdown=self.tailored_markdown,
                changes=[CVChange(**change) for change in self.tailor_changes],
                unsupported_requirements=list(self.tailor_unsupported),
                stretch_flags=[StretchFlag(**flag) for flag in self.stretch_flags],
                summary="Deterministic tailored resume.",
            ),
            usage,
        )

    # --- helpers ----------------------------------------------------------

    def build_answers(self, questions: Any = ()) -> list[ScreeningAnswer]:
        answers: list[ScreeningAnswer] = []
        for question in questions or ():
            label, kind, field_id = describe_question(question)
            answers.append(
                ScreeningAnswer(
                    question=label,
                    answer=self.answer_value,
                    question_type=kind,
                    confidence=self.confidence,
                    reasoning="Deterministic test answer.",
                    field_id=field_id,
                )
            )
        return answers


def describe_question(question: Any) -> tuple[str, str, str | None]:
    """Read a label, a kind and a field id out of whatever shape is passed in."""
    valid_kinds = {"text", "textarea", "number", "select", "radio", "checkbox", "unknown"}
    if isinstance(question, str):
        return question, "text", None
    if isinstance(question, dict):
        label = question.get("label") or question.get("question")
        kind = question.get("kind") or question.get("question_type")
        field_id = question.get("field_id")
    else:
        label = getattr(question, "label", None) or getattr(question, "question", None)
        kind = getattr(question, "kind", None) or getattr(question, "question_type", None)
        field_id = getattr(question, "field_id", None)
    return (
        str(label or "Unlabelled question"),
        kind if kind in valid_kinds else "unknown",
        field_id,
    )
