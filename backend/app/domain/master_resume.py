"""The master resume, and how one application's version of it is derived.

The feature this module exists for: one candidate, N applications, and a resume
per application that is visibly adapted to its posting — experiences reordered
and re-described, skills re-prioritised, relevant projects pulled forward.

Two decisions shape everything here.

**It is deterministic and offline.** No API key, no model call, no network. A
personalised resume is a *selection and ordering* problem over data the candidate
already wrote, and selection is something code can do exactly, repeatably and for
free. The AI layer still gets to polish the rendered prose (see
`app.services.tailoring_service`), but the structure the UI shows — which
experiences were chosen, which skills were promoted, which technologies matched —
is computed here and is identical on every run. That is also what makes the
behaviour testable ("five postings, five different resumes") instead of a
property of whichever model happened to answer.

**It cannot invent.** Every sentence in a derived resume is a sentence the
candidate wrote in their master resume; every technology named is one their own
entry lists. The engine chooses *which* of the candidate's own words to lead
with, and never writes a new claim. This is not a stylistic preference: a resume
that grows a skill its owner lacks fails the interview and burns the
relationship, and `app.ai.client.flag_unsupported_skills` still runs over the
output precisely because "the generator promised not to" is not evidence.

A master experience therefore carries *several* pre-written highlights, each
tagged with the technologies it covers. The same experience honestly reads
differently for a .NET backend posting and for a React full-stack one, because a
different subset of its own highlights leads.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from app.domain.language import detect_language, fold
from app.domain.technologies import (
    job_technologies,
    mentioned_terms,
    mentions,
    position_of,
)

# How central an experience is to one posting. Ordering, not filtering: a
# `context` entry still appears, because dropping employment history silently is
# how a tailored resume turns into a misleading one.
Emphasis = Literal["lead", "support", "context"]

# A title match is worth far more than a body match: a posting's title is the one
# line that states what the role *is*, while its body also lists the stack of the
# team next door. The exact ratio does not matter; the ordering it produces does.
_TITLE_WEIGHT = 8
_BODY_WEIGHT = 1

# Relevance, as a percentage of the strongest entry in this version, at or above
# which an experience is presented as leading it rather than supporting it.
_LEAD_THRESHOLD = 60
# Below this, an entry technically shares a term with the posting but not enough
# of one to call it support — one incidental keyword out of a dozen. It is still
# shown, labelled as context, because a resume that hides employment history to
# look focused is a resume that lies.
_SUPPORT_THRESHOLD = 15

# Seniority words, most specific first — "tech lead" must win over "senior".
# Matched against a folded haystack, so accents are already gone: "sênior" and
# "júnior" arrive here as "senior" and "junior".
_LEVELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("lead", ("tech lead", "team lead", "staff", "principal", "lider tecnico")),
    ("senior", ("senior", "sr.", "especialista")),
    ("mid", ("pleno", "mid-level", "mid level", "intermediate")),
    ("junior", ("junior", "jr.", "trainee", "estagio", "entry level")),
)

_HEADINGS: dict[str, dict[str, str]] = {
    "pt": {
        "focus": "Foco desta versão",
        "skills": "Competências",
        "experience": "Experiência profissional",
        "projects": "Projetos",
        "education": "Formação",
        "certifications": "Certificações",
        "prioritised": "Priorizadas para esta vaga",
        "other": "Demais competências",
    },
    "en": {
        "focus": "Focus of this version",
        "skills": "Skills",
        "experience": "Professional experience",
        "projects": "Projects",
        "education": "Education",
        "certifications": "Certifications",
        "prioritised": "Prioritised for this role",
        "other": "Other skills",
    },
}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _string_list(value: Any) -> tuple[str, ...]:
    """A tolerant list-of-strings reader for JSON columns written by anyone."""
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, Iterable):
        return tuple(_text(item) for item in value if _text(item))
    return ()


# --------------------------------------------------------------------------- #
# The master resume
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Highlight:
    """One achievement the candidate wrote, and the technologies it covers.

    `technologies` is what makes selection possible without a model: it is the
    candidate's own statement of what this bullet is about, so choosing between
    two of their bullets never requires guessing at their meaning.
    """

    text: str
    technologies: tuple[str, ...] = ()

    @classmethod
    def parse(cls, raw: Any) -> Highlight | None:
        if isinstance(raw, str):
            text = _text(raw)
            return cls(text=text) if text else None
        if isinstance(raw, Mapping):
            text = _text(raw.get("text"))
            if not text:
                return None
            return cls(text=text, technologies=_string_list(raw.get("technologies")))
        return None

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "technologies": list(self.technologies)}

    @property
    def haystack(self) -> str:
        return " ".join((self.text, *self.technologies))


@dataclass(frozen=True, slots=True)
class Experience:
    """One job the candidate held. Identity fields are never rewritten."""

    id: str
    role: str
    company: str
    start: str = ""
    end: str = ""
    location: str = ""
    # The neutral description, used when a posting matches none of the highlights.
    summary: str = ""
    highlights: tuple[Highlight, ...] = ()
    technologies: tuple[str, ...] = ()

    @classmethod
    def parse(cls, raw: Any, *, index: int = 0) -> Experience | None:
        if not isinstance(raw, Mapping):
            return None
        role = _text(raw.get("role")) or _text(raw.get("title"))
        company = _text(raw.get("company"))
        if not (role or company):
            return None
        highlights = tuple(
            parsed
            for parsed in (Highlight.parse(item) for item in raw.get("highlights") or ())
            if parsed is not None
        )
        return cls(
            id=_text(raw.get("id")) or f"exp-{index + 1}",
            role=role,
            company=company,
            start=_text(raw.get("start")),
            end=_text(raw.get("end")),
            location=_text(raw.get("location")),
            summary=_text(raw.get("summary")) or _text(raw.get("description")),
            highlights=highlights,
            technologies=_string_list(raw.get("technologies")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "company": self.company,
            "start": self.start,
            "end": self.end,
            "location": self.location,
            "summary": self.summary,
            "highlights": [highlight.as_dict() for highlight in self.highlights],
            "technologies": list(self.technologies),
        }

    @property
    def period(self) -> str:
        if self.start and self.end:
            return f"{self.start} — {self.end}"
        return self.start or self.end

    @property
    def haystack(self) -> str:
        return " ".join(
            (
                self.role,
                self.summary,
                *self.technologies,
                *(highlight.haystack for highlight in self.highlights),
            )
        )


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    description: str = ""
    outcome: str = ""
    technologies: tuple[str, ...] = ()

    @classmethod
    def parse(cls, raw: Any, *, index: int = 0) -> Project | None:
        if not isinstance(raw, Mapping):
            return None
        name = _text(raw.get("name")) or _text(raw.get("title"))
        if not name:
            return None
        return cls(
            id=_text(raw.get("id")) or f"proj-{index + 1}",
            name=name,
            description=_text(raw.get("description")),
            outcome=_text(raw.get("outcome")),
            technologies=_string_list(raw.get("technologies")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "outcome": self.outcome,
            "technologies": list(self.technologies),
        }

    @property
    def haystack(self) -> str:
        return " ".join((self.name, self.description, self.outcome, *self.technologies))


@dataclass(frozen=True, slots=True)
class Education:
    id: str
    degree: str
    institution: str = ""
    start: str = ""
    end: str = ""
    detail: str = ""

    @classmethod
    def parse(cls, raw: Any, *, index: int = 0) -> Education | None:
        if not isinstance(raw, Mapping):
            return None
        degree = _text(raw.get("degree")) or _text(raw.get("title"))
        institution = _text(raw.get("institution")) or _text(raw.get("school"))
        if not (degree or institution):
            return None
        return cls(
            id=_text(raw.get("id")) or f"edu-{index + 1}",
            degree=degree,
            institution=institution,
            start=_text(raw.get("start")),
            end=_text(raw.get("end")),
            detail=_text(raw.get("detail")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "degree": self.degree,
            "institution": self.institution,
            "start": self.start,
            "end": self.end,
            "detail": self.detail,
        }

    @property
    def period(self) -> str:
        if self.start and self.end:
            return f"{self.start} — {self.end}"
        return self.start or self.end


@dataclass(frozen=True, slots=True)
class MasterResume:
    """Everything the candidate maintains once, in one place.

    `resume_text` is the original free-text resume and stays authoritative for
    the AI path and for the invention guard. The structured lists are what make
    per-application derivation possible; a profile with none of them still
    derives, it just has less to reorder.
    """

    full_name: str = ""
    headline: str = ""
    location: str = ""
    summary: str = ""
    years_of_experience: int | None = None
    skills: tuple[str, ...] = ()
    experiences: tuple[Experience, ...] = ()
    projects: tuple[Project, ...] = ()
    education: tuple[Education, ...] = ()
    certifications: tuple[str, ...] = ()
    resume_text: str = ""

    @classmethod
    def from_profile(cls, profile: Any) -> MasterResume:
        """Read a `ProfileContext` (or anything carrying the same attributes)."""
        return cls(
            full_name=_text(getattr(profile, "full_name", "")),
            headline=_text(getattr(profile, "headline", "")),
            location=_text(getattr(profile, "location", "")),
            summary=_text(getattr(profile, "summary", "")),
            years_of_experience=getattr(profile, "years_of_experience", None),
            skills=_string_list(getattr(profile, "skills", ())),
            experiences=tuple(
                parsed
                for parsed in (
                    Experience.parse(raw, index=index)
                    for index, raw in enumerate(getattr(profile, "experiences", ()) or ())
                )
                if parsed is not None
            ),
            projects=tuple(
                parsed
                for parsed in (
                    Project.parse(raw, index=index)
                    for index, raw in enumerate(getattr(profile, "projects", ()) or ())
                )
                if parsed is not None
            ),
            education=tuple(
                parsed
                for parsed in (
                    Education.parse(raw, index=index)
                    for index, raw in enumerate(getattr(profile, "education", ()) or ())
                )
                if parsed is not None
            ),
            certifications=_string_list(getattr(profile, "certifications", ())),
            resume_text=_text(getattr(profile, "resume_text", "")),
        )

    def as_dict(self) -> dict[str, Any]:
        """The snapshot frozen onto a derived resume. See `derive`'s docstring."""
        return {
            "full_name": self.full_name,
            "headline": self.headline,
            "location": self.location,
            "summary": self.summary,
            "years_of_experience": self.years_of_experience,
            "skills": list(self.skills),
            "experiences": [experience.as_dict() for experience in self.experiences],
            "projects": [project.as_dict() for project in self.projects],
            "education": [entry.as_dict() for entry in self.education],
            "certifications": list(self.certifications),
            "resume_text": self.resume_text,
        }

    @property
    def is_empty(self) -> bool:
        """Nothing to derive from: no free text, no structure, no skills."""
        return not (self.resume_text or self.experiences or self.skills or self.projects)

    @property
    def vocabulary(self) -> tuple[str, ...]:
        """Every technology the candidate claims, in their own spelling.

        Skills first, so "PostgreSQL" as the user typed it wins over a
        lower-cased dictionary entry when both would match a posting.
        """
        seen: dict[str, str] = {}
        for term in (
            *self.skills,
            *(tech for experience in self.experiences for tech in experience.technologies),
            *(
                tech
                for experience in self.experiences
                for highlight in experience.highlights
                for tech in highlight.technologies
            ),
            *(tech for project in self.projects for tech in project.technologies),
        ):
            seen.setdefault(fold(term), term)
        return tuple(seen.values())

    @property
    def structured_text(self) -> str:
        """The structured half of the master resume, flattened.

        Kept separate from `source_text` so `app.ai.scoring.profile_source_text`
        can append it to the four parts it has always hashed. An empty structured
        master yields `""`, which that composition then drops — which is what
        keeps every existing fingerprint stable across this feature's upgrade.
        """
        parts: list[str] = []
        for experience in self.experiences:
            parts.append(
                " ".join(
                    (
                        experience.role,
                        experience.company,
                        experience.location,
                        experience.summary,
                        " ".join(experience.technologies),
                        " ".join(highlight.haystack for highlight in experience.highlights),
                    )
                )
            )
        for project in self.projects:
            parts.append(project.haystack)
        for entry in self.education:
            parts.append(" ".join((entry.degree, entry.institution, entry.detail)))
        parts.append(" ".join(self.certifications))
        return "\n".join(part.strip() for part in parts if part and part.strip())

    @property
    def source_text(self) -> str:
        """Everything the candidate provided — what "supported" is measured against."""
        parts = (
            self.resume_text,
            self.summary,
            self.headline,
            " ".join(self.skills),
            self.structured_text,
        )
        return "\n".join(part.strip() for part in parts if part and part.strip())


# --------------------------------------------------------------------------- #
# What one posting is asking for
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class JobFocus:
    """The posting, reduced to what can be matched against a resume."""

    title: str = ""
    company: str = ""
    level: str | None = None
    # Technologies the posting names *and* the candidate can back, best first.
    keywords: tuple[str, ...] = ()
    # Technologies the posting names that the master resume cannot back. Surfaced
    # to the user, never written into the resume.
    unsupported: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "company": self.company,
            "level": self.level,
            "keywords": list(self.keywords),
            "unsupported": list(self.unsupported),
        }

    def weight(self, term: str) -> int:
        """Importance of one focus keyword; 0 when the posting never names it."""
        folded = fold(term)
        for rank, keyword in enumerate(self.keywords):
            if fold(keyword) == folded:
                return len(self.keywords) - rank
        return 0


def _detect_level(title: str, description: str) -> str | None:
    haystack = fold(f"{title} {description}")
    for level, needles in _LEVELS:
        if any(needle in haystack for needle in needles):
            return level
    return None


def extract_focus(job: Any, master: MasterResume) -> JobFocus:
    """Read a posting through the lens of what this candidate actually has.

    Keywords are ranked by where the posting names them — the title first, then
    the body — because that is the posting's own statement of priority. Terms the
    candidate cannot back never become keywords; they become `unsupported`, which
    is the honest half of tailoring.
    """
    title = _text(getattr(job, "title", ""))
    description = _text(getattr(job, "description", ""))
    company = _text(getattr(job, "company", ""))

    named = job_technologies(f"{title}\n{description}", master.vocabulary)
    source = master.source_text
    supported: list[tuple[int, int, str]] = []
    unsupported: list[str] = []
    for rank, term in enumerate(named):
        if not mentions(source, term):
            unsupported.append(term)
            continue
        in_title = position_of(title, term)
        if in_title is not None:
            supported.append((-_TITLE_WEIGHT, in_title, term))
        else:
            in_body = position_of(description, term)
            supported.append((-_BODY_WEIGHT, in_body if in_body is not None else rank, term))

    return JobFocus(
        title=title,
        company=company,
        level=_detect_level(title, description),
        keywords=tuple(term for _, _, term in sorted(supported)),
        unsupported=tuple(unsupported),
    )


# --------------------------------------------------------------------------- #
# The derived resume
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TailoredExperience:
    """One experience as this application presents it."""

    id: str
    role: str
    company: str
    period: str = ""
    location: str = ""
    # Composed only from highlights and the summary the candidate wrote.
    description: str = ""
    highlights: tuple[str, ...] = ()
    # The entry's own technologies, job-relevant ones first.
    technologies: tuple[str, ...] = ()
    matched: tuple[str, ...] = ()
    relevance: int = 0
    emphasis: Emphasis = "context"
    # Highlights the candidate wrote that this version leaves out, so the UI can
    # say what was set aside instead of quietly losing it.
    omitted: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "company": self.company,
            "period": self.period,
            "location": self.location,
            "description": self.description,
            "highlights": list(self.highlights),
            "technologies": list(self.technologies),
            "matched": list(self.matched),
            "relevance": self.relevance,
            "emphasis": self.emphasis,
            "omitted": list(self.omitted),
        }


@dataclass(frozen=True, slots=True)
class TailoredProject:
    id: str
    name: str
    description: str = ""
    outcome: str = ""
    technologies: tuple[str, ...] = ()
    matched: tuple[str, ...] = ()
    relevance: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "outcome": self.outcome,
            "technologies": list(self.technologies),
            "matched": list(self.matched),
            "relevance": self.relevance,
        }


@dataclass(frozen=True, slots=True)
class ResumeSections:
    """The structured, per-application resume the UI renders.

    Identity — name, headline, location, the summary the candidate wrote — is
    copied verbatim. Only ordering, selection and emphasis are derived.
    """

    full_name: str = ""
    headline: str = ""
    location: str = ""
    summary: str = ""
    years_of_experience: int | None = None
    # Skills the posting asks for, in the posting's order of priority.
    prioritized_skills: tuple[str, ...] = ()
    # Everything else the candidate lists, in their own order.
    other_skills: tuple[str, ...] = ()
    experiences: tuple[TailoredExperience, ...] = ()
    projects: tuple[TailoredProject, ...] = ()
    education: tuple[Education, ...] = ()
    certifications: tuple[str, ...] = ()
    language: str = "pt"

    def as_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "headline": self.headline,
            "location": self.location,
            "summary": self.summary,
            "years_of_experience": self.years_of_experience,
            "prioritized_skills": list(self.prioritized_skills),
            "other_skills": list(self.other_skills),
            "experiences": [experience.as_dict() for experience in self.experiences],
            "projects": [project.as_dict() for project in self.projects],
            "education": [entry.as_dict() for entry in self.education],
            "certifications": list(self.certifications),
            "language": self.language,
        }


@dataclass(frozen=True, slots=True)
class Derivation:
    """One application's resume: the sections, the reasoning, and the markdown."""

    sections: ResumeSections
    focus: JobFocus
    content: str
    changes: list[dict[str, str]] = field(default_factory=list)
    unsupported_requirements: list[str] = field(default_factory=list)


def _match(haystack: str, focus: JobFocus) -> tuple[tuple[str, ...], int]:
    """Which focus keywords a piece of the resume backs, and how strongly."""
    matched = mentioned_terms(haystack, focus.keywords)
    return tuple(matched), sum(focus.weight(term) for term in matched)


def _relevance_pct(score: int, best: int) -> int:
    if best <= 0 or score <= 0:
        return 0
    return max(1, min(100, round(score * 100 / best)))


def _reorder(terms: Sequence[str], focus: JobFocus) -> tuple[str, ...]:
    """Terms the posting asks for first (by its priority), the rest untouched."""
    wanted = sorted(
        (term for term in terms if focus.weight(term) > 0),
        key=lambda term: -focus.weight(term),
    )
    rest = [term for term in terms if focus.weight(term) == 0]
    return tuple((*wanted, *rest))


def _adapt_experience(experience: Experience, focus: JobFocus) -> tuple[TailoredExperience, int]:
    """Re-describe one experience for one posting, using only its own words.

    The highlights that touch the posting lead, in the posting's order of
    priority; the rest are recorded as omitted rather than deleted. When nothing
    matches, the candidate's neutral summary stands in — an entry with an empty
    description would read as a gap in the history, which it is not.
    """
    scored: list[tuple[int, int, Highlight, tuple[str, ...]]] = []
    for index, highlight in enumerate(experience.highlights):
        matched, score = _match(highlight.haystack, focus)
        # `-score` then the candidate's own order, so equal relevance keeps the
        # sequence they wrote rather than shuffling between calls.
        scored.append((-score, index, highlight, matched))
    scored.sort()

    relevant = [entry for entry in scored if entry[0] < 0]
    if relevant:
        kept = [entry[2].text for entry in relevant]
        omitted = [entry[2].text for entry in scored if entry[0] == 0]
    else:
        # Nothing in this entry speaks to the posting. Lead with the summary when
        # there is one, otherwise with the candidate's own first bullet.
        kept = (
            [experience.summary]
            if experience.summary
            else [entry[2].text for entry in scored[:1]]
        )
        omitted = [entry[2].text for entry in scored if entry[2].text not in kept]

    matched, score = _match(experience.haystack, focus)
    return (
        TailoredExperience(
            id=experience.id,
            role=experience.role,
            company=experience.company,
            period=experience.period,
            location=experience.location,
            description=" ".join(part for part in kept if part).strip(),
            highlights=tuple(part for part in kept if part),
            technologies=_reorder(experience.technologies, focus),
            matched=matched,
            relevance=score,
            omitted=tuple(part for part in omitted if part),
        ),
        score,
    )


def _with_emphasis(tailored: TailoredExperience, score: int, best: int) -> TailoredExperience:
    """Normalise one entry's relevance to a percentage and label it."""
    pct = _relevance_pct(score, best)
    if pct >= _LEAD_THRESHOLD:
        emphasis: Emphasis = "lead"
    elif pct >= _SUPPORT_THRESHOLD:
        emphasis = "support"
    else:
        emphasis = "context"
    return TailoredExperience(
        id=tailored.id,
        role=tailored.role,
        company=tailored.company,
        period=tailored.period,
        location=tailored.location,
        description=tailored.description,
        highlights=tailored.highlights,
        technologies=tailored.technologies,
        matched=tailored.matched,
        relevance=pct,
        emphasis=emphasis,
        omitted=tailored.omitted,
    )


def derive(master: MasterResume, job: Any) -> Derivation:
    """Build this application's resume from the master and the posting.

    Called once per application, and the caller freezes `master.as_dict()`
    alongside the result. That snapshot is the isolation guarantee: editing the
    profile afterwards changes the master and every *future* derivation, and
    cannot reach back into an application that already has its own version.
    """
    focus = extract_focus(job, master)
    # `detect_language` answers "pt-BR" or "en"; the headings only have two
    # variants, so the region is dropped here rather than inside the heuristic.
    language = "pt" if detect_language(master.source_text or focus.title).startswith("pt") else "en"

    adapted = [_adapt_experience(experience, focus) for experience in master.experiences]
    best_experience = max((score for _, score in adapted), default=0)
    experiences = tuple(
        _with_emphasis(tailored, score, best_experience)
        for _, (tailored, score) in sorted(
            enumerate(adapted), key=lambda pair: (-pair[1][1], pair[0])
        )
    )

    scored_projects: list[tuple[int, int, Project, tuple[str, ...]]] = []
    for index, project in enumerate(master.projects):
        matched, score = _match(project.haystack, focus)
        scored_projects.append((-score, index, project, matched))
    scored_projects.sort()
    best_project = max((-score for score, _, _, _ in scored_projects), default=0)
    projects = tuple(
        TailoredProject(
            id=project.id,
            name=project.name,
            description=project.description,
            outcome=project.outcome,
            technologies=_reorder(project.technologies, focus),
            matched=matched,
            relevance=_relevance_pct(-score, best_project),
        )
        for score, _, project, matched in scored_projects
    )

    sections = ResumeSections(
        full_name=master.full_name,
        headline=master.headline,
        location=master.location,
        summary=master.summary,
        years_of_experience=master.years_of_experience,
        prioritized_skills=tuple(
            term for term in _reorder(master.skills, focus) if focus.weight(term) > 0
        ),
        other_skills=tuple(term for term in master.skills if focus.weight(term) == 0),
        experiences=experiences,
        projects=projects,
        education=master.education,
        certifications=master.certifications,
        language=language,
    )

    return Derivation(
        sections=sections,
        focus=focus,
        content=render_markdown(sections, focus),
        changes=_describe_changes(sections, focus, language),
        unsupported_requirements=list(focus.unsupported),
    )


def render_markdown(sections: ResumeSections, focus: JobFocus) -> str:
    """The derived resume as the editable Markdown document the user sees."""
    labels = _HEADINGS.get(sections.language, _HEADINGS["pt"])
    lines: list[str] = []
    if sections.full_name:
        lines.append(f"# {sections.full_name}")
    subtitle = " · ".join(part for part in (sections.headline, sections.location) if part)
    if subtitle:
        lines.append(subtitle)

    if focus.keywords:
        lines.append("")
        lines.append(f"## {labels['focus']}")
        target = " — ".join(part for part in (focus.title, focus.company) if part)
        if target:
            lines.append(f"**{target}**")
        lines.append(", ".join(focus.keywords))

    if sections.summary:
        lines.append("")
        lines.append(sections.summary)

    if sections.prioritized_skills or sections.other_skills:
        lines.append("")
        lines.append(f"## {labels['skills']}")
        if sections.prioritized_skills:
            lines.append(f"**{labels['prioritised']}:** {', '.join(sections.prioritized_skills)}")
        if sections.other_skills:
            lines.append(f"{labels['other']}: {', '.join(sections.other_skills)}")

    if sections.experiences:
        lines.append("")
        lines.append(f"## {labels['experience']}")
        for experience in sections.experiences:
            lines.append("")
            header = " — ".join(part for part in (experience.role, experience.company) if part)
            lines.append(f"### {header}")
            meta = " · ".join(part for part in (experience.period, experience.location) if part)
            if meta:
                lines.append(f"*{meta}*")
            for highlight in experience.highlights:
                lines.append(f"- {highlight}")
            if experience.technologies:
                lines.append(f"- {', '.join(experience.technologies)}")

    if sections.projects:
        lines.append("")
        lines.append(f"## {labels['projects']}")
        for project in sections.projects:
            detail = " ".join(part for part in (project.description, project.outcome) if part)
            lines.append(f"- **{project.name}** — {detail}" if detail else f"- **{project.name}**")
            if project.technologies:
                lines.append(f"  - {', '.join(project.technologies)}")

    if sections.education:
        lines.append("")
        lines.append(f"## {labels['education']}")
        for entry in sections.education:
            parts = [part for part in (entry.degree, entry.institution, entry.period) if part]
            lines.append(f"- {' — '.join(parts)}")
            if entry.detail:
                lines.append(f"  - {entry.detail}")

    if sections.certifications:
        lines.append("")
        lines.append(f"## {labels['certifications']}")
        for certification in sections.certifications:
            lines.append(f"- {certification}")

    return "\n".join(lines).strip() + "\n"


def _describe_changes(
    sections: ResumeSections, focus: JobFocus, language: str
) -> list[dict[str, str]]:
    """The edit log, in the vocabulary the review UI already renders.

    Only `reordered`, `emphasized` and `condensed` can ever appear: there is no
    "added" action, because adding is the one thing this engine cannot do.
    """
    pt = language != "en"
    changes: list[dict[str, str]] = []

    if sections.prioritized_skills:
        listed = ", ".join(sections.prioritized_skills[:6])
        count = len(sections.prioritized_skills)
        changes.append(
            {
                "section": "Competências" if pt else "Skills",
                "action": "reordered",
                "detail": (
                    f"{count} competência(s) pedidas pelo anúncio passaram para o "
                    f"início: {listed}."
                    if pt
                    else f"{count} skill(s) the posting asks for moved to the front: {listed}."
                ),
            }
        )

    leading = [entry for entry in sections.experiences if entry.emphasis == "lead"]
    if leading:
        first = leading[0]
        where = " — ".join(part for part in (first.role, first.company) if part)
        listed = ", ".join(first.matched[:5])
        changes.append(
            {
                "section": "Experiência profissional" if pt else "Professional experience",
                "action": "reordered",
                "detail": (
                    f"«{where}» assumiu o topo por cobrir {listed}."
                    if pt
                    else f"“{where}” leads because it covers {listed}."
                ),
            }
        )

    for experience in sections.experiences:
        if not experience.omitted:
            continue
        where = " — ".join(part for part in (experience.role, experience.company) if part)
        changes.append(
            {
                "section": (f"Experiência — {where}" if pt else f"Experience — {where}"),
                "action": "condensed",
                "detail": (
                    f"Ficaram {len(experience.highlights)} ponto(s) ligados à vaga; "
                    f"{len(experience.omitted)} do currículo principal não entraram "
                    "nesta versão."
                    if pt
                    else (
                        f"Kept {len(experience.highlights)} bullet(s) tied to the posting; "
                        f"{len(experience.omitted)} from the master resume stayed out."
                    )
                ),
            }
        )

    relevant_projects = [project for project in sections.projects if project.matched]
    if relevant_projects:
        listed = ", ".join(project.name for project in relevant_projects[:3])
        changes.append(
            {
                "section": "Projetos" if pt else "Projects",
                "action": "emphasized",
                "detail": (
                    f"Projetos com tecnologias da vaga vieram primeiro: {listed}."
                    if pt
                    else f"Projects using the posting's stack come first: {listed}."
                ),
            }
        )

    if focus.keywords:
        listed = ", ".join(focus.keywords[:8])
        changes.append(
            {
                "section": "Foco desta versão" if pt else "Focus of this version",
                "action": "emphasized",
                "detail": (
                    f"Palavras-chave do anúncio destacadas nesta versão: {listed}."
                    if pt
                    else f"Posting keywords surfaced in this version: {listed}."
                ),
            }
        )

    return changes


__all__ = [
    "Derivation",
    "Education",
    "Emphasis",
    "Experience",
    "Highlight",
    "JobFocus",
    "MasterResume",
    "Project",
    "ResumeSections",
    "TailoredExperience",
    "TailoredProject",
    "derive",
    "extract_focus",
    "render_markdown",
]
