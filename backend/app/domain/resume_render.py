"""The adapted resume as an ordered document, ready to be drawn.

Splitting this from the drawing is the point. *What the page says* — which
sections, in which order, with which lines under which heading — is a product
decision that has to be checkable without a PDF library, a font or a byte
comparison. *How it looks* is one replaceable adapter (`app.services.resume_pdf`).

So this module emits blocks and nothing else. It has no idea what a point size
is, and a test can assert "the first technology this posting asked about leads
the skills line" by reading a tuple.

The rule the rest of the resume code obeys applies here unchanged: every string
emitted comes from the stored snapshot, which came from the candidate's own
master resume. This module joins and orders. It never writes a new fact.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.domain.resume_diff import Snapshot, SnapshotExperience

BlockKind = Literal[
    "name", "headline", "contact", "heading", "paragraph", "entry", "bullet", "terms"
]

# Bullets kept under one position. A resume that runs past this stops being read;
# the ranking already put the ones this posting asks about first, so the tail is
# the least relevant part of the least relevant experience.
MAX_BULLETS_PER_ENTRY = 6
# Technologies printed on one line. Past this it reads as a keyword dump.
MAX_TERMS_PER_LINE = 12

_MONTHS_PT: tuple[str, ...] = (
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
)


@dataclass(frozen=True, slots=True)
class Block:
    """One thing to draw, named by what it is rather than by how it looks."""

    kind: BlockKind
    text: str = ""
    items: tuple[str, ...] = ()


def month_year(value: date | None) -> str:
    """A date as a resume prints it: "mar 2023"."""
    if value is None:
        return ""
    return f"{_MONTHS_PT[value.month - 1]} {value.year}"


def period_text(started_on: date | None, ended_on: date | None, is_current: bool) -> str:
    """The period between two dates, in the wording a reader expects.

    "atual" rather than an empty right-hand side: a range that trails off reads
    as missing data, and this is a fact the candidate stated.
    """
    start = month_year(started_on)
    if is_current:
        return f"{start} — atual" if start else "atual"
    end = month_year(ended_on)
    if start and end:
        return f"{start} — {end}"
    return start or end


def _entry_title(experience: SnapshotExperience) -> str:
    parts = [part for part in (experience.role, experience.company) if part.strip()]
    return " — ".join(parts)


def _entry_meta(experience: SnapshotExperience) -> str:
    parts = [part for part in (experience.period, experience.location or "") if part.strip()]
    return " · ".join(parts)


def _experience_blocks(experience: SnapshotExperience) -> list[Block]:
    blocks: list[Block] = []
    title = _entry_title(experience)
    if not title:
        # A position with neither a role nor an employer is not a position. It
        # cannot be drawn honestly, so it is left out rather than printed blank.
        return blocks

    blocks.append(Block(kind="entry", text=title, items=(_entry_meta(experience),)))
    if experience.summary.strip():
        blocks.append(Block(kind="paragraph", text=experience.summary.strip()))

    # Results before responsibilities: a measured outcome is what a reader stops
    # on, and the ranking has already put the relevant ones first inside each.
    lines = [line for line in (*experience.results, *experience.responsibilities) if line.strip()]
    for line in lines[:MAX_BULLETS_PER_ENTRY]:
        blocks.append(Block(kind="bullet", text=line.strip()))

    if experience.technologies:
        blocks.append(
            Block(kind="terms", items=tuple(experience.technologies[:MAX_TERMS_PER_LINE]))
        )
    return blocks


def render_blocks(
    snapshot: Snapshot,
    *,
    full_name: str | None = None,
    headline: str | None = None,
    contact: Sequence[str] = (),
) -> tuple[Block, ...]:
    """The adapted resume as an ordered document.

    Sections appear only when they have content: a candidate with no projects
    gets no "Projetos" heading, rather than a heading over nothing.
    """
    blocks: list[Block] = []

    if full_name and full_name.strip():
        blocks.append(Block(kind="name", text=full_name.strip()))
    if headline and headline.strip():
        blocks.append(Block(kind="headline", text=headline.strip()))
    lines = tuple(item.strip() for item in contact if item and item.strip())
    if lines:
        blocks.append(Block(kind="contact", items=lines))

    if snapshot.summary.strip():
        blocks.append(Block(kind="heading", text="Resumo"))
        blocks.append(Block(kind="paragraph", text=snapshot.summary.strip()))

    if snapshot.skills:
        blocks.append(Block(kind="heading", text="Tecnologias"))
        blocks.append(Block(kind="terms", items=tuple(snapshot.skills[:MAX_TERMS_PER_LINE])))

    entries = [block for item in snapshot.experiences for block in _experience_blocks(item)]
    if entries:
        blocks.append(Block(kind="heading", text="Experiência"))
        blocks.extend(entries)

    return tuple(blocks)


def plain_text(blocks: Sequence[Block]) -> str:
    """The same document as text — what the guard reads, and what a test asserts."""
    lines: list[str] = []
    for block in blocks:
        if block.items and not block.text:
            lines.append(", ".join(block.items))
        elif block.items:
            lines.append(f"{block.text} · {' · '.join(item for item in block.items if item)}")
        elif block.text:
            lines.append(block.text)
    return "\n".join(line for line in lines if line.strip())


__all__ = [
    "MAX_BULLETS_PER_ENTRY",
    "MAX_TERMS_PER_LINE",
    "Block",
    "BlockKind",
    "month_year",
    "period_text",
    "plain_text",
    "render_blocks",
]
