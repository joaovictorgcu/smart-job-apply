"""Deriving one application's resume from the master resume.

The rule is the same one the CV-tailoring prompt is built around, except here it
is structural rather than instructed: **nothing is invented, because nothing is
generated**. Every string this module emits was written by the candidate. All it
decides is *order* and *emphasis* — which experience leads, which of the
candidate's own bullets come first, which of their technologies the posting is
actually asking about.

That is why it lives in `app.domain` next to `scoring.py`: like "is this job
worth applying to", "which of my experience matters for this posting" is a
product rule that has to be provable against plain data — no database, no model
call, no API key. It also means the feature works on a deployment with no
Anthropic key at all, which an AI-only derivation could not claim.

The relevance signal is the technology vocabulary in `app.domain.technologies`:
the terms a posting names, restricted to the known core plus the candidate's own
spellings. Prose about culture and benefits is noise for this question.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.language import fold, squash
from app.domain.technologies import (
    covers,
    job_technologies,
    mentioned_terms,
    mentions,
    position_of,
    spelling_in,
)

# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ProjectEntry:
    """One project inside an experience, as the candidate wrote it."""

    name: str
    description: str = ""
    technologies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExperienceInput:
    """One position on the master resume, decomposed.

    `experience_id` is provenance only. The adaptation copies text; it never
    resolves this id back to a row, which is what keeps a snapshot independent
    of later master edits.
    """

    company: str
    role: str
    experience_id: int | None = None
    location: str | None = None
    employment_type: str | None = None
    started_on: date | None = None
    ended_on: date | None = None
    is_current: bool = False
    summary: str = ""
    responsibilities: tuple[str, ...] = ()
    technologies: tuple[str, ...] = ()
    results: tuple[str, ...] = ()
    projects: tuple[ProjectEntry, ...] = ()
    position: int = 0

    def searchable(self) -> str:
        """Everything this experience says, as one block, for term matching."""
        parts: list[str] = [self.role, self.company, self.summary]
        parts.extend(self.responsibilities)
        parts.extend(self.results)
        parts.extend(self.technologies)
        for project in self.projects:
            parts.append(project.name)
            parts.append(project.description)
            parts.extend(project.technologies)
        return "\n".join(part for part in parts if part)

    def recency_key(self) -> int:
        """Higher is more recent. A current role outranks every finished one."""
        if self.is_current:
            return date.max.toordinal()
        if self.ended_on is not None:
            return self.ended_on.toordinal()
        if self.started_on is not None:
            return self.started_on.toordinal()
        return 0


@dataclass(frozen=True, slots=True)
class MasterResume:
    """The candidate's single source of truth, as the derivation sees it."""

    full_name: str | None = None
    headline: str | None = None
    location: str | None = None
    summary: str | None = None
    years_of_experience: int | None = None
    skills: tuple[str, ...] = ()
    resume_text: str = ""
    experiences: tuple[ExperienceInput, ...] = ()

    def vocabulary(self) -> tuple[str, ...]:
        """The candidate's own technology spellings, most specific source first.

        Fed to `job_technologies` ahead of the known core so that a posting
        naming "Postgres" is reported using the spelling the candidate's resume
        uses, not the vocabulary's.
        """
        seen: dict[str, str] = {}
        for term in (
            *(tech for experience in self.experiences for tech in experience.technologies),
            *(
                tech
                for experience in self.experiences
                for project in experience.projects
                for tech in project.technologies
            ),
            *self.skills,
        ):
            folded = fold(term).strip()
            if folded and folded not in seen:
                seen[folded] = term
        return tuple(seen.values())

    def searchable(self) -> str:
        """Everything the candidate provided anywhere, for coverage checks."""
        parts = [
            self.headline or "",
            self.summary or "",
            self.resume_text or "",
            " ".join(self.skills),
            *(experience.searchable() for experience in self.experiences),
        ]
        return "\n".join(part for part in parts if part.strip())

    def is_empty(self) -> bool:
        """True when there is nothing to adapt — no experience, no skills, no text."""
        return not (self.experiences or self.skills or (self.resume_text or "").strip())


@dataclass(frozen=True, slots=True)
class JobTarget:
    """The posting the resume is being adapted to.

    `priority_terms` is the one input that comes from the candidate rather than
    the posting: the technologies they said they want to lead with. It can only
    ever *reorder* what the posting already asks about — see `_prioritize` —
    so a preference the posting never mentions changes nothing, and a
    preference the candidate does not actually have changes nothing either.
    """

    title: str = ""
    company: str = ""
    description: str = ""
    location: str | None = None
    priority_terms: tuple[str, ...] = ()

    def searchable(self) -> str:
        # The title is repeated deliberately: a term in "Backend .NET Engineer"
        # is the posting's headline requirement, not an aside in paragraph nine,
        # and `job_technologies` orders by first mention.
        return "\n".join(part for part in (self.title, self.title, self.description) if part)


# --------------------------------------------------------------------------- #
# Outputs
# --------------------------------------------------------------------------- #

# The kinds of edit the derivation can report. A closed set, like
# `CVChangeAction`: the review screen renders one labelled group per kind, and a
# free-text kind would make that impossible to translate. There is deliberately
# no "added" kind — adding is the one thing this module cannot do.
CHANGE_KINDS = (
    "experience_prioritized",
    "experience_refocused",
    "skill_highlighted",
    "technology_emphasized",
    "project_selected",
)


@dataclass(frozen=True, slots=True)
class ResumeChange:
    """One reported edit: what moved, and which terms caused it."""

    kind: str
    target: str
    terms: tuple[str, ...] = ()
    # Only meaningful for `experience_refocused`: how many of the experience's
    # own bullets the posting matched, out of how many there are.
    matched: int = 0
    total: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "target": self.target,
            "terms": list(self.terms),
            "matched": self.matched,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class AdaptedExperience:
    """One experience as this application presents it.

    Same facts as the master row, in a different order: `responsibilities` and
    `results` are the candidate's own sentences with the ones this posting asks
    about first, and `technologies` leads with the matched ones. `promoted` says
    how many sentences moved up, which is what makes "the description changed"
    a checkable claim rather than a vibe.
    """

    company: str
    role: str
    experience_id: int | None = None
    location: str | None = None
    employment_type: str | None = None
    started_on: date | None = None
    ended_on: date | None = None
    is_current: bool = False
    summary: str = ""
    responsibilities: tuple[str, ...] = ()
    technologies: tuple[str, ...] = ()
    results: tuple[str, ...] = ()
    projects: tuple[dict[str, Any], ...] = ()
    relevance: int = 0
    matched_terms: tuple[str, ...] = ()
    promoted: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "company": self.company,
            "role": self.role,
            "location": self.location,
            "employment_type": self.employment_type,
            "started_on": self.started_on.isoformat() if self.started_on else None,
            "ended_on": self.ended_on.isoformat() if self.ended_on else None,
            "is_current": self.is_current,
            "summary": self.summary,
            "responsibilities": list(self.responsibilities),
            "technologies": list(self.technologies),
            "results": list(self.results),
            "projects": [dict(project) for project in self.projects],
            "relevance": self.relevance,
            "matched_terms": list(self.matched_terms),
            "promoted": self.promoted,
        }


# The adherence factors and what each is worth. Only factors with a signal are
# scored; the rest are dropped and the remaining weights renormalised, so a
# posting that states no seniority requirement does not silently cost points.
FIT_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("technologies", 40),
    ("experience", 30),
    ("skills", 20),
    ("seniority", 10),
)


@dataclass(frozen=True, slots=True)
class FitFactor:
    """One axis of the adherence number, with the counts behind it.

    Deliberately structured rather than a prose `evidence` string: unlike the
    AI's `ScoreDimension`, this text would be generated here, and generating
    Portuguese prose in the backend when every other user-facing sentence lives
    in the frontend is how two vocabularies start drifting.
    """

    factor: str
    score: int
    weight_pct: int
    matched: int = 0
    total: int = 0
    terms: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor,
            "score": self.score,
            "weight_pct": self.weight_pct,
            "matched": self.matched,
            "total": self.total,
            "terms": list(self.terms),
        }


@dataclass(frozen=True, slots=True)
class AdaptedResume:
    """The finished derivation, ready to be snapshotted onto an application."""

    headline: str | None = None
    summary: str | None = None
    skills: tuple[str, ...] = ()
    highlighted_skills: tuple[str, ...] = ()
    emphasized_technologies: tuple[str, ...] = ()
    experiences: tuple[AdaptedExperience, ...] = ()
    projects: tuple[dict[str, Any], ...] = ()
    changes: tuple[ResumeChange, ...] = ()
    fit_score: int = 0
    fit_factors: tuple[FitFactor, ...] = ()
    uncovered_requirements: tuple[str, ...] = ()
    fingerprint: str = ""


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #

# "5+ anos", "at least 3 years", "mínimo de 4 anos de experiência". Only the
# smallest stated figure is used: a posting asking for "3 to 5 years" is asking
# for three.
_YEARS_REQUIRED = re.compile(r"(\d{1,2})\s*\+?\s*(?:\+\s*)?(?:anos|years)")


def _dedup(terms: Iterable[str]) -> tuple[str, ...]:
    """Drop repeated spellings of the same term, keeping the first seen."""
    seen: dict[str, str] = {}
    for term in terms:
        folded = fold(term).strip()
        if folded and folded not in seen:
            seen[folded] = term
    return tuple(seen.values())


def _drop_subsumed(terms: Sequence[str]) -> tuple[str, ...]:
    """Drop a term another, longer term already contains as a whole term.

    A posting that says "Azure DevOps" names both `azure devops` and `azure` in
    the vocabulary, and counting that as two requirements would inflate the
    denominator of every coverage figure below.

    Whole-term containment, not substring: `java` is a substring of `javascript`
    but not a term inside it, so a posting that really does ask for Java keeps
    it. That distinction is why this uses `position_of` rather than `in`.
    """
    kept: list[str] = []
    for term in terms:
        length = len(fold(term))
        if any(
            len(fold(other)) > length and position_of(other, term) is not None for other in terms
        ):
            continue
        kept.append(term)
    return tuple(kept)


def _reorder_by_relevance(
    lines: Sequence[str], wanted: Sequence[str]
) -> tuple[tuple[str, ...], int]:
    """Sort the candidate's own sentences, most relevant first.

    Nothing is dropped. A resume bullet the posting does not mention is still
    the candidate's experience, and silently deleting it would make the
    application misrepresent them — this is emphasis, not editing. The count
    returned is how many lines matched at least one term, which is what the
    change report quotes.
    """
    if not lines:
        return (), 0
    if not wanted:
        return tuple(lines), 0

    scored: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        hits = len(mentioned_terms(line, wanted))
        # `index` keeps equal scores in the candidate's own order: a stable sort
        # is the difference between "reordered by relevance" and "shuffled".
        scored.append((-hits, index, line))
    scored.sort()
    return tuple(line for _, _, line in scored), sum(1 for hits, _, _ in scored if hits < 0)


def _prioritize(wanted: Sequence[str], priority: Sequence[str]) -> tuple[str, ...]:
    """Move the terms the candidate asked to lead with to the front of `wanted`.

    Reordering only, and deliberately nothing else. A priority term the posting
    never names is not appended — the posting decides what is relevant, and a
    preference only breaks the tie about what to show first. That is why this
    cannot make a resume claim anything new: every term here was already in
    `wanted`, which was itself already the intersection of the posting with the
    candidate's own vocabulary.

    Priorities keep the order the user listed them in; everything else keeps
    the order the posting introduced it in.
    """
    if not priority:
        return tuple(wanted)

    ranks: dict[str, int] = {}
    for rank, term in enumerate(priority):
        key = fold(term).strip()
        if key:
            ranks.setdefault(key, rank)

    leading = [term for term in wanted if fold(term) in ranks]
    if not leading:
        return tuple(wanted)
    leading.sort(key=lambda term: ranks[fold(term)])
    return (*leading, *(term for term in wanted if fold(term) not in ranks))


def _relevance(matched: Sequence[str], wanted: Sequence[str]) -> int:
    """How much of what the posting asks about this experience actually covers."""
    if not wanted:
        return 0
    return round(100 * len(matched) / len(wanted))


def _required_years(text: str) -> int | None:
    """The smallest number of years the posting explicitly asks for, if any."""
    matches = [int(value) for value in _YEARS_REQUIRED.findall(squash(text))]
    plausible = [value for value in matches if 1 <= value <= 30]
    return min(plausible) if plausible else None


def _normalized_weights(factors: Sequence[str]) -> dict[str, int]:
    """Share out 100 points over the factors that have a signal.

    Largest-remainder apportionment, ties broken by the declared order, so the
    same set of factors always produces the same weights — these numbers get
    persisted and rendered as the explanation of the adherence figure.

    Not shared with `app.ai.schemas._rescaled_to_100`: that one repairs
    arithmetic a *model* got wrong in a breakdown it chose, this one distributes
    weights this module declares. Coupling them would tie the domain's rules to
    the AI output contract.
    """
    weights = {name: weight for name, weight in FIT_WEIGHTS if name in set(factors)}
    total = sum(weights.values())
    if not weights or total == 0:
        return dict.fromkeys(weights, 0)

    exact = {name: weight * 100 / total for name, weight in weights.items()}
    floored = {name: int(value) for name, value in exact.items()}
    leftover = 100 - sum(floored.values())
    if leftover > 0:
        order = [name for name, _ in FIT_WEIGHTS if name in floored]
        ranked = sorted(order, key=lambda name: (-(exact[name] - floored[name]), order.index(name)))
        for name in ranked[:leftover]:
            floored[name] += 1
    return floored


def fingerprint(master: MasterResume) -> str:
    """Hash of the master resume a snapshot was derived from.

    Distinct from `app.ai.scoring.profile_fingerprint`, which hashes only the
    free-text profile: that one cannot notice a changed experience bullet, and a
    snapshot going stale because the user rewrote a responsibility is exactly
    the case this has to catch.
    """
    parts: list[str] = [
        master.headline or "",
        master.summary or "",
        master.resume_text or "",
        "|".join(master.skills),
        str(master.years_of_experience or ""),
    ]
    for experience in sorted(
        master.experiences, key=lambda item: (item.experience_id or 0, item.company, item.role)
    ):
        parts.append(
            "".join(
                [
                    experience.company,
                    experience.role,
                    experience.location or "",
                    experience.employment_type or "",
                    experience.started_on.isoformat() if experience.started_on else "",
                    experience.ended_on.isoformat() if experience.ended_on else "",
                    str(experience.is_current),
                    experience.summary,
                    "|".join(experience.responsibilities),
                    "|".join(experience.technologies),
                    "|".join(experience.results),
                    "|".join(
                        f"{project.name}~{project.description}~{'/'.join(project.technologies)}"
                        for project in experience.projects
                    ),
                ]
            )
        )
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()


def adapt(master: MasterResume, job: JobTarget) -> AdaptedResume:
    """Derive the resume this one posting should see.

    Deterministic: the same master and the same posting always produce the same
    document, which is what makes the isolation tests meaningful and what lets
    the change report be trusted as a description of what happened.
    """
    job_text = job.searchable()
    wanted = _prioritize(
        _drop_subsumed(_dedup(job_technologies(job_text, master.vocabulary()))),
        job.priority_terms,
    )
    owned = master.searchable()

    # `covers`, not `mentions`: everything not covered is reported to the user
    # as a requirement their resume cannot back, and "postgres" in the posting
    # against "PostgreSQL" in the resume is not one.
    covered = tuple(term for term in wanted if covers(owned, term))
    # A covered term keeps the candidate's own spelling, which is what belongs in
    # their resume. An uncovered one has no such spelling by definition, so it
    # would otherwise fall back to the lowercase vocabulary and render as
    # "elixir" beside a posting that wrote "Elixir" — take the posting's.
    uncovered = tuple(
        spelling_in(job_text, term) for term in wanted if term not in covered
    )

    ranked = _rank_experiences(master.experiences, wanted)
    highlighted_skills = tuple(skill for skill in master.skills if mentions(job_text, skill))
    skills = tuple(highlighted_skills) + tuple(
        skill for skill in master.skills if skill not in highlighted_skills
    )
    projects = _relevant_projects(ranked, wanted)
    changes = _describe(master.experiences, ranked, highlighted_skills, covered, projects)
    fit_score, fit_factors = _fit(master, job_text, wanted, covered, highlighted_skills, ranked)

    return AdaptedResume(
        headline=master.headline,
        summary=master.summary,
        skills=skills,
        highlighted_skills=highlighted_skills,
        emphasized_technologies=covered,
        experiences=ranked,
        projects=projects,
        changes=changes,
        fit_score=fit_score,
        fit_factors=fit_factors,
        uncovered_requirements=uncovered,
        fingerprint=fingerprint(master),
    )


def _rank_experiences(
    experiences: Sequence[ExperienceInput], wanted: Sequence[str]
) -> tuple[AdaptedExperience, ...]:
    """Score, reorder and refocus every experience for one posting."""
    adapted: list[AdaptedExperience] = []
    for experience in experiences:
        matched = tuple(mentioned_terms(experience.searchable(), wanted))
        responsibilities, promoted_r = _reorder_by_relevance(experience.responsibilities, wanted)
        results, promoted_x = _reorder_by_relevance(experience.results, wanted)
        technologies = _dedup(
            (
                *mentioned_terms(" ".join(experience.technologies), wanted),
                *experience.technologies,
            )
        )
        adapted.append(
            AdaptedExperience(
                experience_id=experience.experience_id,
                company=experience.company,
                role=experience.role,
                location=experience.location,
                employment_type=experience.employment_type,
                started_on=experience.started_on,
                ended_on=experience.ended_on,
                is_current=experience.is_current,
                summary=experience.summary,
                responsibilities=responsibilities,
                technologies=technologies,
                results=results,
                projects=tuple(
                    _project_dict(project, wanted, experience) for project in experience.projects
                ),
                relevance=_relevance(matched, wanted),
                matched_terms=matched,
                promoted=promoted_r + promoted_x,
            )
        )

    # Relevance first, then recency, then the master's own order. Recency is the
    # tiebreak rather than the driver on purpose: for a .NET posting a four-year-old
    # .NET role is worth more than last month's unrelated one, and that inversion
    # is the entire point of adapting.
    order = {id(item): index for index, item in enumerate(experiences)}
    by_key = sorted(
        zip(adapted, experiences, strict=True),
        key=lambda pair: (
            -pair[0].relevance,
            -pair[1].recency_key(),
            pair[1].position,
            order[id(pair[1])],
        ),
    )
    return tuple(item for item, _ in by_key)


def _project_dict(
    project: ProjectEntry, wanted: Sequence[str], experience: ExperienceInput
) -> dict[str, Any]:
    haystack = "\n".join([project.name, project.description, " ".join(project.technologies)])
    matched = mentioned_terms(haystack, wanted)
    return {
        "name": project.name,
        "description": project.description,
        "technologies": list(
            _dedup(
                (*mentioned_terms(" ".join(project.technologies), wanted), *project.technologies)
            )
        ),
        "company": experience.company,
        "role": experience.role,
        "matched_terms": list(matched),
    }


def _relevant_projects(
    experiences: Sequence[AdaptedExperience], wanted: Sequence[str]
) -> tuple[dict[str, Any], ...]:
    """The projects this posting has a reason to see, most relevant first.

    Unlike bullets, projects *are* filtered: a resume lists them as separate
    exhibits, and showing the four unrelated ones alongside the matching one is
    what makes a tailored resume read as untailored. The unmatched ones are
    still on the master resume, one click away.
    """
    if not wanted:
        return ()
    candidates = [
        dict(project)
        for experience in experiences
        for project in experience.projects
        if project.get("matched_terms")
    ]
    candidates.sort(key=lambda project: -len(project.get("matched_terms") or []))
    return tuple(candidates)


def _describe(
    master: Sequence[ExperienceInput],
    ranked: Sequence[AdaptedExperience],
    highlighted_skills: Sequence[str],
    covered: Sequence[str],
    projects: Sequence[dict[str, Any]],
) -> tuple[ResumeChange, ...]:
    """The change report: what moved, and which terms moved it.

    Only real differences are reported. An experience that neither moved nor had
    a single bullet promoted produces no entry, because a change list padded
    with no-ops is a change list nobody reads — the same reason the audit trail
    skips settings updates that changed nothing.
    """
    changes: list[ResumeChange] = []
    original = [f"{item.role} — {item.company}" for item in master]

    for index, item in enumerate(ranked):
        label = f"{item.role} — {item.company}"
        previous = original.index(label) if label in original else index
        if index < previous and item.matched_terms:
            changes.append(
                ResumeChange(
                    kind="experience_prioritized",
                    target=label,
                    terms=tuple(item.matched_terms[:6]),
                )
            )
        total = len(item.responsibilities) + len(item.results)
        if item.promoted and item.promoted < total:
            changes.append(
                ResumeChange(
                    kind="experience_refocused",
                    target=label,
                    terms=tuple(item.matched_terms[:6]),
                    matched=item.promoted,
                    total=total,
                )
            )

    changes.extend(
        ResumeChange(kind="skill_highlighted", target=skill) for skill in highlighted_skills
    )
    changes.extend(ResumeChange(kind="technology_emphasized", target=term) for term in covered)
    changes.extend(
        ResumeChange(
            kind="project_selected",
            target=str(project.get("name") or ""),
            terms=tuple(str(term) for term in (project.get("matched_terms") or [])),
        )
        for project in projects
    )
    return tuple(changes)


def _fit(
    master: MasterResume,
    job_text: str,
    wanted: Sequence[str],
    covered: Sequence[str],
    highlighted_skills: Sequence[str],
    ranked: Sequence[AdaptedExperience],
) -> tuple[int, tuple[FitFactor, ...]]:
    """Adherence between the profile and the posting, and why.

    Returns `(0, ())` when the posting names nothing this module can recognise.
    A percentage computed from no signal is worse than no percentage: the UI
    hides the figure entirely rather than showing a confident-looking zero.
    """
    if not wanted:
        return 0, ()

    scores: dict[str, tuple[int, int, int, tuple[str, ...]]] = {
        "technologies": (
            round(100 * len(covered) / len(wanted)),
            len(covered),
            len(wanted),
            tuple(covered[:8]),
        )
    }

    if ranked:
        best = max(ranked, key=lambda item: item.relevance)
        scores["experience"] = (
            best.relevance,
            len(best.matched_terms),
            len(wanted),
            tuple(best.matched_terms[:8]),
        )

    if master.skills:
        scores["skills"] = (
            min(100, round(100 * len(highlighted_skills) / len(wanted))),
            len(highlighted_skills),
            len(wanted),
            tuple(highlighted_skills[:8]),
        )

    required = _required_years(job_text)
    if required is not None and master.years_of_experience is not None:
        years = master.years_of_experience
        scores["seniority"] = (
            100 if years >= required else round(100 * years / required),
            years,
            required,
            (),
        )

    weights = _normalized_weights(list(scores))
    factors = tuple(
        FitFactor(
            factor=name,
            score=scores[name][0],
            weight_pct=weights.get(name, 0),
            matched=scores[name][1],
            total=scores[name][2],
            terms=scores[name][3],
        )
        for name, _ in FIT_WEIGHTS
        if name in scores
    )
    overall = round(sum(factor.score * factor.weight_pct for factor in factors) / 100)
    return max(0, min(100, overall)), factors


__all__ = [
    "CHANGE_KINDS",
    "FIT_WEIGHTS",
    "AdaptedExperience",
    "AdaptedResume",
    "ExperienceInput",
    "FitFactor",
    "JobTarget",
    "MasterResume",
    "ProjectEntry",
    "ResumeChange",
    "adapt",
    "fingerprint",
]
