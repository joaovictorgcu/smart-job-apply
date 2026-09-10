"""Why this vacancy — in terms the reader can check against their own resume.

A score is a number somebody has to take on faith. What makes it actionable is
the two lists underneath it: what the posting asks for that you already have,
and what it asks for that you do not. A reader can argue with those. They
cannot argue with "82".

Both lists come out of the same intersection the resume derivation uses
(`app.domain.technologies`), which is what keeps the recommendation and the
adapted resume telling the same story: a term shown as covered here is a term
that gets emphasised there.

**No prose.** This returns terms and counts, and the sentence is composed in
the frontend — the same rule `app.schemas.resume` states for the adaptation
report. The whole UI vocabulary lives in `frontend/src`, and generating
Portuguese here would be a second wording to keep in step with the first.

Deterministic and offline: it re-reads a stored score, it never asks for one.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.language import fold
from app.domain.scoring import verdict_for
from app.domain.technologies import covers, job_technologies, owned_spelling, spelling_in

# Chips on a job card. Past this the row stops being scannable, and the point of
# the list is that it is read at a glance.
MAX_TERMS = 8


@dataclass(frozen=True, slots=True)
class Recommendation:
    """What this posting asks for, split by what the candidate can back.

    `covered` keeps the candidate's own spelling — those terms belong to them.
    `missing` keeps the posting's, because by definition the candidate has no
    spelling for a technology they never wrote down.
    """

    verdict: str
    score: int | None = None
    covered: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    # Terms in `covered` the user asked to lead with. A subset, never an
    # addition: a priority the posting does not ask about appears nowhere.
    prioritized: tuple[str, ...] = ()
    # Whole counts, before the display cap, so a "5 of 7" reads honestly even
    # when only the first few chips are shown.
    covered_total: int = 0
    asked_total: int = 0

    @property
    def coverage_pct(self) -> int:
        """Share of what the posting names that the resume can back."""
        if self.asked_total <= 0:
            return 0
        return round(100 * self.covered_total / self.asked_total)

    @property
    def has_evidence(self) -> bool:
        """False when the posting named nothing we can reason about.

        A posting written entirely in prose about culture yields no terms, and
        an empty two-column list would read as "you match nothing" rather than
        "there was nothing to compare".
        """
        return self.asked_total > 0


def _priority_ranks(priority: Iterable[str]) -> dict[str, int]:
    """Where each stated priority sits in the user's own ordering."""
    ranks: dict[str, int] = {}
    for rank, term in enumerate(priority):
        key = fold(term or "").strip()
        if key:
            ranks.setdefault(key, rank)
    return ranks


def build(
    *,
    score: int | None,
    title: str,
    description: str | None,
    resume_text: str,
    vocabulary: Sequence[str] = (),
    priority: Iterable[str] = (),
) -> Recommendation:
    """Split what one posting asks for into covered and missing.

    `vocabulary` is the candidate's own technology spellings, passed ahead of
    the known core so a posting saying "Postgres" is reported the way their
    resume says it. `resume_text` is everything they wrote — the flattened
    master resume, not just its skills list — because a technology named only
    inside an achievement is still one they genuinely claim.

    The posting's *title and description* are the only inputs on the job side.
    Nothing from a model's own prose is trusted here: this list has to be
    checkable against the two documents the user can open.
    """
    verdict = verdict_for(score if score is not None else 0)
    posting_text = "\n".join(part for part in (title or "", title or "", description or "") if part)
    if not posting_text.strip():
        return Recommendation(verdict=verdict, score=score)

    asked = job_technologies(posting_text, vocabulary)
    # `covers`, not `mentions`: a miss here is shown to the user as something
    # they lack, and "postgres" in the posting against "PostgreSQL" in the
    # resume is not a gap. The split is decided on the posting's terms and only
    # then re-spelled, so the two sides cannot disagree about a term's identity.
    is_covered = {term: covers(resume_text, term) for term in asked}
    covered = tuple(owned_spelling(resume_text, term) for term in asked if is_covered[term])
    missing = tuple(spelling_in(posting_text, term) for term in asked if not is_covered[term])

    ranks = _priority_ranks(priority)
    # A priority term leads the covered list, in the order the user listed them:
    # it is what they said they want read first, and it is already something
    # this posting asks about.
    prioritized = tuple(
        sorted((term for term in covered if fold(term) in ranks), key=lambda t: ranks[fold(t)])
    )
    ordered_covered = (
        *prioritized,
        *(term for term in covered if fold(term) not in ranks),
    )

    return Recommendation(
        verdict=verdict,
        score=score,
        covered=ordered_covered[:MAX_TERMS],
        missing=missing[:MAX_TERMS],
        prioritized=prioritized[:MAX_TERMS],
        covered_total=len(covered),
        asked_total=len(asked),
    )


__all__ = ["MAX_TERMS", "Recommendation", "build"]
