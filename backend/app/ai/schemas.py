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

# A closed set, not free text: the dashboard renders one labelled row per
# dimension and has to translate the label, which is impossible if the model
# invents its own names. It also makes two jobs' breakdowns comparable.
ScoreDimensionName = Literal[
    "skills",
    "experience",
    "seniority",
    "education",
    "location",
    "language",
]


class ScoreDimension(BaseModel):
    """One axis of the fit score, so a number becomes an explanation."""

    model_config = ConfigDict(extra="ignore")

    dimension: ScoreDimensionName
    score: int = Field(ge=0, le=100, description="0-100 for this dimension alone.")
    weight: Literal["hard", "nice_to_have"] = Field(
        default="hard",
        description="Whether the posting states this as a requirement or a preference.",
    )
    evidence: str = Field(
        description="What in the posting and the candidate's profile produced this number."
    )


# Decisive checks evaluated before the score. A failed gate means the score is
# irrelevant: no fit number outweighs "requires citizenship the candidate lacks".
GateName = Literal["eligibility", "language"]
GateStatus = Literal["pass", "fail", "flag"]


class ScoreGate(BaseModel):
    """One decisive check, with the posting's own wording as evidence."""

    model_config = ConfigDict(extra="ignore")

    gate: GateName
    status: GateStatus
    evidence: str = Field(
        description="The posting's quoted wording, or why the gate passed."
    )


class JobScore(BaseModel):
    """How well a job matches the user's profile."""

    model_config = ConfigDict(extra="ignore")

    score: int = Field(ge=0, le=100, description="0-100; how well the profile fits the job.")
    gates: list[ScoreGate] = Field(
        default_factory=list,
        description="Eligibility and language gates, evaluated before the score.",
    )
    reasons: list[str] = Field(
        default_factory=list, description="Objective reasons for the score (strengths)."
    )
    missing_requirements: list[str] = Field(
        default_factory=list, description="Job requirements the profile does not cover."
    )
    breakdown: list[ScoreDimension] = Field(
        default_factory=list,
        description="Per-dimension scores that explain how the overall score was reached.",
    )
    recommend_apply: bool = Field(description="Is it worth applying?")
    summary: str | None = Field(default=None, description="A one-sentence rationale.")

    @field_validator("score")
    @classmethod
    def _clamp(cls, value: int) -> int:
        return max(0, min(100, value))


# Where an answer came from. The distinction that matters to the reviewer is
# "something I wrote" versus "something the model produced": `answer_bank` and
# `user` are the user's own words, `ai` is inference over the profile.
AnswerSource = Literal["answer_bank", "ai", "user"]


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
    # Defaults to `ai`: this schema is what the model fills in, and every other
    # producer (the answer bank, the review UI) sets the field explicitly.
    source: AnswerSource = "ai"
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


class StretchFlag(BaseModel):
    """A tailored claim in the grey zone between honest rephrasing and invention.

    Grounded in the source resume, but framed aggressively enough that an
    interviewer probing it could make the candidate backtrack — the user decides
    whether to keep, soften, or drop it.
    """

    model_config = ConfigDict(extra="ignore")

    text: str = Field(description="The stretched claim, quoted from the tailored resume.")
    why_stretch: str = Field(description="What makes it a stretch rather than a plain fact.")


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
    stretch_flags: list[StretchFlag] = Field(
        default_factory=list,
        description="Claims kept in the resume but aggressive enough to deserve review.",
    )
    summary: str | None = Field(default=None, description="A one-line note on the approach.")


class JobAnalysis(BaseModel):
    """Consolidated result of a job analysis."""

    model_config = ConfigDict(extra="ignore")

    score: int = 0
    reasons: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    breakdown: list[ScoreDimension] = Field(default_factory=list)
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
