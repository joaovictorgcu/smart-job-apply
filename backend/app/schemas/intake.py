"""What we read out of an uploaded resume, and what the user confirms of it.

Two shapes, and the split is the point. `ResumeIntakeRead` is a *proposal*: it
is never persisted, and it carries `warnings` so a layout the parser did not
recognise is visible rather than silently empty. `IntakeApply` is the user's
answer — the corrected version they pressed a button on — and it is the only
thing that reaches the database.

`experiences` on the apply side reuses `ExperienceCreate` rather than defining a
parallel shape, so a position saved by the onboarding wizard passes exactly the
same validation as one typed into the profile page.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.resume import ExperienceCreate
from app.schemas.user import ProfileRead


class IntakeExperienceRead(BaseModel):
    """One position the parser found. `is_complete` drives the "check this" flag."""

    role: str = ""
    company: str = ""
    employment_type: str | None = None
    location: str | None = None
    started_on: date | None = None
    ended_on: date | None = None
    is_current: bool = False
    # The period exactly as the document prints it, so the user can compare the
    # parsed dates against their own wording.
    period_text: str = ""
    summary: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    is_complete: bool = False


class IntakeEducationRead(BaseModel):
    institution: str = ""
    degree: str = ""
    period_text: str = ""


class IntakeProjectRead(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)


class ResumeIntakeRead(BaseModel):
    """Everything one uploaded file said. Nothing here has been saved."""

    full_name: str | None = None
    headline: str | None = None
    location: str | None = None
    email: str | None = None
    phone: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    experiences: list[IntakeExperienceRead] = Field(default_factory=list)
    education: list[IntakeEducationRead] = Field(default_factory=list)
    projects: list[IntakeProjectRead] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    # What could not be read, in the user's language. An empty proposal with no
    # warning would read as "you have no experience", which is worse than a gap.
    warnings: list[str] = Field(default_factory=list)

    # The plain text the file yielded, and the stored filename when one was
    # uploaded in the same request. Returned so the confirm screen can offer to
    # keep the text the AI will read without a second round trip.
    resume_text: str = ""
    resume_filename: str | None = None


class IntakeApply(BaseModel):
    """The confirmed proposal. Only what is here is written.

    Fields left out are not touched, which is what makes re-running the wizard
    on an account that already has a profile safe.
    """

    full_name: str | None = Field(default=None, max_length=200)
    headline: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    summary: str | None = None
    years_of_experience: int | None = Field(default=None, ge=0, le=70)
    resume_text: str | None = None
    skills: list[str] | None = Field(default=None, max_length=200)
    preferred_languages: list[str] | None = Field(default=None, max_length=20)
    experiences: list[ExperienceCreate] = Field(default_factory=list, max_length=40)
    # Destructive and therefore opt-in: the confirm screen asks before sending
    # it, and it only ever removes positions this same account entered.
    replace_experiences: bool = False


class IntakeApplied(BaseModel):
    """What the confirmation actually changed."""

    profile: ProfileRead
    experiences_created: int = 0
    experiences_removed: int = 0
