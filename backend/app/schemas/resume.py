"""The master resume, and the per-application snapshot derived from it.

Two vocabularies on purpose. `Experience*` is the master resume the user edits
once, on the profile page. `ApplicationResume*` is one application's frozen copy,
plus the report of what the derivation changed and how well the profile adheres
to the posting. Nothing in the second shape can be written back into the first.

Every user-facing sentence about these numbers is composed in the frontend, so
the factors and changes here carry counts and terms rather than prose: the
derivation is deterministic and local, and generating Portuguese in the backend
when the whole UI vocabulary lives in `frontend/src` is how two wordings start
drifting apart.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import ApplicationStatus
from app.schemas.common import ORMModel

MAX_BULLET_CHARS = 600
MAX_BULLETS = 40
MAX_TERMS = 60


class ProjectEntry(BaseModel):
    """One project inside an experience, in the candidate's own words."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=MAX_BULLET_CHARS)
    technologies: list[str] = Field(default_factory=list, max_length=MAX_TERMS)


class ExperienceBase(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    employment_type: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=200)
    started_on: date | None = None
    ended_on: date | None = None
    is_current: bool = False
    summary: str | None = Field(default=None, max_length=2000)
    responsibilities: list[str] = Field(default_factory=list, max_length=MAX_BULLETS)
    technologies: list[str] = Field(default_factory=list, max_length=MAX_TERMS)
    results: list[str] = Field(default_factory=list, max_length=MAX_BULLETS)
    projects: list[ProjectEntry] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _check_period(self) -> ExperienceBase:
        # A period that runs backwards would make every recency tiebreak wrong,
        # and "current with an end date" is two contradictory claims about the
        # same job — both are the user's typo, caught before they are persisted.
        if self.started_on and self.ended_on and self.ended_on < self.started_on:
            raise ValueError("ended_on cannot be earlier than started_on.")
        if self.is_current and self.ended_on is not None:
            raise ValueError("A current position cannot have an end date.")
        return self


class ExperienceCreate(ExperienceBase):
    """A new position on the master resume. Appended last unless told otherwise."""

    position: int | None = Field(default=None, ge=0, le=999)


class ExperienceUpdate(BaseModel):
    """Partial edit of one position. Only the fields sent are touched."""

    company: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, min_length=1, max_length=200)
    employment_type: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=200)
    started_on: date | None = None
    ended_on: date | None = None
    is_current: bool | None = None
    summary: str | None = Field(default=None, max_length=2000)
    responsibilities: list[str] | None = Field(default=None, max_length=MAX_BULLETS)
    technologies: list[str] | None = Field(default=None, max_length=MAX_TERMS)
    results: list[str] | None = Field(default=None, max_length=MAX_BULLETS)
    projects: list[ProjectEntry] | None = Field(default=None, max_length=20)
    position: int | None = Field(default=None, ge=0, le=999)


class ExperienceRead(ORMModel):
    id: int
    company: str
    role: str
    employment_type: str | None = None
    location: str | None = None
    started_on: date | None = None
    ended_on: date | None = None
    is_current: bool = False
    summary: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    position: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MasterResumeRead(BaseModel):
    """The master resume as one document: the profile's text plus its positions.

    This is the "voltar para o currículo principal" destination — the thing every
    application's copy is derived from, and the only place a fact about the
    candidate can be changed.
    """

    headline: str | None = None
    location: str | None = None
    summary: str | None = None
    years_of_experience: int | None = None
    skills: list[str] = Field(default_factory=list)
    resume_text: str | None = None
    resume_filename: str | None = None
    experiences: list[ExperienceRead] = Field(default_factory=list)
    # Hash of everything above. An application snapshot whose fingerprint no
    # longer matches this was derived from an older master.
    fingerprint: str
    updated_at: datetime | None = None


class AdaptedProject(BaseModel):
    """A project this posting had a reason to see."""

    name: str
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    company: str = ""
    role: str = ""
    matched_terms: list[str] = Field(default_factory=list)


class AdaptedExperience(BaseModel):
    """One experience as this application presents it.

    Same facts as the master position, reordered: `responsibilities` and
    `results` lead with the candidate's own sentences this posting asks about,
    and `technologies` leads with the matched ones. `promoted` of `matched_terms`
    is what makes "the description changed for this vacancy" checkable.
    """

    experience_id: int | None = None
    company: str
    role: str
    location: str | None = None
    employment_type: str | None = None
    started_on: date | None = None
    ended_on: date | None = None
    is_current: bool = False
    summary: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    projects: list[AdaptedProject] = Field(default_factory=list)
    relevance: int = 0
    matched_terms: list[str] = Field(default_factory=list)
    promoted: int = 0


class ResumeChange(BaseModel):
    """One reported edit. `kind` is a closed set; the label is the frontend's."""

    kind: str
    target: str
    terms: list[str] = Field(default_factory=list)
    matched: int = 0
    total: int = 0


class FitFactor(BaseModel):
    """One axis of the adherence figure, with the counts that produced it."""

    factor: str
    score: int
    weight_pct: int
    matched: int = 0
    total: int = 0
    terms: list[str] = Field(default_factory=list)


class ApplicationResumeRead(BaseModel):
    """The resume one application is using, with the report of how it got there."""

    application_id: int
    job_id: int
    job_title: str | None = None
    job_company: str | None = None
    version: int = 1

    headline: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    highlighted_skills: list[str] = Field(default_factory=list)
    emphasized_technologies: list[str] = Field(default_factory=list)
    experiences: list[AdaptedExperience] = Field(default_factory=list)
    projects: list[AdaptedProject] = Field(default_factory=list)
    changes: list[ResumeChange] = Field(default_factory=list)

    # Empty factors mean the posting named nothing recognisable, so there is no
    # adherence to report; `fit_score` is 0 and the UI hides the figure rather
    # than showing a confident-looking zero.
    fit_score: int = 0
    fit_factors: list[FitFactor] = Field(default_factory=list)
    uncovered_requirements: list[str] = Field(default_factory=list)

    model: str | None = None
    was_edited: bool = False
    # True when the master resume changed after this snapshot was derived. Stale
    # is not wrong: the snapshot is still exactly what this application presents.
    is_stale: bool = False
    adapted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdaptedExperienceEdit(BaseModel):
    """The parts of one adapted experience the reviewer may rewrite.

    Company, role and period are not here: this screen adapts a resume, it does
    not invent a job history, and letting the request restate them would be the
    one hole through which a fabricated employer could enter. Neither are
    `relevance`/`matched_terms`/`promoted` — those are the derivation's own
    report, and a client that could rewrite them could lie about what happened.
    """

    summary: str = Field(default="", max_length=2000)
    responsibilities: list[str] = Field(default_factory=list, max_length=MAX_BULLETS)
    technologies: list[str] = Field(default_factory=list, max_length=MAX_TERMS)
    results: list[str] = Field(default_factory=list, max_length=MAX_BULLETS)


class ApplicationResumeUpdate(BaseModel):
    """The reviewer's edits to this application's copy — and only this one."""

    headline: str | None = Field(default=None, max_length=300)
    summary: str | None = Field(default=None, max_length=4000)
    skills: list[str] | None = Field(default=None, max_length=MAX_TERMS)
    # Positional: the list must be the same length as the stored one, so a stale
    # editor is rejected instead of silently reassigning one job's bullets to
    # another. See `resume_service.update_application_resume`.
    experiences: list[AdaptedExperienceEdit] | None = Field(default=None, max_length=60)


class ResumeVersionSummary(BaseModel):
    """One row of "the other versions of my resume".

    Enough to tell them apart and navigate to them, and no document content: the
    point of this list is that the user can see their versions are per-vacancy
    and independent, not read four resumes at once.
    """

    application_id: int
    job_id: int
    job_title: str
    job_company: str
    application_status: ApplicationStatus
    version: int = 1
    fit_score: int = 0
    has_fit: bool = False
    highlighted_count: int = 0
    was_edited: bool = False
    is_stale: bool = False
    updated_at: datetime | None = None
