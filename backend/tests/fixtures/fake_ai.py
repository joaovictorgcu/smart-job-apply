"""A deterministic stand-in for the Claude client.

The AI boundary is `app/ai/schemas.py`: whatever the real client looks like, it has
to hand back `JobScore`, `CoverLetter`, `ScreeningAnswer` and `JobAnalysis`. This
fake produces exactly those, with knobs for the three cases that matter for
safety: a refusal, a low-confidence answer, and a transport error.

Method names are duplicated under the plausible aliases (`score_job`/`score`,
`generate_cover_letter`/`cover_letter`, ...) so a naming choice in the real client
does not silently turn into a network call.
"""

from __future__ import annotations

from typing import Any

from app.ai.schemas import (
    AIUsage,
    CoverLetter,
    JobAnalysis,
    JobScore,
    ScreeningAnswer,
    ScreeningAnswerSet,
)
from app.models.enums import AnswerConfidence

DEFAULT_MODEL = "claude-opus-5"
REFUSAL_REASON = "The model declined to answer this request."


class FakeAIError(RuntimeError):
    """Transport-level failure, standing in for `anthropic.APIError`."""


class FakeAIClient:
    """Deterministic AI client.

    Knobs:
        score:          the score every job gets.
        refused:        the model refuses — nothing is generated, `refused` is set.
        low_confidence: screening answers come back `confidence="low"`, which the
                        schema turns into `needs_review=True`.
        api_error:      every call raises, to exercise error handling.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        score: int = 85,
        reasons: list[str] | None = None,
        missing_requirements: list[str] | None = None,
        recommend_apply: bool | None = None,
        cover_letter_text: str = "I am excited about this role and my background fits it well.",
        language: str = "en",
        answer_value: str = "7",
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
        self.recommend_apply = recommend_apply
        self.cover_letter_text = cover_letter_text
        self.language = language
        self.answer_value = answer_value
        self.refused = refused
        self.low_confidence = low_confidence
        self.api_error = api_error
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_ms = latency_ms

        self.calls: list[str] = []
        self.last_usage: AIUsage | None = None

    # -- introspection the app layer may use ------------------------------- #

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def configured(self) -> bool:
        return True

    def status(self) -> dict[str, Any]:
        return {"configured": True, "model": self.model}

    # -- helpers ----------------------------------------------------------- #

    def _record(self, name: str) -> None:
        self.calls.append(name)
        if self.api_error:
            raise FakeAIError("Simulated Anthropic API failure.")
        self.last_usage = AIUsage(
            model=self.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            latency_ms=self.latency_ms,
            refused=self.refused,
            refusal_category="policy" if self.refused else None,
        )

    def call_count(self, name: str) -> int:
        return self.calls.count(name)

    @property
    def confidence(self) -> AnswerConfidence:
        return AnswerConfidence.LOW if self.low_confidence else AnswerConfidence.HIGH

    def usage(self) -> AIUsage:
        return self.last_usage or AIUsage(model=self.model)

    # -- scoring ----------------------------------------------------------- #

    async def score_job(self, *_args: Any, **_kwargs: Any) -> JobScore:
        self._record("score_job")
        recommend = self.recommend_apply
        if recommend is None:
            recommend = self.score >= 70
        return JobScore(
            score=self.score,
            reasons=list(self.reasons),
            missing_requirements=list(self.missing_requirements),
            recommend_apply=recommend,
            summary=f"Deterministic test score of {self.score}.",
        )

    score = score_job
    evaluate_job = score_job

    async def score_jobs(self, jobs: Any, *_args: Any, **_kwargs: Any) -> list[JobScore]:
        return [await self.score_job(job) for job in jobs]

    # -- cover letter ------------------------------------------------------ #

    async def generate_cover_letter(self, *_args: Any, **_kwargs: Any) -> CoverLetter:
        self._record("generate_cover_letter")
        return CoverLetter(content=self.cover_letter_text, language=self.language)

    cover_letter = generate_cover_letter
    write_cover_letter = generate_cover_letter

    # -- screening answers ------------------------------------------------- #

    async def answer_screening_questions(
        self, questions: Any = (), *_args: Any, **_kwargs: Any
    ) -> ScreeningAnswerSet:
        self._record("answer_screening_questions")
        return ScreeningAnswerSet(answers=self.build_answers(questions))

    answer_questions = answer_screening_questions
    screening_answers = answer_screening_questions

    def build_answers(self, questions: Any = ()) -> list[ScreeningAnswer]:
        answers: list[ScreeningAnswer] = []
        for question in questions or ():
            label, kind, field_id = _describe(question)
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

    # -- consolidated analysis --------------------------------------------- #

    async def analyze_job(
        self, *_args: Any, questions: Any = (), **_kwargs: Any
    ) -> JobAnalysis:
        self._record("analyze_job")
        if self.refused:
            return JobAnalysis(refused=True, refusal_reason=REFUSAL_REASON)
        recommend = self.recommend_apply
        if recommend is None:
            recommend = self.score >= 70
        return JobAnalysis(
            score=self.score,
            reasons=list(self.reasons),
            missing_requirements=list(self.missing_requirements),
            recommend_apply=recommend,
            summary=f"Deterministic test score of {self.score}.",
            cover_letter=self.cover_letter_text,
            cover_letter_language=self.language,
            screening_answers=self.build_answers(questions),
        )

    analyze = analyze_job

    async def close(self) -> None:
        self.calls.append("close")


def _describe(question: Any) -> tuple[str, str, str | None]:
    """Read a label, a kind and a field id out of whatever shape is passed in."""
    if isinstance(question, str):
        return question, "text", None
    label = getattr(question, "label", None) or getattr(question, "question", None)
    kind = getattr(question, "kind", None) or getattr(question, "question_type", None)
    field_id = getattr(question, "field_id", None)
    if label is None and isinstance(question, dict):
        label = question.get("label") or question.get("question")
        kind = question.get("kind") or question.get("question_type")
        field_id = question.get("field_id")
    valid_kinds = {"text", "textarea", "number", "select", "radio", "checkbox", "unknown"}
    return (
        str(label or "Unlabelled question"),
        kind if kind in valid_kinds else "unknown",
        field_id,
    )
