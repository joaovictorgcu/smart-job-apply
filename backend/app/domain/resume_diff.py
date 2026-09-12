"""Your resume, and the one this vacancy gets — side by side.

The derivation already reports *that* it reorganised something
(`app.domain.resume.ResumeChange`). What a reviewer actually needs before
approving is narrower and more checkable: which experience moved from third to
first, which technologies came forward, how many sentences were promoted — and,
above all, **how few** edits there were.

That last part is the product rule this module exists to make visible. An
adapted resume has to still read as the same document. So the comparison ends
in a budget the reviewer can check at a glance:

    3 alterações · 2 tecnologias destacadas · 1 trecho ajustado · 0 invenções

The fourth number is not an assumption. `invented` is computed by running the
invention guard over the adapted document against the master's own words, so a
zero there is a measurement rather than a promise — and a non-zero one is the
signal to stop and read.

Pure: two documents in, counts and moves out. No database, no model call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.domain.language import fold
from app.domain.technologies import flag_unsupported_skills

# Terms named in a single "moved forward" line. Past this the line stops being
# a summary of what changed and becomes the list itself.
MAX_NAMED_TERMS = 6


@dataclass(frozen=True, slots=True)
class SnapshotExperience:
    """One position as an application's stored copy presents it.

    Deliberately a plain shape rather than the ORM row or the response model:
    what is stored is JSON, and the comparison has to work on exactly that.
    """

    experience_id: int | None = None
    company: str = ""
    role: str = ""
    summary: str = ""
    responsibilities: tuple[str, ...] = ()
    technologies: tuple[str, ...] = ()
    results: tuple[str, ...] = ()
    matched_terms: tuple[str, ...] = ()
    promoted: int = 0


@dataclass(frozen=True, slots=True)
class Snapshot:
    """The document one application presents, as stored."""

    summary: str = ""
    skills: tuple[str, ...] = ()
    emphasized_technologies: tuple[str, ...] = ()
    experiences: tuple[SnapshotExperience, ...] = ()

    def searchable(self) -> str:
        """Every word this document renders, for the invention guard."""
        parts: list[str] = [self.summary, *self.skills, *self.emphasized_technologies]
        for experience in self.experiences:
            parts += [experience.company, experience.role, experience.summary]
            parts += experience.responsibilities
            parts += experience.technologies
            parts += experience.results
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class ExperienceMove:
    """One position that changed place, and why.

    Positions are 1-based, because they are read as "3ª → 1ª" and nobody counts
    their own CV from zero.
    """

    experience_id: int | None
    company: str
    role: str
    from_position: int
    to_position: int
    promoted_bullets: int = 0
    matched_terms: tuple[str, ...] = ()

    @property
    def moved(self) -> bool:
        return self.from_position != self.to_position


@dataclass(frozen=True, slots=True)
class ResumeComparison:
    """What separates the master resume from this application's copy.

    `is_comparable` is false when the copy was derived from a different master
    than the one being compared against — the user edited their profile
    afterwards. The diff would then attribute their own edits to the
    adaptation, which is worse than showing nothing and saying why.
    """

    moves: tuple[ExperienceMove, ...] = ()
    highlighted_technologies: tuple[str, ...] = ()
    promoted_bullets: int = 0
    # Terms in the adapted document that the master's own words cannot back.
    # Expected empty, measured rather than assumed.
    invented: tuple[str, ...] = field(default_factory=tuple)
    is_comparable: bool = True

    @property
    def experiences_reordered(self) -> int:
        return sum(1 for move in self.moves if move.moved)

    @property
    def sections_adjusted(self) -> int:
        """Positions whose own sentences were reordered inside them."""
        return sum(1 for move in self.moves if move.promoted_bullets > 0)

    @property
    def changes_total(self) -> int:
        """The headline number: how many distinct edits this copy carries."""
        return (
            self.experiences_reordered
            + len(self.highlighted_technologies)
            + self.sections_adjusted
        )

    @property
    def is_clean(self) -> bool:
        """Nothing in the copy that the master cannot back."""
        return not self.invented


def _moved_forward(master_order: Sequence[str], adapted_order: Sequence[str]) -> tuple[str, ...]:
    """Terms the adapted document lists earlier than the master does.

    Only forward moves count. A term that slipped down did so because another
    one came up, and reporting both would double every highlight.
    """
    positions = {fold(term): index for index, term in enumerate(master_order)}
    forward: list[str] = []
    for index, term in enumerate(adapted_order):
        previous = positions.get(fold(term))
        if previous is not None and index < previous:
            forward.append(term)
    return tuple(forward[:MAX_NAMED_TERMS])


def compare(
    *,
    master_experience_ids: Sequence[int | None],
    master_skills: Sequence[str],
    master_text: str,
    snapshot: Snapshot,
    is_comparable: bool = True,
) -> ResumeComparison:
    """Diff one application's copy against the master it came from.

    `master_experience_ids` is the master's own display order; the copy's
    `experience_id` values are matched against it, which is why the derivation
    keeps that id for provenance even though it never dereferences it.

    A position the master no longer has is skipped rather than reported as a
    move: it was deleted from the profile after this copy was frozen, and the
    copy keeping it is the documented behaviour, not a change the adaptation
    made.
    """
    if not is_comparable:
        return ResumeComparison(is_comparable=False)

    order = {value: index for index, value in enumerate(master_experience_ids) if value is not None}

    moves: list[ExperienceMove] = []
    for index, experience in enumerate(snapshot.experiences):
        previous = order.get(experience.experience_id) if experience.experience_id else None
        if previous is None:
            continue
        moves.append(
            ExperienceMove(
                experience_id=experience.experience_id,
                company=experience.company,
                role=experience.role,
                from_position=previous + 1,
                to_position=index + 1,
                promoted_bullets=experience.promoted,
                matched_terms=experience.matched_terms[:MAX_NAMED_TERMS],
            )
        )

    highlighted = _moved_forward(master_skills, snapshot.skills)
    promoted = sum(experience.promoted for experience in snapshot.experiences)
    invented = tuple(flag_unsupported_skills(master_text, snapshot.searchable()))

    return ResumeComparison(
        moves=tuple(moves),
        highlighted_technologies=highlighted,
        promoted_bullets=promoted,
        invented=invented,
        is_comparable=True,
    )


__all__ = [
    "MAX_NAMED_TERMS",
    "ExperienceMove",
    "ResumeComparison",
    "Snapshot",
    "SnapshotExperience",
    "compare",
]
