"""Offline provider: deterministic answers, no network, no API key, no cost.

This is what lets the end-to-end suite drive the whole product — search, score,
draft, review gate, submit — without calling any model. It is also the provider
to select when you want to click through the app locally without signing up for
anything.

Two properties matter and are load-bearing for the tests:

* **Deterministic.** The same job always produces the same score and the same
  answers, so an assertion on a number is stable. Scores are derived from a hash
  of the posting rather than fixed, so a suite still sees a spread of values.
* **Shaped like a real answer.** Every field the UI renders is populated —
  gates, breakdown weights, reasons, per-question confidence — because a stub
  that returns empty lists would make the review screens untestable.

It never claims to be a real assessment. `AI_STUB_SCORE` pins the score when a
test needs a specific side of a threshold.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from pydantic import BaseModel

from app.ai.providers.base import ProviderResponse, TextBlock, Usage
from app.ai.schemas import (
    CVChange,
    DraftReview,
    JobScore,
    RequirementCoverage,
    ReviewNote,
    ScoreDimension,
    ScoreGate,
    ScreeningAnswer,
    ScreeningAnswerSet,
    TailoredResume,
)
from app.models.enums import AnswerConfidence

STUB_MODEL = "stub-offline"

# Weights sum to 100, matching what the prompt asks a real model for.
_DIMENSIONS: tuple[tuple[str, str, int], ...] = (
    ("skills", "hard", 40),
    ("experience", "hard", 30),
    ("seniority", "nice_to_have", 15),
    ("location", "nice_to_have", 15),
)

# Questions the offline provider answers from the profile rather than guessing.
# Anything not matched here is returned flagged for review, which is the honest
# outcome for a stub and keeps the review gate exercised.
_ANSWER_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"years?|anos", re.I), "5"),
    (re.compile(r"^\s*(city|cidade|location|localiza)", re.I), "São Paulo, Brazil"),
    (re.compile(r"authoriz|autoriza|work permit|visto", re.I), "Yes"),
    (re.compile(r"sponsor|patroc", re.I), "No"),
    (re.compile(r"salary|salário|salario|remunera", re.I), "12000"),
    (re.compile(r"notice|aviso|disponibilidade|start", re.I), "30"),
    (re.compile(r"english|inglês|ingles", re.I), "Advanced"),
)

@dataclass(frozen=True)
class _Question:
    """One question recovered from the screening prompt."""

    label: str
    options: tuple[str, ...] = ()


class StubProvider:
    """Answers every capability from the prompt text alone."""

    name = "stub"

    def __init__(self, *, model: str = STUB_MODEL, forced_score: int | None = None) -> None:
        self._model = model
        self._forced_score = forced_score

    @property
    def model(self) -> str:
        return self._model

    async def aclose(self) -> None:
        return None

    async def send(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
        effort: str | None = None,
        output_format: type[BaseModel] | None = None,
    ) -> ProviderResponse:
        if output_format is None:
            text = self._free_text(system, user_prompt)
            return ProviderResponse(
                model=self._model,
                content=[TextBlock(text=text)],
                usage=self._usage(user_prompt, text),
            )

        parsed = self._structured(output_format, user_prompt)
        return ProviderResponse(
            model=self._model,
            parsed_output=parsed,
            content=[TextBlock(text=parsed.model_dump_json())],
            usage=self._usage(user_prompt, parsed.model_dump_json()),
        )

    # --- structured capabilities --------------------------------------------

    def _structured(self, output_format: type[BaseModel], prompt: str) -> BaseModel:
        if output_format is JobScore:
            return self._score(prompt)
        if output_format is ScreeningAnswerSet:
            return self._answers(prompt)
        if output_format is TailoredResume:
            return self._resume(prompt)
        if output_format is DraftReview:
            return self._review(prompt)
        # An unknown schema still has to validate; every field in the project's
        # schemas is either defaulted or nullable, so the empty instance is valid.
        return output_format()

    def _score(self, prompt: str) -> JobScore:
        score = self._forced_score if self._forced_score is not None else 62 + _spread(prompt, 34)
        return JobScore(
            score=score,
            gates=[
                ScoreGate(
                    gate="eligibility",
                    status="pass",
                    evidence="The offline provider does not evaluate eligibility; treated as open.",
                ),
                ScoreGate(
                    gate="language",
                    status="pass",
                    evidence="The posting language matches the profile language.",
                ),
            ],
            reasons=[
                "The posting's core stack appears in the candidate's experience.",
                "Seniority in the posting is within one level of the profile.",
            ],
            missing_requirements=["Domain experience the posting names is not evidenced."],
            breakdown=[
                ScoreDimension(
                    dimension=name,  # type: ignore[arg-type]  # names come from the Literal
                    score=max(0, min(100, score + offset)),
                    weight=weight,  # type: ignore[arg-type]  # ditto
                    weight_pct=weight_pct,
                    evidence=f"Offline provider: fixed {name} weighting.",
                )
                for (name, weight, weight_pct), offset in zip(
                    _DIMENSIONS, (6, 0, -4, -8), strict=True
                )
            ],
            recommend_apply=score >= 70,
            summary="Offline provider — a deterministic placeholder, not a real assessment.",
        )

    def _answers(self, prompt: str) -> ScreeningAnswerSet:
        answers: list[ScreeningAnswer] = []
        for question in _questions_in(prompt):
            answer = _rule_answer(question)
            answers.append(
                ScreeningAnswer(
                    question=question.label,
                    answer=answer or "",
                    confidence=(AnswerConfidence.HIGH if answer else AnswerConfidence.LOW),
                    # No rule matched means the stub would be guessing; say so
                    # rather than filling the field with something plausible.
                    needs_review=answer is None,
                    reasoning=(
                        "Offline provider: matched a known question pattern."
                        if answer
                        else "Offline provider has no rule for this question; answer it yourself."
                    ),
                )
            )
        return ScreeningAnswerSet(answers=answers)

    def _resume(self, prompt: str) -> TailoredResume:
        return TailoredResume(
            tailored_markdown=(
                "# Candidate\n\n"
                "## Summary\n"
                "Reordered to lead with the experience this posting asks for first.\n\n"
                "## Experience\n"
                "- Existing role, re-emphasized toward the posting's stated stack.\n\n"
                "_Produced by the offline provider: nothing here is new content._\n"
            ),
            changes=[
                CVChange(
                    section="Summary",
                    action="reordered",
                    detail="Moved the matching experience to the top.",
                ),
                CVChange(
                    section="Experience",
                    action="emphasized",
                    detail="Highlighted the stack the posting names.",
                ),
            ],
            unsupported_requirements=["Anything the posting requires beyond the source resume."],
            summary="Offline provider — structure only, no rewriting.",
        )

    def _review(self, prompt: str) -> DraftReview:
        return DraftReview(
            edits=[],
            critique=[
                ReviewNote(
                    category="missed_keywords",
                    note="Offline provider does not read the posting; check keywords yourself.",
                ),
                ReviewNote(category="company_angle", note="No company research was performed."),
                ReviewNote(category="reframing", note="No reframing was attempted."),
                ReviewNote(category="tone", note="Tone was not evaluated."),
            ],
            coverage=[
                RequirementCoverage(
                    requirement="Reviewed offline",
                    status="missing_have_it",
                    note="Run a real provider for a substantive review.",
                )
            ],
            summary="Offline provider — the draft was not substantively reviewed.",
        )

    # --- free-text capabilities ---------------------------------------------

    def _free_text(self, system: str, prompt: str) -> str:
        lowered = system.lower()
        if "interview" in lowered or "entrevista" in lowered:
            return (
                "## Likely questions\n"
                "- Walk me through the project closest to this role.\n"
                "- Where does your experience fall short of the posting?\n\n"
                "## Your angle\n"
                "- Lead with the overlap; name the gap before they do.\n\n"
                "_Offline provider: generic prep, not grounded in this posting._\n"
            )
        return (
            "Dear hiring team,\n\n"
            "I am applying for this role. My experience covers the stack the posting "
            "names, and I would welcome the chance to go through it with you.\n\n"
            "This letter was produced by the offline provider and should be rewritten "
            "before it is sent.\n\n"
            "Kind regards"
        )

    def _usage(self, prompt: str, output: str) -> Usage:
        # A word count, not a tokenizer: the audit row wants an order of magnitude
        # and the stub must not pull in a tokenizer dependency to provide one.
        return Usage(
            input_tokens=len(prompt.split()),
            output_tokens=len(output.split()),
        )


def _rule_answer(question: _Question) -> str | None:
    """The rule's answer for this question, or None when there is no rule.

    A value the form does not offer is treated as no answer at all: filling a
    select with something outside its options is exactly the silent guess this
    provider must not make.
    """
    answer = next(
        (value for pattern, value in _ANSWER_RULES if pattern.search(question.label)), None
    )
    if answer is None or not question.options:
        return answer
    folded = {option.strip().lower(): option for option in question.options}
    return folded.get(answer.strip().lower())


def _questions_in(prompt: str) -> list[_Question]:
    """Recover the questions the screening prompt listed.

    `build_screening_prompt` emits one JSON object per line — `{"index": 1,
    "question": "...", "type": "...", "options": [...]}` — so that is what is
    parsed. Bullet lines are also accepted because they are the obvious shape a
    future prompt revision would use, and a stub that silently answered nothing
    would look like a working run that drafted no answers.
    """
    questions: list[_Question] = []
    for raw in prompt.splitlines():
        line = raw.strip()
        if not line:
            continue

        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            label = str(payload.get("question") or "").strip()
            if not label:
                continue
            options = payload.get("options")
            questions.append(
                _Question(
                    label=label,
                    options=tuple(str(option) for option in options)
                    if isinstance(options, list)
                    else (),
                )
            )
            continue

        if line.startswith(("-", "*")):
            label = line.lstrip("-* ").strip()
            # Drop a leading "[field-id]" and a trailing "(number, required)".
            label = re.sub(r"^\[[^\]]+\]\s*", "", label)
            label = re.sub(r"\s*\([^()]*\)\s*$", "", label).strip()
            if label:
                questions.append(_Question(label=label))
    return questions


def _spread(text: str, width: int) -> int:
    """A stable 0..width-1 value for `text`, so scores vary but never drift."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return digest[0] % max(1, width)


__all__ = ["STUB_MODEL", "StubProvider"]
