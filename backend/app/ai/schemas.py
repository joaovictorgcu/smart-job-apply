"""AI output contract — provider-agnostic.

Every provider (today, Claude) must return these structures. Keeping the format here
means swapping model or provider never leaks into the services or the API.

Consolidated format (`JobAnalysis`):
    {"score": 87, "reasons": [...], "missing_requirements": [...],
     "cover_letter": "...", "screening_answers": [...]}
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import AnswerConfidence

QuestionType = Literal["text", "textarea", "number", "select", "radio", "checkbox", "unknown"]


class JobScore(BaseModel):
    """How well a job matches the user's profile."""

    model_config = ConfigDict(extra="ignore")

    score: int = Field(ge=0, le=100, description="0-100; how well the profile fits the job.")
    reasons: list[str] = Field(
        default_factory=list, description="Objective reasons for the score (strengths)."
    )
    missing_requirements: list[str] = Field(
        default_factory=list, description="Job requirements the profile does not cover."
    )
    recommend_apply: bool = Field(description="Is it worth applying?")
    summary: str | None = Field(default=None, description="A one-sentence rationale.")

    @field_validator("score")
    @classmethod
    def _clamp(cls, value: int) -> int:
        return max(0, min(100, value))


class ScreeningAnswer(BaseModel):
    """Suggested answer to a screening question.

    `needs_review` (or a low confidence) makes the dashboard highlight the field so
    the user reviews it before submitting — we never guess silently.
    """

    model_config = ConfigDict(extra="ignore")

    question: str
    answer: str
    question_type: QuestionType = "unknown"
    confidence: AnswerConfidence = AnswerConfidence.MEDIUM
    needs_review: bool = False
    reasoning: str | None = None
    # Identifier of the form field, when known (filled in by the automation).
    field_id: str | None = None

    # A model validator, not a field validator: field validators are skipped when
    # the field falls back to its default, which is the common case here (the model
    # returns a confidence but no needs_review) and would leave a low-confidence
    # answer unflagged for review.
    @model_validator(mode="after")
    def _low_confidence_needs_review(self) -> ScreeningAnswer:
        if self.confidence == AnswerConfidence.LOW and not self.needs_review:
            self.needs_review = True
        return self


class ScreeningAnswerSet(BaseModel):
    """Wrapper for structured output (the root has to be an object)."""

    model_config = ConfigDict(extra="ignore")

    answers: list[ScreeningAnswer] = Field(default_factory=list)


class CoverLetter(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str
    language: str = Field(default="pt-BR", description="Detected/used language (e.g. pt-BR, en).")


# Every allowed action operates on content that is ALREADY in the resume. There is
# deliberately no "added" action: adding new experience would be invention, which
# is the one thing tailoring must never do.
CVChangeAction = Literal["reordered", "emphasized", "rephrased", "condensed", "omitted"]


class CVChange(BaseModel):
    """One edit the model made while tailoring the resume, for the user to see."""

    model_config = ConfigDict(extra="ignore")

    section: str = Field(description="Which part of the resume changed.")
    action: CVChangeAction
    detail: str = Field(description="What changed and why it fits this job.")


class TailoredResume(BaseModel):
    """A resume adapted to one job — reorganized and re-emphasized, never invented.

    `unsupported_requirements` is the honesty valve: anything the posting asks for
    that the source resume cannot back is surfaced here rather than fabricated into
    `tailored_markdown`.
    """

    model_config = ConfigDict(extra="ignore")

    tailored_markdown: str = Field(description="The adapted resume, in Markdown.")
    changes: list[CVChange] = Field(default_factory=list)
    unsupported_requirements: list[str] = Field(
        default_factory=list,
        description="Requirements the source resume does not support (not invented).",
    )
    summary: str | None = Field(default=None, description="A one-line note on the approach.")


class JobAnalysis(BaseModel):
    """Consolidated result of a job analysis."""

    model_config = ConfigDict(extra="ignore")

    score: int = 0
    reasons: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    recommend_apply: bool = False
    summary: str | None = None
    cover_letter: str | None = None
    cover_letter_language: str | None = None
    screening_answers: list[ScreeningAnswer] = Field(default_factory=list)
    # The AI may refuse (stop_reason="refusal"): this flags the manual fallback.
    refused: bool = False
    refusal_reason: str | None = None


class AIUsage(BaseModel):
    """Tokens/latency of a single call, for auditing and cost tracking."""

    model_config = ConfigDict(extra="ignore")

    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    refused: bool = False
    refusal_category: str | None = None
