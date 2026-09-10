"""Reading a resume the user uploaded, so they confirm instead of retyping.

The product promise this serves is one sentence: *upload your CV once, and the
app shows you what it found*. Everything downstream — scoring, the per-posting
derivation in `app.domain.resume`, the screening answers — already reads from
`Profile` and `Experience`. What was missing was the path from a PDF to those
rows that does not run through a form with thirty fields.

Two rules shape the whole module, and both are the same rule the derivation
already obeys:

* **Nothing is invented.** Every string returned here is a substring of the
  uploaded text, or a candidate's own technology spelling recovered from it.
  Dates are the single derived value, and they are parsed from a range the
  document itself prints.
* **Nothing is written.** This produces a *proposal*. The user confirms or
  corrects it, and only then does a service turn it into rows. A parser working
  on the free-form layout of a resume will be wrong sometimes, and being wrong
  in a screen the user is already reading is cheap — being wrong silently in
  their profile is not.

Deterministic and offline on purpose, for the same reason the derivation is: it
has to behave identically on a deployment with no AI key, and "what did we read
out of this CV" must be provable against plain text in a unit test.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from app.domain.language import fold, squash
from app.domain.technologies import KNOWN_TECHNOLOGIES, mentioned_terms, spelling_in

# A heading is a short line. Anything longer is a sentence that happens to begin
# with the word "Experiência".
MAX_HEADING_CHARS = 48
MAX_HEADING_WORDS = 5
# A person's name, and the one-line title under it.
MAX_NAME_CHARS = 60
MAX_HEADLINE_CHARS = 140
# Header lines pulled up into an entry's title block before its date line.
MAX_ENTRY_TITLE_LINES = 2
# Past this a "skill" is a sentence someone wrote in a bulleted list.
MAX_SKILL_CHARS = 48


# --------------------------------------------------------------------------- #
# What was found
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class IntakeProject:
    name: str
    description: str = ""
    technologies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IntakeExperience:
    """One position as the document presents it.

    `company` and `role` may come back empty: a layout this parser could not
    split is reported as a gap for the user to fill, never as a guess dressed up
    as a fact.
    """

    role: str = ""
    company: str = ""
    employment_type: str | None = None
    location: str | None = None
    started_on: date | None = None
    ended_on: date | None = None
    is_current: bool = False
    period_text: str = ""
    summary: str = ""
    responsibilities: tuple[str, ...] = ()
    technologies: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        """Whether this entry could be saved as-is, with no correction."""
        return bool(self.role.strip() and self.company.strip())


@dataclass(frozen=True, slots=True)
class IntakeEducation:
    institution: str = ""
    degree: str = ""
    period_text: str = ""


@dataclass(frozen=True, slots=True)
class ResumeIntake:
    """Everything one uploaded resume said, for the user to confirm.

    `warnings` names what could not be read rather than hiding it. A CV whose
    experience section this parser did not recognise has to say so — the
    alternative is an empty list the user reads as "I have no experience
    recorded", which is worse than an honest gap.
    """

    full_name: str | None = None
    headline: str | None = None
    location: str | None = None
    email: str | None = None
    phone: str | None = None
    summary: str | None = None
    skills: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    experiences: tuple[IntakeExperience, ...] = ()
    education: tuple[IntakeEducation, ...] = ()
    projects: tuple[IntakeProject, ...] = ()
    certifications: tuple[str, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not (
            self.full_name
            or self.headline
            or self.summary
            or self.skills
            or self.experiences
            or self.education
            or self.projects
        )


# --------------------------------------------------------------------------- #
# Section headings
# --------------------------------------------------------------------------- #

# Folded, punctuation-squashed heading phrases, Portuguese and English. Matched
# exactly against a squashed line, so "EXPERIÊNCIA PROFISSIONAL:" and
# "Experiência profissional" are the same heading and a sentence beginning with
# the word is not a heading at all.
_HEADINGS: dict[str, frozenset[str]] = {
    "summary": frozenset(
        {
            "resumo", "resumo profissional", "perfil", "perfil profissional",
            "objetivo", "objetivo profissional", "sobre", "sobre mim",
            "apresentacao", "summary", "professional summary", "profile",
            "about", "about me", "objective", "career objective",
        }
    ),
    "experience": frozenset(
        {
            "experiencia", "experiencias", "experiencia profissional",
            "experiencias profissionais", "experiencia de trabalho",
            "historico profissional", "atuacao profissional", "carreira",
            "experience", "professional experience", "work experience",
            "employment history", "work history",
        }
    ),
    "education": frozenset(
        {
            "formacao", "formacao academica", "educacao", "escolaridade",
            "education", "academic background", "academic education",
        }
    ),
    "skills": frozenset(
        {
            "habilidades", "competencias", "competencias tecnicas",
            "conhecimentos", "conhecimentos tecnicos", "tecnologias",
            "stack", "stack tecnica", "ferramentas", "skills",
            "technical skills", "hard skills", "technologies", "tools",
        }
    ),
    "languages": frozenset({"idiomas", "linguas", "languages", "language skills"}),
    "projects": frozenset(
        {
            "projetos", "projetos pessoais", "portfolio", "projects",
            "personal projects", "side projects",
        }
    ),
    "certifications": frozenset(
        {
            "certificacoes", "certificados", "cursos", "cursos e certificacoes",
            "certifications", "courses", "licenses and certifications",
        }
    ),
    "contact": frozenset({"contato", "contatos", "contact", "dados pessoais"}),
}


def _heading_of(line: str) -> str | None:
    """The section a line opens, or None when it is ordinary content."""
    stripped = line.strip().strip(":•-–—*").strip()
    if not stripped or len(stripped) > MAX_HEADING_CHARS:
        return None
    squashed = squash(stripped)
    if not squashed or len(squashed.split()) > MAX_HEADING_WORDS:
        return None
    for section, phrases in _HEADINGS.items():
        if squashed in phrases:
            return section
    return None


def _split_sections(lines: Sequence[str]) -> dict[str, list[str]]:
    """Group the document's lines under the heading that introduced them.

    The block before the first heading is the header — name, title, contact —
    and is stored under the empty key.
    """
    sections: dict[str, list[str]] = {"": []}
    current = ""
    for line in lines:
        heading = _heading_of(line)
        if heading is not None:
            current = heading
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return sections


# --------------------------------------------------------------------------- #
# Contact details
# --------------------------------------------------------------------------- #

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Loose on purpose: +55 (81) 99999-9999, (11) 3333-4444, +351 900 000 000.
# Anchored on at least eight digits so a date or a postcode cannot match.
_PHONE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{4,5}[\s.-]?\d{4}\b")
_URL = re.compile(r"(?:https?://|www\.)\S+|linkedin\.com/\S+|github\.com/\S+", re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:[-–—•*▪·◦]|\d+[.)])\s+")


def _is_contact_line(line: str) -> bool:
    return bool(_EMAIL.search(line) or _URL.search(line) or _PHONE.search(line))


def _is_bullet(line: str) -> bool:
    return bool(_BULLET.match(line))


def _debullet(line: str) -> str:
    return _BULLET.sub("", line).strip()


# --------------------------------------------------------------------------- #
# Periods
# --------------------------------------------------------------------------- #

# Three-letter prefixes, Portuguese and English. No two collide, which is why a
# single table serves both languages.
_MONTHS: dict[str, int] = {
    "jan": 1, "fev": 2, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "mai": 5,
    "may": 5, "jun": 6, "jul": 7, "ago": 8, "aug": 8, "set": 9, "sep": 9,
    "out": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12,
}

_PRESENT_WORDS = frozenset(
    {"present", "presente", "current", "currently", "atual", "atualmente", "hoje", "now", "momento"}
)

_MONTH_WORD = r"[A-Za-zÀ-ÿ]{3,12}"
_DATE_PART = (
    rf"(?:{_MONTH_WORD}\.?\s*(?:de\s+)?\d{{4}}"  # março de 2021, Jan 2021
    r"|\d{1,2}\s*[/.\-]\s*\d{4}"  # 03/2021
    r"|\d{4}\s*[/.\-]\s*\d{1,2}"  # 2021-03
    r"|\d{4})"  # 2021
)
_PRESENT_PART = r"(?:o\s+momento|" + "|".join(sorted(_PRESENT_WORDS)) + r")"
_RANGE_SEP = r"\s*(?:[-–—]|\bat[ée]\b|\ba\b|\bto\b|\buntil\b)\s*"
_DATE_RANGE = re.compile(
    rf"(?P<start>{_DATE_PART}){_RANGE_SEP}(?P<end>{_DATE_PART}|{_PRESENT_PART})",
    re.IGNORECASE,
)


def _parse_date_part(raw: str, *, end_of_period: bool) -> date | None:
    """One side of a printed period, as a date. None when it is unreadable.

    A year on its own becomes January or December, depending on which end of the
    range it is: that is the reading a human gives "2021 — 2023", and the day is
    never shown back to the user.
    """
    text = raw.strip()
    if not text:
        return None

    numeric = re.fullmatch(r"(\d{1,4})\s*[/.\-]\s*(\d{1,4})", text)
    if numeric is not None:
        left, right = int(numeric.group(1)), int(numeric.group(2))
        month, year = (left, right) if left <= 12 and right > 12 else (right, left)
        if 1 <= month <= 12 and 1000 <= year <= 9999:
            return _clamp(year, month, end_of_period)
        return None

    year_only = re.fullmatch(r"\d{4}", text)
    if year_only is not None:
        return _clamp(int(text), 12 if end_of_period else 1, end_of_period)

    worded = re.fullmatch(rf"({_MONTH_WORD})\.?\s*(?:de\s+)?(\d{{4}})", text, re.IGNORECASE)
    if worded is not None:
        month = _MONTHS.get(fold(worded.group(1))[:3])
        if month is not None:
            return _clamp(int(worded.group(2)), month, end_of_period)
    return None


def _clamp(year: int, month: int, end_of_period: bool) -> date | None:
    """A month as a date: its first day, or its last when it ends a period."""
    if not (1 <= month <= 12) or not (1900 <= year <= 2200):
        return None
    if not end_of_period:
        return date(year, month, 1)
    return date(year, month, calendar.monthrange(year, month)[1])


@dataclass(frozen=True, slots=True)
class _Period:
    started_on: date | None
    ended_on: date | None
    is_current: bool
    text: str


def _find_period(line: str) -> _Period | None:
    """The date range a line prints, if it prints one."""
    match = _DATE_RANGE.search(line)
    if match is None:
        return None
    end_raw = match.group("end")
    is_current = fold(end_raw).strip() in _PRESENT_WORDS or "momento" in fold(end_raw)
    return _Period(
        started_on=_parse_date_part(match.group("start"), end_of_period=False),
        ended_on=None if is_current else _parse_date_part(end_raw, end_of_period=True),
        is_current=is_current,
        text=match.group(0).strip(),
    )


# --------------------------------------------------------------------------- #
# Entry titles
# --------------------------------------------------------------------------- #

# Separators a resume uses between a role and a company on one line. A bare
# hyphen is only one when it is spaced, so "Full-Stack Developer" survives.
# `em` is deliberately absent: it separates a role from a company far less often
# than it appears inside a degree ("Bacharelado em Ciência da Computação").
_TITLE_SPLIT = re.compile(r"\s+[|·•]\s+|\s+[-–—]\s+|\s+@\s+|\s+\bat\b\s+|\s+\bna\b\s+")

# Recognition only. The value stored is the document's own wording, never this
# canonical form — the proposal has to be quotable back to the uploaded file.
_EMPLOYMENT_TYPES = frozenset(
    {
        "clt", "pj", "estagio", "internship", "intern", "trainee", "freelance",
        "freelancer", "autonomo", "tempo integral", "full time", "full-time",
        "part time", "part-time", "meio periodo", "contract", "contrato",
        "temporario", "voluntario", "aprendiz",
    }
)

_WORKPLACE_WORDS = frozenset(
    {"remoto", "remote", "hibrido", "hybrid", "presencial", "on site", "onsite"}
)


def _looks_like_place(fragment: str) -> bool:
    folded = squash(fragment)
    if folded in _WORKPLACE_WORDS:
        return True
    # "Recife, PE" / "Lisboa, Portugal": a comma and no digits.
    return "," in fragment and not any(char.isdigit() for char in fragment)


def _title_fragments(lines: Iterable[str]) -> list[str]:
    """A block of title lines, flattened into the parts it names."""
    parts: list[str] = []
    for line in lines:
        cleaned = _DATE_RANGE.sub("", line).strip(" .,;|·•-–—\t")
        if not cleaned:
            continue
        parts.extend(
            fragment.strip(" .,;\t") for fragment in _TITLE_SPLIT.split(cleaned) if fragment.strip()
        )
    return parts


# --------------------------------------------------------------------------- #
# Experience
# --------------------------------------------------------------------------- #


def _technologies_in(text: str) -> tuple[str, ...]:
    """The known technologies this text names, spelled as the document spells them."""
    found = mentioned_terms(text, sorted(KNOWN_TECHNOLOGIES))
    return tuple(spelling_in(text, term) for term in found)


def _entry_blocks(lines: Sequence[str]) -> list[tuple[list[str], list[str], _Period]]:
    """Split an experience section into (title lines, body lines, period).

    An entry is anchored on the line that prints its period, because that is the
    one element every resume layout puts on the entry itself. The title is the
    run of short non-bullet lines immediately above it — that covers both
    "Role — Company — Jan 2020-Present" on one line and the three-line stack
    LinkedIn exports.
    """
    anchors = [index for index, line in enumerate(lines) if _find_period(line) is not None]
    if not anchors:
        return []

    blocks: list[tuple[list[str], list[str], _Period]] = []
    consumed = 0
    for position, anchor in enumerate(anchors):
        start = anchor
        cursor = anchor - 1
        while (
            cursor >= consumed
            and start - cursor <= MAX_ENTRY_TITLE_LINES
            and lines[cursor].strip()
            and not _is_bullet(lines[cursor])
        ):
            start = cursor
            cursor -= 1

        next_anchor = anchors[position + 1] if position + 1 < len(anchors) else len(lines)
        body_end = next_anchor
        # Give the next entry its own title lines back.
        back = 0
        while (
            body_end - 1 > anchor
            and back < MAX_ENTRY_TITLE_LINES
            and body_end - 1 < len(lines)
            and lines[body_end - 1].strip()
            and not _is_bullet(lines[body_end - 1])
        ):
            body_end -= 1
            back += 1

        period = _find_period(lines[anchor])
        if period is None:  # pragma: no cover - anchors were selected by this test
            continue
        blocks.append((list(lines[start : anchor + 1]), list(lines[anchor + 1 : body_end]), period))
        # `body_end` is where the *next* entry's title starts, so it is the first
        # line the next iteration may still claim. Stopping at `next_anchor`
        # instead would leave every entry after the first with no title at all.
        consumed = body_end
    return blocks


def _experience_from(
    title_lines: Sequence[str], body_lines: Sequence[str], period: _Period
) -> IntakeExperience:
    fragments = _title_fragments(title_lines)

    employment_type: str | None = None
    location: str | None = None
    named: list[str] = []
    for fragment in fragments:
        if squash(fragment) in _EMPLOYMENT_TYPES and employment_type is None:
            employment_type = fragment
        elif _looks_like_place(fragment) and location is None:
            location = fragment
        else:
            named.append(fragment)

    role = named[0] if named else ""
    company = named[1] if len(named) > 1 else ""

    responsibilities = tuple(
        _debullet(line) for line in body_lines if _is_bullet(line) and _debullet(line)
    )
    prose = [line.strip() for line in body_lines if line.strip() and not _is_bullet(line)]

    block = "\n".join([*title_lines, *body_lines])
    return IntakeExperience(
        role=role,
        company=company,
        employment_type=employment_type,
        location=location,
        started_on=period.started_on,
        ended_on=period.ended_on,
        is_current=period.is_current,
        period_text=period.text,
        summary=" ".join(prose),
        responsibilities=responsibilities,
        technologies=_technologies_in(block),
    )


# --------------------------------------------------------------------------- #
# Lists
# --------------------------------------------------------------------------- #

_LIST_SPLIT = re.compile(r"[,;|•·/]|\s{2,}")


def _list_items(lines: Sequence[str], *, max_chars: int = MAX_SKILL_CHARS) -> tuple[str, ...]:
    """A comma-, bullet- or pipe-separated list, as the items it names.

    Order is preserved and duplicates collapse on their folded form, so
    "React" and "react" do not both end up as chips the user has to delete.
    """
    seen: dict[str, str] = {}
    for line in lines:
        text = _debullet(line) if _is_bullet(line) else line.strip()
        if not text:
            continue
        # A "Skills:" prefix on the same line as the list.
        text = re.sub(r"^[A-Za-zÀ-ÿ\s]{,24}:\s*", "", text)
        for raw in _LIST_SPLIT.split(text):
            # Only trailing punctuation is stripped, and only from the right: a
            # leading dot is part of the name in ".NET".
            item = raw.strip().lstrip("-–—•*·").rstrip(".,;:").strip()
            if not item or len(item) > max_chars:
                continue
            key = fold(item)
            seen.setdefault(key, item)
    return tuple(seen.values())


_KNOWN_LANGUAGES = frozenset(
    {
        "portugues", "portuguese", "ingles", "english", "espanhol", "spanish",
        "frances", "french", "alemao", "german", "italiano", "italian",
        "mandarim", "mandarin", "japones", "japanese", "coreano", "korean",
        "russo", "russian", "arabe", "arabic", "holandes", "dutch",
    }
)


def _languages_from(lines: Sequence[str]) -> tuple[str, ...]:
    """Languages named in the section, each with the level printed beside it."""
    found: dict[str, str] = {}
    for line in lines:
        text = _debullet(line) if _is_bullet(line) else line.strip()
        if not text:
            continue
        for part in re.split(r"[,;|]", text):
            fragment = part.strip(" .\t-–—")
            if not fragment:
                continue
            head = fold(fragment).split()[0] if fold(fragment).split() else ""
            if head in _KNOWN_LANGUAGES:
                found.setdefault(head, fragment)
    return tuple(found.values())


def _education_from(lines: Sequence[str]) -> tuple[IntakeEducation, ...]:
    """Each non-empty line of the section as one entry.

    Deliberately line-oriented: education blocks are short, and a wrong split
    here costs the user one correction on a screen they are already reading.
    """
    entries: list[IntakeEducation] = []
    for line in lines:
        text = _debullet(line) if _is_bullet(line) else line.strip()
        if not text:
            continue
        period = _find_period(text)
        without_period = _DATE_RANGE.sub("", text).strip(" .,;()|·•-–—\t")
        if not without_period and period is None:
            continue
        fragments = [
            fragment.strip(" .,;()\t")
            for fragment in _TITLE_SPLIT.split(without_period)
            if fragment.strip()
        ]
        if not fragments:
            continue
        entries.append(
            IntakeEducation(
                degree=fragments[0] if len(fragments) > 1 else "",
                institution=fragments[1] if len(fragments) > 1 else fragments[0],
                period_text=period.text if period is not None else "",
            )
        )
    return tuple(entries)


def _projects_from(lines: Sequence[str]) -> tuple[IntakeProject, ...]:
    projects: list[IntakeProject] = []
    for line in lines:
        text = _debullet(line) if _is_bullet(line) else line.strip()
        if not text:
            continue
        parts = _TITLE_SPLIT.split(text, maxsplit=1)
        name = parts[0].strip(" .,;:\t")
        description = parts[1].strip() if len(parts) > 1 else ""
        if not name:
            continue
        projects.append(
            IntakeProject(name=name, description=description, technologies=_technologies_in(text))
        )
    return tuple(projects)


# --------------------------------------------------------------------------- #
# The header block
# --------------------------------------------------------------------------- #


def _looks_like_name(line: str) -> bool:
    text = line.strip()
    if not text or len(text) > MAX_NAME_CHARS:
        return False
    if any(char.isdigit() for char in text) or _is_contact_line(text):
        return False
    words = text.split()
    return 1 < len(words) <= 6


# --------------------------------------------------------------------------- #
# The one entry point
# --------------------------------------------------------------------------- #


def extract(text: str) -> ResumeIntake:
    """Read an uploaded resume into a proposal the user confirms.

    Never raises on a document it cannot read: an unrecognised layout comes back
    as an empty proposal with warnings naming what was missing, and the user
    fills those fields in by hand — which is exactly the state they were in
    before uploading anything.
    """
    lines = [line.rstrip() for line in (text or "").splitlines()]
    if not any(line.strip() for line in lines):
        return ResumeIntake(warnings=("O arquivo enviado não tem texto legível.",))

    sections = _split_sections(lines)
    header = [line for line in sections.get("", []) if line.strip()]
    warnings: list[str] = []

    email_match = _EMAIL.search(text)
    phone_match = _PHONE.search(text)

    full_name: str | None = None
    headline: str | None = None
    location: str | None = None
    header_prose: list[str] = []
    for line in header:
        stripped = line.strip()
        if _is_contact_line(stripped):
            continue
        if full_name is None and _looks_like_name(stripped):
            full_name = stripped
            continue
        if headline is None and len(stripped) <= MAX_HEADLINE_CHARS and not _is_bullet(stripped):
            headline = stripped
            continue
        if location is None and _looks_like_place(stripped):
            location = stripped
            continue
        header_prose.append(stripped)

    # A headline that is really a place belongs in the location field.
    if headline is not None and location is None and _looks_like_place(headline):
        location, headline = headline, None

    summary_lines = [line.strip() for line in sections.get("summary", []) if line.strip()]
    summary = " ".join(summary_lines) if summary_lines else " ".join(header_prose)

    experience_lines = sections.get("experience", [])
    experiences = tuple(
        _experience_from(title, body, period)
        for title, body, period in _entry_blocks(experience_lines)
    )
    if not experiences:
        warnings.append(
            "Não reconhecemos as suas experiências no arquivo. Adicione-as você mesmo — "
            "elas são o que mais pesa na adaptação do currículo."
        )
    elif any(not entry.is_complete for entry in experiences):
        warnings.append(
            "Algumas experiências ficaram sem cargo ou sem empresa. Confira antes de salvar."
        )

    skills = _list_items(sections.get("skills", []))
    if not skills:
        # No skills section: the technologies the document itself names are still
        # the candidate's own words, so they are an honest starting point.
        skills = _technologies_in(text)
        if skills:
            warnings.append(
                "Não havia uma seção de tecnologias, então listamos as que aparecem no texto."
            )

    education = _education_from(sections.get("education", []))
    projects = _projects_from(sections.get("projects", []))
    certifications = _list_items(sections.get("certifications", []), max_chars=120)
    languages = _languages_from(sections.get("languages", []))

    return ResumeIntake(
        full_name=full_name,
        headline=headline,
        location=location,
        email=email_match.group(0) if email_match else None,
        phone=phone_match.group(0).strip() if phone_match else None,
        summary=summary or None,
        skills=skills,
        languages=languages,
        experiences=experiences,
        education=education,
        projects=projects,
        certifications=certifications,
        warnings=tuple(warnings),
    )


__all__ = [
    "IntakeEducation",
    "IntakeExperience",
    "IntakeProject",
    "ResumeIntake",
    "extract",
]
