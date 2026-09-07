"""Tailored-resume request/response schemas.

Two representations of the same idea, and they are not interchangeable:

* `TailoredResumeRead` is the AI narrative for one job — markdown prose,
  reached from the job screen.
* `ApplicationResumeRead` is the resume one application actually presents:
  structured, derived from the master with no model call, diffable against the
  snapshot it came from, and editable field by field.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.ai.schemas import StretchFlag
from app.domain.resume import ResumeChange, ResumeDocument


class CVChangeOut(BaseModel):
    section: str
    action: str
    detail: str


class TailoredResumeRead(BaseModel):
    job_id: int
    content: str
    changes: list[CVChangeOut] = Field(default_factory=list)
    # Requirements the resume genuinely cannot back — surfaced, not invented.
    unsupported_requirements: list[str] = Field(default_factory=list)
    # Technologies the invention guard found in the tailored text but not the
    # source; the user verifies each one.
    invention_flags: list[str] = Field(default_factory=list)
    # Grounded but aggressive claims — keep, soften, or drop is the user's call.
    stretch_flags: list[StretchFlag] = Field(default_factory=list)
    summary: str | None = None
    model: str | None = None
    was_edited: bool = False
    # True when the profile changed after this draft was generated.
    is_stale: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TailoredResumeUpdate(BaseModel):
    """The user's edits to the tailored resume before they use it."""

    content: str = Field(min_length=1)


class ApplicationResumeRead(BaseModel):
    """The resume one application presents, and where it came from.

    `document` is what this application shows an employer. `base_document` is
    the master as it stood when the version was derived — sent alongside so the
    UI can show the difference without a second request, and so "editing my
    main resume changed nothing here" is visible rather than promised.
    """

    application_id: int
    job_id: int
    job_title: str | None = None
    job_company: str | None = None

    document: ResumeDocument
    base_document: ResumeDocument
    # The candidate's own terms this posting asked for, strongest first.
    focus: list[str] = Field(default_factory=list)
    changes: list[ResumeChange] = Field(default_factory=list)
    # Technologies present in this version but not in the master. The rule-based
    # derivation cannot produce any; an edit by hand can.
    invention_flags: list[str] = Field(default_factory=list)
    # "rules" while it is the derivation's output, "user" once edited by hand.
    source: str = "rules"
    # True when the master resume changed after this version was derived. The
    # version itself is untouched — this is an offer to re-derive, not a warning
    # that something moved underneath the user.
    is_stale: bool = False
    # The version rendered as markdown, for copying into a form or a portal.
    markdown: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApplicationResumeUpdate(BaseModel):
    """The user's edits to one application's resume version.

    The whole document is sent back, not a patch: the editor works on the
    document as a unit, and a field-by-field patch protocol would let two
    concurrent edits interleave into a resume neither of them wrote.

    Company, role and period are checked against the snapshot server-side —
    a version re-emphasizes the past, it does not rewrite it.
    """

    document: ResumeDocument
