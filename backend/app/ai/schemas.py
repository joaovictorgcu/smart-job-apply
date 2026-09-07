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
    # Deliberately kept alongside `weight`: "is this a hard requirement" and "how
    # much did it move the number" are different questions. A nice-to-have the
    # posting dwells on can carry more weight than a hard requirement mentioned once.
    #
    # Defaults to 0 rather than being required, because this field is also how
    # breakdowns persisted before it existed are read back: `Job.score_breakdown`
    # is a JSON column of dumped `ScoreDimension`s, so every stored row is
    # re-validated through this model. 0 therefore means "no weight was stated",
    # which is exactly what a pre-existing row knows about itself.
    weight_pct: int = Field(
        default=0,
        ge=0,
        le=100,
        description=(
            "Share of the overall score this dimension carries; the emitted "
            "values sum to 100 across the breakdown."
        ),
    )
    evidence: str = Field(
        description="What in the posting and the candidate's profile produced this number."
    )


def _rescaled_to_100(weights: list[int]) -> list[int]:
    """Scale non-negative weights so they sum to exactly 100.

    Largest-remainder apportionment: floor every scaled share, then hand the
    leftover points to the largest fractional remainders, ties broken by
    position. That keeps the result deterministic — the same input always
    produces the same output — which matters because these numbers end up
    persisted and rendered as the explanation of a score.

    An all-zero input carries no information about relative importance, so the
    weight is split evenly rather than left at zero: the model did choose to
    emit those dimensions, and an even split says "all of them, equally", which
    is the least-assuming reading of silence.
    """
    if not weights:
        return []

    total = sum(weights)
    if total == 0:
        # Nothing to be proportional to; see the docstring for why even beats zero.
        shares = [100 / len(weights)] * len(weights)
    else:
        shares = [weight * 100 / total for weight in weights]

    floored = [int(share) for share in shares]
    leftover = 100 - sum(floored)
    if leftover > 0:
        ranked = sorted(
            range(len(shares)),
            key=lambda index: (-(shares[index] - floored[index]), index),
        )
        for index in ranked[:leftover]:
            floored[index] += 1
    return floored


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

    # Normalise rather than reject. The prompt asks for weights summing to 100,
    # but models are unreliable at arithmetic, and a `ValidationError` here would
    # throw away an entire scoring call — every gate, reason and dimension — over
    # a rounding error the model made in the last field it wrote. The relative
    # importance it expressed (30 vs 10) survives rescaling intact; only the
    # arithmetic is repaired, and repairing it is deterministic. Rejecting would
    # cost a paid retry to obtain the same judgement with tidier numbers.
    #
    # Only `JobScore` normalises. Stored breakdowns are read back as bare
    # `ScoreDimension` lists, so rows written before `weight_pct` existed keep
    # their zeros instead of being handed invented even weights on read.
    @model_validator(mode="after")
    def _normalize_breakdown_weights(self) -> JobScore:
        if not self.breakdown:
            return self
        rescaled = _rescaled_to_100([dimension.weight_pct for dimension in self.breakdown])
        for dimension, weight_pct in zip(self.breakdown, rescaled, strict=True):
            dimension.weight_pct = weight_pct
        return self


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


# The reviewer's critique arrives in four mandatory categories, so silence in
# one of them is an explicit "no issues", never a skipped check.
ReviewCategory = Literal["missed_keywords", "company_angle", "reframing", "tone"]

# Four coverage states, not two: "the document never says it but the profile
# supports it" is the actionable one, and "gap" must stay visible, never stuffed.
CoverageStatus = Literal["covered", "synonym_only", "missing_have_it", "missing_gap"]


class SuggestedEdit(BaseModel):
    """One mechanical edit to the cover letter, applied verbatim or not at all."""

    model_config = ConfigDict(extra="ignore")

    old_string: str = Field(description="Exact text currently in the letter.")
    new_string: str = Field(description="The replacement text.")
    reason: str = Field(description="Why, in one sentence.")


class ReviewNote(BaseModel):
    """The reviewer's finding in one category — 'no issues' is a valid finding."""

    model_config = ConfigDict(extra="ignore")

    category: ReviewCategory
    note: str


class RequirementCoverage(BaseModel):
    """Whether one stated requirement is addressed by the draft documents."""

    model_config = ConfigDict(extra="ignore")

    requirement: str
    status: CoverageStatus
    note: str | None = Field(
        default=None, description="Where it is covered, or what supports adding it."
    )


class DraftReview(BaseModel):
    """A second, fresh-context pass over the drafted application materials.

    `edits` are grounded, mechanical improvements to the letter; `critique` is
    the narrative judgment in four mandatory categories; `coverage` maps every
    stated requirement to one of four statuses. Nothing here submits anything —
    the human still reads and approves.
    """

    model_config = ConfigDict(extra="ignore")

    edits: list[SuggestedEdit] = Field(default_factory=list)
    critique: list[ReviewNote] = Field(default_factory=list)
    coverage: list[RequirementCoverage] = Field(default_factory=list)
    summary: str | None = Field(default=None, description="One-sentence verdict on the draft.")


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
