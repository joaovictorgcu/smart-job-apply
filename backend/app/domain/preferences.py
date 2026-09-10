"""What the user is looking for, and what that rules out.

Two jobs, both deliberately deterministic and both here rather than in a
prompt.

**Screening.** A posting the user has already said no to — "sênior", "call
center", "presencial" — should not cost a model call to reject. `screen` is the
cheap, explainable pass that runs *before* scoring: it either lets the posting
through or names the user's own word that stopped it. It cannot skip a posting
for a reason the user did not write down.

**Querying.** `search_keywords` turns the stated role into the query string a
portal search runs, so the user never has to fill a search form to get started.

The asymmetry that matters: this module can *reject* a posting and *rank* a
term, and it can do neither to the resume. Nothing here is ever written into a
document — `priority_technologies` only re-ranks terms the candidate already
claims, exactly like the posting's own text does in `app.domain.resume`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.language import fold
from app.domain.technologies import mentions

# The query a portal search runs. Past this the string stops being a search and
# starts being a filter the portal silently truncates.
MAX_KEYWORD_TERMS = 4
MAX_KEYWORD_CHARS = 300
# Screening evidence is rendered in a list cell, like `Job.skip_reason`.
MAX_REASON_CHARS = 300

# The vocabularies the portal filters already speak, so a preference maps onto a
# search with no translation table. Anything outside them is the user's own free
# text and is only ever matched, never sent as a filter value.
SENIORITY_VALUES: tuple[str, ...] = (
    "internship",
    "entry",
    "associate",
    "mid-senior",
    "director",
    "executive",
)
WORK_MODELS: tuple[str, ...] = ("remote", "hybrid", "on-site")

# How a posting spells a workplace type, mapped to the value above. A posting
# says "Remoto"; the preference says "remote"; they are the same answer.
_WORKPLACE_SPELLINGS: dict[str, str] = {
    "remote": "remote",
    "remoto": "remote",
    "teletrabalho": "remote",
    "hybrid": "hybrid",
    "hibrido": "hybrid",
    "on-site": "on-site",
    "on site": "on-site",
    "onsite": "on-site",
    "presencial": "on-site",
}


def normalize_workplace(value: str | None) -> str | None:
    """A posting's workplace wording as one of `WORK_MODELS`, or None.

    None means "the posting did not say", which is never grounds for skipping:
    a missing field is not a mismatch.
    """
    if not value:
        return None
    return _WORKPLACE_SPELLINGS.get(fold(value).strip())


@dataclass(frozen=True, slots=True)
class JobPreferenceRules:
    """The standing answer to "what am I looking for", as plain data."""

    target_role: str = ""
    alternative_roles: tuple[str, ...] = ()
    seniority: tuple[str, ...] = ()
    work_models: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    salary_min: int | None = None
    salary_currency: str = "BRL"
    priority_technologies: tuple[str, ...] = ()
    excluded_terms: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """True when nothing has been stated, so nothing may be ruled out."""
        return not (
            self.target_role.strip()
            or self.alternative_roles
            or self.seniority
            or self.work_models
            or self.locations
            or self.salary_min
            or self.priority_technologies
            or self.excluded_terms
        )

    def roles(self) -> tuple[str, ...]:
        """The main role first, then the alternatives, without repeats."""
        ordered: dict[str, str] = {}
        for role in (self.target_role, *self.alternative_roles):
            cleaned = (role or "").strip()
            if cleaned:
                ordered.setdefault(fold(cleaned), cleaned)
        return tuple(ordered.values())


@dataclass(frozen=True, slots=True)
class PreferenceVerdict:
    """Whether a posting survives the user's stated preferences, and why not.

    `reason` is written for the user and quotes their own term, because that is
    the only thing that makes a skipped posting reviewable: "you asked me to
    skip anything saying 'presencial'" is arguable, "filtered" is not.
    """

    excluded: bool = False
    reason: str | None = None
    matched_term: str | None = None

    def __bool__(self) -> bool:
        """Truthy when the posting passes, so `if verdict:` reads correctly."""
        return not self.excluded


PASSES = PreferenceVerdict()


def _first_match(terms: Iterable[str], haystacks: Sequence[str]) -> tuple[str, str] | None:
    """The first stated term any of these fields names, with the field's text."""
    for term in terms:
        cleaned = term.strip()
        if not cleaned:
            continue
        for haystack in haystacks:
            if haystack and mentions(haystack, cleaned):
                return cleaned, haystack
    return None


def screen(
    rules: JobPreferenceRules,
    *,
    title: str,
    location: str | None = None,
    workplace_type: str | None = None,
) -> PreferenceVerdict:
    """Decide whether a posting is worth scoring at all.

    Matched against the title, the location and the workplace type — the fields
    that describe *what the job is*. The description is deliberately excluded:
    "call center" inside a paragraph about the company's clients does not make
    a backend role a call-centre job, and a screen that fires on it teaches the
    user to stop trusting the skip list.

    A preference the user has not stated can never exclude anything, which is
    why an empty `work_models` passes every posting and a posting that does not
    say its workplace type passes too.
    """
    if rules.is_empty:
        return PASSES

    fields = [title or "", location or "", workplace_type or ""]

    hit = _first_match(rules.excluded_terms, fields)
    if hit is not None:
        term, _ = hit
        reason = f'You asked to skip postings mentioning "{term}".'
        return PreferenceVerdict(excluded=True, reason=reason[:MAX_REASON_CHARS], matched_term=term)

    if rules.work_models:
        posted = normalize_workplace(workplace_type)
        if posted is not None and posted not in rules.work_models:
            wanted = ", ".join(rules.work_models)
            reason = f"This posting is {posted}, and you are looking for {wanted}."
            return PreferenceVerdict(
                excluded=True, reason=reason[:MAX_REASON_CHARS], matched_term=posted
            )

    return PASSES


def search_keywords(rules: JobPreferenceRules) -> str:
    """The query string a portal search runs for these preferences.

    The roles, OR-joined, capped: a portal treats a long disjunction as noise
    and quietly returns the intersection of nothing. Technologies are left out
    on purpose — they belong in the ranking, not the query, and adding them
    narrows a search that is already narrow enough to miss good postings.
    """
    roles = rules.roles()[:MAX_KEYWORD_TERMS]
    if not roles:
        return ""
    joined = " OR ".join(f'"{role}"' if " " in role else role for role in roles)
    return joined[:MAX_KEYWORD_CHARS]


def search_location(rules: JobPreferenceRules) -> str | None:
    """The one location a portal search filter takes, or None for anywhere."""
    for location in rules.locations:
        cleaned = location.strip()
        if cleaned:
            return cleaned[:200]
    return None


def search_remote_filter(rules: JobPreferenceRules) -> str | None:
    """The one workplace value a portal search filter takes.

    A single choice, so several stated models mean "do not filter at all" —
    the screen above still rejects what does not match, and asking the portal
    for one of them would hide the others outright.
    """
    return rules.work_models[0] if len(rules.work_models) == 1 else None


__all__ = [
    "MAX_KEYWORD_TERMS",
    "PASSES",
    "SENIORITY_VALUES",
    "WORK_MODELS",
    "JobPreferenceRules",
    "PreferenceVerdict",
    "normalize_workplace",
    "screen",
    "search_keywords",
    "search_location",
    "search_remote_filter",
]
