"""What a fit score means: skip or keep, and in which band.

The judgement is separated from the persistence path on purpose. Whether a job
is worth an application is the product's central rule, and it has to be provable
against a `JobScore` alone — no database, no model call, no job row.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.schemas import JobScore, ScoreDimension

# Inherited from the reference project's evaluation framework. The bands exist
# so the UI has a stable vocabulary for a bare number: an "82" means nothing on
# its own, and moving a boundary silently rewrites what every past score claimed.
VERDICT_BANDS: tuple[tuple[str, int], ...] = (
    ("strong", 75),
    ("good", 60),
    ("moderate", 45),
    ("weak", 30),
    ("poor", 0),
)

# `Job.skip_reason` is a bounded column rendered in a single list cell; a gate's
# evidence is the posting's own wording and can run for paragraphs.
_MAX_SKIP_REASON = 300


def verdict_for(score: int) -> str:
    """Name the band a numeric score falls in."""
    for verdict, floor in VERDICT_BANDS:
        if score >= floor:
            return verdict
    # Unreachable for a schema-clamped 0-100 score; keeps a negative caller sane.
    return VERDICT_BANDS[-1][0]


def weighted_score(breakdown: Sequence[ScoreDimension]) -> int | None:
    """Recompute the headline score from the breakdown that is supposed to explain it.

    This is the whole point of `weight_pct`: an "82" nobody can reproduce is a
    number taken on faith, and a number taken on faith cannot be argued with.

    Returns `None` when there is nothing to recompute from — an empty breakdown,
    or one whose weights are all zero. The latter is how breakdowns persisted
    before `weight_pct` existed read back, and treating them as equally weighted
    would put a number on the screen that the model never produced. "Not
    derivable" is the honest answer for those rows.

    Divides by the actual weight total rather than by 100: fresh scores come
    through `JobScore`, which normalises the sum, but stored rows bypass that
    validator and a partial breakdown must still average correctly.
    """
    if not breakdown:
        return None

    total_weight = sum(dimension.weight_pct for dimension in breakdown)
    if total_weight <= 0:
        return None

    weighted = sum(dimension.score * dimension.weight_pct for dimension in breakdown)
    # Half-up, not `round()`: banker's rounding would send an exact 82.5 to 82
    # while a user reading the arithmetic expects 83.
    return int(weighted / total_weight + 0.5)


@dataclass(frozen=True, slots=True)
class ScoreDecision:
    """What to do with a scored job, and why.

    `verdict` is the numeric band whatever the outcome: a gate-skipped job still
    shows the user how well it otherwise fitted.

    `weighted` is the score its own breakdown adds up to, and `divergence` is how
    far the headline score sits from it (overall minus weighted). Both default to
    `None` for a breakdown that cannot be recomputed.
    """

    skipped: bool
    skip_reason: str | None
    verdict: str
    failed_gate: str | None
    weighted: int | None = None
    divergence: int | None = None


def decide(score: JobScore, *, min_score: int) -> ScoreDecision:
    """Decide whether a scored job is worth surfacing.

    A failed gate is decisive whatever the number says: skipping with the
    posting's own wording beats surfacing a misleading "82" the user would waste
    an application on. Only when every gate holds does the threshold apply.

    `divergence` is reported, never applied. The threshold below compares the
    model's own `score`, not the recomputed one, because a model whose breakdown
    contradicts its headline number is telling the user something about the
    quality of that judgement — and silently substituting the arithmetic would
    hide it while pretending to fix it. Which of the two numbers is wrong is not
    knowable from here; that the two disagree is, and that is what gets surfaced.
    """
    verdict = verdict_for(score.score)
    weighted = weighted_score(score.breakdown)
    divergence = None if weighted is None else score.score - weighted

    # First failure wins — gates are ordered by the prompt, and one blocking
    # requirement is enough; listing the rest would not change the outcome.
    failed = next((gate for gate in score.gates if gate.status == "fail"), None)
    if failed is not None:
        return ScoreDecision(
            skipped=True,
            skip_reason=f"Gate {failed.gate}: {failed.evidence}"[:_MAX_SKIP_REASON],
            verdict=verdict,
            failed_gate=failed.gate,
            weighted=weighted,
            divergence=divergence,
        )

    if score.score < min_score:
        return ScoreDecision(
            skipped=True,
            skip_reason=f"Score {score.score} is below the minimum of {min_score}.",
            verdict=verdict,
            failed_gate=None,
            weighted=weighted,
            divergence=divergence,
        )

    return ScoreDecision(
        skipped=False,
        skip_reason=None,
        verdict=verdict,
        failed_gate=None,
        weighted=weighted,
        divergence=divergence,
    )


__all__ = ["VERDICT_BANDS", "ScoreDecision", "decide", "verdict_for", "weighted_score"]
