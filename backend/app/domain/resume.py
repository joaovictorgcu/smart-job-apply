"""The structured resume: one master, one version per application.

Two things live here, and both are deliberately in the domain layer rather than
next to the database or the AI client.

**The document.** `ResumeDocument` is a resume as data — experiences with their
company, role, period, achievements, technologies and projects. The master
profile, an application's own version and the snapshot that version was derived
from are all the same type, so one renderer, one differ and one set of rules
serve every screen.

**The derivation.** `tailor_document` re-emphasizes a document for one posting
*with no model call*: it intersects the posting's text with the candidate's own
vocabulary, ranks experiences and achievements by what that intersection
matches, and rewrites the summaries to lead with the matched terms. Two
consequences matter more than the algorithm:

* It cannot invent. Every term it emphasizes came out of the candidate's own
  document — the posting only decides the *order* and the wording *around*
  facts that were already there. A posting demanding Rust from someone who has
  never written Rust produces no Rust anywhere, because "Rust" is not in the
  vocabulary the intersection is taken against.
* It is deterministic and works offline. That is what makes "four applications
  really do carry four different resumes" an assertion a test can make, rather
  than a property of whichever model happened to answer.

The AI path (`app.ai.tailor_resume`) still exists and still earns its place: it
writes prose. This is the part that has to be right every single time.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# How much more a term counts for appearing in the posting's title than in its
# body: a title says what the role *is*, a body also lists what would be nice.
TITLE_WEIGHT = 3
# Occurrences of one term in the description past which repetition stops being
# evidence of importance and starts being boilerplate.
MAX_DESCRIPTION_HITS = 3
# An experience with nothing in common with the posting keeps this many
# achievements. It is never dropped: an employment history with a hole in it
# reads as a lie, and the job of tailoring is emphasis, not concealment.
CONDENSED_HIGHLIGHTS = 2
# Terms named inside a rewritten summary. Past three the sentence stops reading
# like a resume line and starts reading like a keyword list.
MAX_EMPHASIS_TERMS = 3
# Terms recorded on an experience as "this is what it is here to answer".
MAX_EXPERIENCE_FOCUS = 4


def _slug(text: str) -> str:
    """A stable, ascii-only identifier fragment."""
    folded = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", stripped.lower()).strip("-")


def fold(text: str) -> str:
    """Lowercase, accent-free text, for matching."""
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


# --------------------------------------------------------------------------- #
# The document
# --------------------------------------------------------------------------- #


class ResumeHighlight(BaseModel):
    """One achievement, tagged with the technologies it actually involved.

    The tags are what make honest targeted emphasis possible: matching a
    posting against free text alone ranks an achievement that merely mentions a
    tool above one that was built with it. `impact` is kept apart from `text` so
    a rewritten summary can quote the measured result without re-deriving it.
    """

    model_config = ConfigDict(extra="ignore")

    text: str
    technologies: list[str] = Field(default_factory=list)
    impact: str | None = None


class ResumeProject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    outcome: str | None = None


class ResumeExperience(BaseModel):
    """One position. `key` is its identity across every version of the resume.

    Company, role and period are facts about the past. A version may reorder,
    rephrase and re-emphasize them; it may not change them, and
    `resume_service.update_document` refuses an edit that tries. That check
    needs an identity which survives reordering, which is what `key` is for —
    a list index would not do.
    """

    model_config = ConfigDict(extra="ignore")

    key: str = ""
    company: str
    role: str
    start: str = ""
    end: str | None = None
    location: str | None = None
    summary: str | None = None
    highlights: list[ResumeHighlight] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    projects: list[ResumeProject] = Field(default_factory=list)
    # Filled in only on a derived version: the posting's terms this experience
    # is being used to answer. Always empty on the master document.
    focus: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ensure_key(self) -> ResumeExperience:
        if not self.key.strip():
            self.key = _slug(f"{self.company}-{self.role}-{self.start}") or "experiencia"
        return self

    @property
    def period(self) -> str:
        return f"{self.start} — {self.end}" if self.end else self.start

    @property
    def identity(self) -> tuple[str, str, str, str]:
        """The part a derived version may never rewrite."""
        return (self.key, self.company, self.role, f"{self.start}|{self.end or ''}")


class ResumeEducation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    institution: str
    degree: str = ""
    start: str = ""
    end: str | None = None
    detail: str | None = None


class ResumeDocument(BaseModel):
    """A whole resume as data.

    The same type is the master, one application's version, and the snapshot
    that version was derived from. Nothing distinguishes them but where they are
    stored — which is exactly what keeps one renderer and one differ enough.
    """

    model_config = ConfigDict(extra="ignore")

    headline: str | None = None
    summary: str | None = None
    # Competências (architecture, technical leadership) and tecnologias (.NET,
    # React) are asked for differently by a posting and weigh differently in a
    # resume, so they stay two lists rather than one bag of "skills".
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    experiences: list[ResumeExperience] = Field(default_factory=list)
    projects: list[ResumeProject] = Field(default_factory=list)
    education: list[ResumeEducation] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_keys(self) -> ResumeDocument:
        """Make every experience key unique inside the document.

        Two spells at the same company with the same title would otherwise
        collide, and a collision silently merges two positions in every diff
        and every edit check.
        """
        seen: dict[str, int] = {}
        for experience in self.experiences:
            count = seen.get(experience.key, 0) + 1
            seen[experience.key] = count
            if count > 1:
                experience.key = f"{experience.key}-{count}"
        return self

    @property
    def is_empty(self) -> bool:
        """True when there is nothing here worth versioning per application."""
        return not (self.experiences or self.skills or self.technologies or self.projects)

    @property
    def experience_keys(self) -> tuple[str, ...]:
        return tuple(experience.key for experience in self.experiences)

    def experience(self, key: str) -> ResumeExperience | None:
        return next((item for item in self.experiences if item.key == key), None)


def empty_document() -> ResumeDocument:
    return ResumeDocument()


def build_document(
    *,
    headline: str | None = None,
    summary: str | None = None,
    skills: Iterable[str] = (),
    technologies: Iterable[str] = (),
    experiences: Iterable[Any] = (),
    projects: Iterable[Any] = (),
    education: Iterable[Any] = (),
    certifications: Iterable[str] = (),
    languages: Iterable[str] = (),
) -> ResumeDocument:
    """Assemble a document from the profile's columns.

    The master resume is stored as the columns it always was (`headline`,
    `summary`, `skills`) plus the structured lists added for this feature — not
    as one nested blob. Keeping the storage flat avoids two sources of truth for
    the headline, and this function is the single place that turns those columns
    into the document every other layer works with.

    Raises `pydantic.ValidationError` on a malformed stored list, which the
    caller reports rather than swallowing: a resume the app cannot parse is
    something the user needs to be told about.
    """
    return ResumeDocument.model_validate(
        {
            "headline": headline,
            "summary": summary,
            "skills": list(skills or []),
            "technologies": list(technologies or []),
            "experiences": list(experiences or []),
            "projects": list(projects or []),
            "education": list(education or []),
            "certifications": list(certifications or []),
            "languages": list(languages or []),
        }
    )


def parse_document(raw: Any) -> ResumeDocument:
    """Validate a stored document (a JSON column) back into the contract."""
    if not raw:
        return empty_document()
    if isinstance(raw, ResumeDocument):
        return raw.model_copy(deep=True)
    return ResumeDocument.model_validate(raw)


def dump_document(document: ResumeDocument) -> dict[str, Any]:
    """The JSON-safe form stored in a JSON column."""
    return document.model_dump(mode="json")


def document_fingerprint(document: ResumeDocument) -> str:
    """Hash of a document's content, for staleness checks.

    Canonical JSON — sorted keys, no incidental whitespace — so identical
    content always hashes identically regardless of how it was assembled.
    """
    canonical = json.dumps(
        dump_document(document), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def render_markdown(document: ResumeDocument) -> str:
    """The document as a resume a human — or a form — can read."""
    lines: list[str] = []
    if document.headline:
        lines += [f"# {document.headline}", ""]
    if document.summary:
        lines += [document.summary.strip(), ""]
    if document.skills:
        lines += ["## Competências", ", ".join(document.skills), ""]
    if document.technologies:
        lines += ["## Tecnologias", ", ".join(document.technologies), ""]

    if document.experiences:
        lines.append("## Experiência")
        for experience in document.experiences:
            lines.append(f"### {experience.role} — {experience.company}")
            meta = [part for part in (experience.period, experience.location) if part]
            if meta:
                lines.append(" · ".join(meta))
            if experience.summary:
                lines.append(experience.summary.strip())
            for highlight in experience.highlights:
                impact = f" ({highlight.impact})" if highlight.impact else ""
                lines.append(f"- {highlight.text}{impact}")
            if experience.technologies:
                lines.append(f"Tecnologias: {', '.join(experience.technologies)}")
            for project in experience.projects:
                lines.append(f"- Projeto — {project.name}: {project.description}")
            lines.append("")

    if document.projects:
        lines.append("## Projetos")
        for project in document.projects:
            lines.append(f"### {project.name}")
            if project.description:
                lines.append(project.description)
            if project.technologies:
                lines.append(f"Tecnologias: {', '.join(project.technologies)}")
            if project.outcome:
                lines.append(f"Resultado: {project.outcome}")
            lines.append("")

    if document.education:
        lines.append("## Formação")
        for entry in document.education:
            period = f" ({entry.start} — {entry.end})" if entry.end else ""
            degree = f"{entry.degree}, " if entry.degree else ""
            lines.append(f"- {degree}{entry.institution}{period}")
        lines.append("")

    if document.certifications:
        lines += ["## Certificações", *(f"- {item}" for item in document.certifications), ""]
    if document.languages:
        lines += ["## Idiomas", ", ".join(document.languages), ""]

    return ("\n".join(lines).strip() + "\n") if lines else ""


def render_plain_text(document: ResumeDocument) -> str:
    """Every word the candidate wrote, flattened.

    Feeds the invention guard and the profile fingerprint. A technology that
    only ever appears inside a structured experience still has to count as
    something the candidate genuinely claims — otherwise the guard would flag
    the candidate's own history as fabricated, which is the one false positive
    that would make it untrustworthy.
    """
    parts: list[str] = [document.headline or "", document.summary or ""]
    parts += [*document.skills, *document.technologies, *document.certifications]
    parts += document.languages
    for experience in document.experiences:
        parts += [experience.company, experience.role, experience.summary or ""]
        parts += experience.technologies
        for highlight in experience.highlights:
            parts += [highlight.text, highlight.impact or "", *highlight.technologies]
        for project in experience.projects:
            parts += [project.name, project.description, project.outcome or ""]
            parts += project.technologies
    for project in document.projects:
        parts += [project.name, project.description, project.outcome or ""]
        parts += project.technologies
    for entry in document.education:
        parts += [entry.institution, entry.degree, entry.detail or ""]
    return "\n".join(part for part in parts if part and part.strip())


# --------------------------------------------------------------------------- #
# What the posting is asking for
# --------------------------------------------------------------------------- #


# A trailing version on a technology name: ".NET 8", "Python 3.11", "Vue 3",
# "Java 17", "SQL-92". Postings and resumes disagree about it constantly.
_VERSION_SUFFIX = re.compile(r"[\s\-_]v?\d+(?:\.\d+)*$")


def _aliases(term: str) -> tuple[str, ...]:
    """The forms one term may legitimately appear as.

    A posting writes "sênior em .NET" where the resume says ".NET 8"; the two
    are the same technology, and a matcher that misses it ranks the wrong
    experience first — which is the whole output. So a term also matches its own
    version-stripped form.

    Only the *candidate's* term is generalised, never the posting's: this widens
    what counts as a hit for something they already claim, and can still not
    introduce a technology they never listed.
    """
    base = _VERSION_SUFFIX.sub("", term).strip()
    if base and base != term and len(base) >= 2:
        return (term, base)
    return (term,)


@lru_cache(maxsize=2048)
def _term_patterns(term: str) -> tuple[re.Pattern[str], ...]:
    r"""Whole-term matchers that survive punctuation inside the term itself.

    `.NET`, `C#`, `Node.js` and `APIs REST` all have to match, and none of them
    is a word in the `\b` sense — so the boundaries are asserted against
    alphanumerics only. Cached because the same handful of terms is matched
    against every experience, achievement and project of a document.
    """
    return tuple(
        re.compile(rf"(?<![a-z0-9]){re.escape(fold(alias))}(?![a-z0-9])")
        for alias in _aliases(term)
    )


def _hits(term: str, haystack: str) -> int:
    """Occurrences of a term in already-folded text, counting its aliases.

    The strongest alias wins rather than the sum: ".NET 8" and ".NET" in one
    sentence are one mention of one technology, not two.
    """
    return max(len(pattern.findall(haystack)) for pattern in _term_patterns(term))


def _present(term: str, haystack: str) -> bool:
    return any(pattern.search(haystack) for pattern in _term_patterns(term))


@dataclass(frozen=True)
class ResumeFocus:
    """What one posting emphasizes, expressed only in the candidate's own terms.

    `terms` is ranked strongest first and carries the candidate's own casing.
    These are their skills and technologies, matched against the posting —
    never strings lifted out of the posting itself. That asymmetry is the whole
    invention guarantee, and it lives here rather than in a prompt.
    """

    terms: tuple[str, ...] = ()
    weights: dict[str, int] = field(default_factory=dict)

    def weight(self, term: str) -> int:
        return self.weights.get(fold(term), 0)

    def __bool__(self) -> bool:
        return bool(self.terms)


def vocabulary(document: ResumeDocument) -> list[str]:
    """Every term the candidate claims, longest first.

    Longest first so ".NET Core" is considered before ".NET": both match, and
    the more specific one should be the one that ranks an experience.
    """
    terms: dict[str, str] = {}

    def add(values: Iterable[str]) -> None:
        for value in values:
            if value and value.strip():
                terms.setdefault(fold(value), value.strip())

    add(document.technologies)
    add(document.skills)
    for experience in document.experiences:
        add(experience.technologies)
        for highlight in experience.highlights:
            add(highlight.technologies)
        for project in experience.projects:
            add(project.technologies)
    for project in document.projects:
        add(project.technologies)
    return sorted(terms.values(), key=lambda term: (-len(term), fold(term)))


def extract_focus(
    document: ResumeDocument,
    *,
    title: str | None = None,
    description: str | None = None,
    extra: Iterable[str] = (),
) -> ResumeFocus:
    """Rank the candidate's own terms by how much this posting asks for them.

    `extra` carries anything else known about the posting — the requirements a
    scoring pass extracted, for instance — and is weighted like the description.
    """
    haystack_title = fold(title or "")
    haystack_body = fold("\n".join([description or "", *[str(item) for item in extra]]))

    weights: dict[str, int] = {}
    ranked: list[tuple[int, int, str]] = []
    for index, term in enumerate(vocabulary(document)):
        weight = TITLE_WEIGHT * _hits(term, haystack_title)
        weight += min(_hits(term, haystack_body), MAX_DESCRIPTION_HITS)
        if weight > 0:
            weights[fold(term)] = weight
            ranked.append((-weight, index, term))

    ranked.sort()
    return ResumeFocus(terms=tuple(term for _, _, term in ranked), weights=weights)


# --------------------------------------------------------------------------- #
# Deriving one application's version
# --------------------------------------------------------------------------- #

ChangeAction = Literal["reordered", "emphasized", "rephrased", "condensed", "omitted"]


class ResumeChange(BaseModel):
    """One edit the derivation made, in the same shape as `ai.schemas.CVChange`.

    The same closed vocabulary of actions on purpose: the review UI already
    renders those badges, and there is deliberately no "added" action — adding
    is the one thing a derived resume must never do.
    """

    model_config = ConfigDict(extra="ignore")

    section: str
    action: ChangeAction
    detail: str


@dataclass(frozen=True)
class TailoredVersion:
    """A derived document, the terms it was derived for, and what it changed."""

    document: ResumeDocument
    focus: tuple[str, ...]
    changes: tuple[ResumeChange, ...]


def _join(terms: Sequence[str]) -> str:
    if not terms:
        return ""
    if len(terms) == 1:
        return terms[0]
    return f"{', '.join(terms[:-1])} e {terms[-1]}"


def _matched(texts: Iterable[str], focus: ResumeFocus) -> list[str]:
    """The focus terms present in this text, strongest first."""
    haystack = fold("\n".join(part for part in texts if part))
    return [term for term in focus.terms if _present(term, haystack)]


def _emphasize(terms: Sequence[str], focus: ResumeFocus) -> list[str]:
    """Matched terms first (strongest first), the rest in their original order."""
    matched = [term for term in terms if focus.weight(term) > 0]
    matched.sort(key=lambda term: (-focus.weight(term), terms.index(term)))
    return [*matched, *(term for term in terms if focus.weight(term) == 0)]


def _with_emphasis(summary: str | None, terms: Sequence[str], impact: str | None = None) -> str:
    """Rewrite a summary so it leads with what this posting cares about.

    Only the connective tissue is new. Every term named here came from the
    candidate's own document and `impact` is quoted from one of their own
    achievements — that is rephrasing, which a derived resume is allowed to do.
    """
    named = _join(list(terms)[:MAX_EMPHASIS_TERMS])
    base = (summary or "").strip().rstrip(".")
    sentence = f"{base} — ênfase em {named}" if base else f"Ênfase em {named}"
    if impact:
        sentence = f"{sentence}; {impact.strip().rstrip('.')}"
    return f"{sentence}."


def _highlight_weight(highlight: ResumeHighlight, focus: ResumeFocus) -> int:
    matched = _matched([highlight.text, highlight.impact or "", *highlight.technologies], focus)
    return sum(focus.weight(term) for term in matched)


def _project_weight(project: ResumeProject, focus: ResumeFocus) -> int:
    matched = _matched(
        [project.name, project.description, project.outcome or "", *project.technologies], focus
    )
    return sum(focus.weight(term) for term in matched)


def _experience_texts(experience: ResumeExperience) -> list[str]:
    parts = [experience.role, experience.summary or "", *experience.technologies]
    for highlight in experience.highlights:
        parts += [highlight.text, highlight.impact or "", *highlight.technologies]
    for project in experience.projects:
        parts += [project.name, project.description, *project.technologies]
    return parts


def tailor_document(document: ResumeDocument, focus: ResumeFocus) -> TailoredVersion:
    """Re-emphasize `document` for the posting `focus` came from.

    Pure and deterministic: the same document and the same posting always give
    the same version.

    With no overlap between posting and candidate (`focus` empty) the document
    comes back untouched and the change list is empty. "Nothing here matches
    this posting" is the honest outcome; shuffling the resume to look busy
    would not be.
    """
    tailored = document.model_copy(deep=True)
    if not focus:
        return TailoredVersion(document=tailored, focus=(), changes=())

    changes: list[ResumeChange] = []

    # --- experiences: the order, then the emphasis inside each one ----------
    scored: list[tuple[int, int, ResumeExperience, list[str]]] = []
    for index, experience in enumerate(tailored.experiences):
        matched = _matched(_experience_texts(experience), focus)
        scored.append((sum(focus.weight(term) for term in matched), index, experience, matched))

    ordered = sorted(scored, key=lambda row: (-row[0], row[1]))
    if ordered and [row[1] for row in ordered] != [row[1] for row in scored]:
        _, _, top, top_matched = ordered[0]
        changes.append(
            ResumeChange(
                section="Experiência",
                action="reordered",
                detail=(
                    f"{top.role} — {top.company} foi para o topo: é a experiência com maior "
                    f"aderência a {_join(top_matched[:MAX_EMPHASIS_TERMS])}."
                ),
            )
        )

    for _, _, experience, matched in ordered:
        label = f"Experiência — {experience.company}"
        if not matched:
            # Kept in full when short; condensed when long, and never removed.
            if len(experience.highlights) > CONDENSED_HIGHLIGHTS:
                folded_away = len(experience.highlights) - CONDENSED_HIGHLIGHTS
                experience.highlights = experience.highlights[:CONDENSED_HIGHLIGHTS]
                changes.append(
                    ResumeChange(
                        section=label,
                        action="condensed",
                        detail=(
                            f"Nada em comum com esta vaga: {folded_away} "
                            f"{'item' if folded_away == 1 else 'itens'} recolhidos. A "
                            "experiência continua no currículo."
                        ),
                    )
                )
            continue

        experience.focus = matched[:MAX_EXPERIENCE_FOCUS]

        previous_highlights = list(experience.highlights)
        experience.highlights = sorted(
            previous_highlights,
            key=lambda highlight: (
                -_highlight_weight(highlight, focus),
                previous_highlights.index(highlight),
            ),
        )
        if [item.text for item in experience.highlights] != [
            item.text for item in previous_highlights
        ]:
            changes.append(
                ResumeChange(
                    section=label,
                    action="emphasized",
                    detail=(
                        "Realizações reordenadas para abrir com o que toca "
                        f"{_join(matched[:MAX_EMPHASIS_TERMS])}."
                    ),
                )
            )

        previous_technologies = list(experience.technologies)
        experience.technologies = _emphasize(previous_technologies, focus)
        if experience.technologies != previous_technologies:
            changes.append(
                ResumeChange(
                    section=label,
                    action="emphasized",
                    detail=(
                        "Tecnologias reordenadas: "
                        f"{_join(experience.technologies[:MAX_EMPHASIS_TERMS])} primeiro."
                    ),
                )
            )

        previous_projects = list(experience.projects)
        experience.projects = sorted(
            previous_projects,
            key=lambda project: (
                -_project_weight(project, focus),
                previous_projects.index(project),
            ),
        )
        if [item.name for item in experience.projects] != [item.name for item in previous_projects]:
            changes.append(
                ResumeChange(
                    section=label,
                    action="reordered",
                    detail=f"Projetos reordenados por aderência a {_join(matched[:2])}.",
                )
            )

        # The impact quoted in the summary comes from the achievement that best
        # matches this posting, which is now the first one in the list.
        top_impact = next(
            (
                highlight.impact
                for highlight in experience.highlights
                if highlight.impact and _highlight_weight(highlight, focus) > 0
            ),
            None,
        )
        rewritten = _with_emphasis(experience.summary, matched, top_impact)
        if rewritten != (experience.summary or ""):
            changes.append(
                ResumeChange(
                    section=label,
                    action="rephrased",
                    detail=(
                        "Descrição reescrita para destacar "
                        f"{_join(matched[:MAX_EMPHASIS_TERMS])}"
                        + (" e o resultado medido." if top_impact else ".")
                    ),
                )
            )
        experience.summary = rewritten

    tailored.experiences = [row[2] for row in ordered]

    # --- competências, tecnologias, projetos, resumo ------------------------
    previous_skills = list(tailored.skills)
    tailored.skills = _emphasize(previous_skills, focus)
    if tailored.skills != previous_skills:
        changes.append(
            ResumeChange(
                section="Competências",
                action="emphasized",
                detail=f"{_join(tailored.skills[:MAX_EMPHASIS_TERMS])} à frente da lista.",
            )
        )

    previous_technologies = list(tailored.technologies)
    tailored.technologies = _emphasize(previous_technologies, focus)
    if tailored.technologies != previous_technologies:
        changes.append(
            ResumeChange(
                section="Tecnologias",
                action="emphasized",
                detail=f"{_join(tailored.technologies[:MAX_EMPHASIS_TERMS])} à frente da lista.",
            )
        )

    previous_standalone = list(tailored.projects)
    tailored.projects = sorted(
        previous_standalone,
        key=lambda project: (
            -_project_weight(project, focus),
            previous_standalone.index(project),
        ),
    )
    if [item.name for item in tailored.projects] != [item.name for item in previous_standalone]:
        changes.append(
            ResumeChange(
                section="Projetos",
                action="reordered",
                detail=(
                    f"{tailored.projects[0].name} primeiro, por aderência a "
                    f"{_join(list(focus.terms)[:2])}."
                ),
            )
        )

    rewritten_summary = _with_emphasis(tailored.summary, list(focus.terms))
    if rewritten_summary != (tailored.summary or ""):
        changes.append(
            ResumeChange(
                section="Resumo",
                action="rephrased",
                detail=(
                    "Resumo profissional reescrito em torno de "
                    f"{_join(list(focus.terms)[:MAX_EMPHASIS_TERMS])}."
                ),
            )
        )
    tailored.summary = rewritten_summary

    return TailoredVersion(document=tailored, focus=focus.terms, changes=tuple(changes))


def tailor_for_posting(
    document: ResumeDocument,
    *,
    title: str | None = None,
    description: str | None = None,
    extra: Iterable[str] = (),
) -> TailoredVersion:
    """`extract_focus` then `tailor_document` — the one call a service needs."""
    return tailor_document(
        document, extract_focus(document, title=title, description=description, extra=extra)
    )


def identity_conflicts(base: ResumeDocument, edited: ResumeDocument) -> list[str]:
    """Experience identities the edit changed or invented.

    A version re-emphasizes the past; it does not rewrite it. Company, role and
    period therefore have to survive an edit unchanged, and an experience the
    master never had cannot appear at all. Returned as a list of keys so the
    caller can name them in the error.
    """
    known = {experience.key: experience.identity for experience in base.experiences}
    conflicts: list[str] = []
    for experience in edited.experiences:
        expected = known.get(experience.key)
        if expected is None or expected != experience.identity:
            conflicts.append(experience.key)
    return conflicts


__all__ = [
    "CONDENSED_HIGHLIGHTS",
    "ResumeChange",
    "ResumeDocument",
    "ResumeEducation",
    "ResumeExperience",
    "ResumeFocus",
    "ResumeHighlight",
    "ResumeProject",
    "TailoredVersion",
    "build_document",
    "document_fingerprint",
    "dump_document",
    "empty_document",
    "extract_focus",
    "fold",
    "identity_conflicts",
    "parse_document",
    "render_markdown",
    "render_plain_text",
    "tailor_document",
    "tailor_for_posting",
    "vocabulary",
]
