"""What a fit score means: skip or keep, and in which band.

The judgement is separated from the persistence path on purpose. Whether a job
is worth an application is the product's central rule, and it has to be provable
against a `JobScore` alone — no database, no model call, no job row.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.schemas import JobScore

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


@dataclass(frozen=True, slots=True)
class ScoreDecision:
    """What to do with a scored job, and why.

    `verdict` is the numeric band whatever the outcome: a gate-skipped job still
    shows the user how well it otherwise fitted.
    """

    skipped: bool
    skip_reason: str | None
    verdict: str
    failed_gate: str | None


def decide(score: JobScore, *, min_score: int) -> ScoreDecision:
    """Decide whether a scored job is worth surfacing.

    A failed gate is decisive whatever the number says: skipping with the
    posting's own wording beats surfacing a misleading "82" the user would waste
    an application on. Only when every gate holds does the threshold apply.
    """
    verdict = verdict_for(score.score)

    # First failure wins — gates are ordered by the prompt, and one blocking
    # requirement is enough; listing the rest would not change the outcome.
    failed = next((gate for gate in score.gates if gate.status == "fail"), None)
    if failed is not None:
        return ScoreDecision(
            skipped=True,
            skip_reason=f"Gate {failed.gate}: {failed.evidence}"[:_MAX_SKIP_REASON],
            verdict=verdict,
            failed_gate=failed.gate,
        )

    if score.score < min_score:
        return ScoreDecision(
            skipped=True,
            skip_reason=f"Score {score.score} is below the minimum of {min_score}.",
            verdict=verdict,
            failed_gate=None,
        )

    return ScoreDecision(skipped=False, skip_reason=None, verdict=verdict, failed_gate=None)


__all__ = ["VERDICT_BANDS", "ScoreDecision", "decide", "verdict_for"]
