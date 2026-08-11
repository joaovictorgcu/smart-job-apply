"""Boundary between the business logic and Playwright.

`Engine` -> `LinkedInService` -> Playwright. The engine and the services know only
these structures; if LinkedIn changes its interface, the fix stays confined to the
`LinkedInService` implementation (`automation/linkedin/*`) and `selectors.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

QuestionKind = Literal["text", "textarea", "number", "select", "radio", "checkbox", "unknown"]


@dataclass(slots=True)
class SearchFilters:
    """Normalized search filters (no LinkedIn URL details)."""

    keywords: str
    location: str | None = None
    remote_filter: str | None = None
    date_posted: str | None = None
    experience_levels: list[str] = field(default_factory=list)
    easy_apply_only: bool = True
    max_results: int = 25


@dataclass(slots=True)
class JobPosting:
    """A job as seen on LinkedIn (nothing Playwright-specific)."""

    external_id: str
    title: str
    company: str
    location: str | None = None
    url: str | None = None
    description: str | None = None
    workplace_type: str | None = None
    easy_apply: bool = False
    posted_at: datetime | None = None
    already_applied: bool = False


@dataclass(slots=True)
class FormQuestion:
    """A single field of the Easy Apply form."""

    field_id: str
    label: str
    kind: QuestionKind = "unknown"
    options: list[str] = field(default_factory=list)
    required: bool = False
    current_value: str | None = None


@dataclass(slots=True)
class FormAnswer:
    """A value to fill into a field."""

    field_id: str
    value: str
    kind: QuestionKind = "unknown"


@dataclass(slots=True)
class ApplicationDraft:
    """A filled-in form, halted at the review step, awaiting approval."""

    job_external_id: str
    questions: list[FormQuestion] = field(default_factory=list)
    answers: list[FormAnswer] = field(default_factory=list)
    unanswered: list[FormQuestion] = field(default_factory=list)
    total_steps: int | None = None
    current_step: int | None = None
    resume_attached: bool = False
    cover_letter_attached: bool = False
    ready_to_submit: bool = False
    screenshot_path: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SessionState:
    browser_open: bool = False
    logged_in: bool = False
    blocked: bool = False
    blocked_reason: str | None = None
    current_url: str | None = None
    display_name: str | None = None


@runtime_checkable
class LinkedInService(Protocol):
    """What the engine is allowed to ask of LinkedIn.

    Every implementation must raise the errors from `automation.errors` — above all
    `SecurityCheckpointError`, which halts everything.
    """

    async def start(self) -> SessionState:
        """Open the browser (restoring the saved session, if there is one)."""
        ...

    async def stop(self) -> None:
        """Close the browser and persist the session state."""
        ...

    async def get_state(self) -> SessionState:
        ...

    async def wait_for_login(self, timeout_seconds: int = 300) -> SessionState:
        """Wait for the user to log in manually in the open window."""
        ...

    async def search_jobs(self, filters: SearchFilters) -> list[JobPosting]:
        """Return matching jobs (Easy Apply only, if requested)."""
        ...

    async def fetch_job_details(self, external_id: str) -> JobPosting:
        """Open the job and return its full description."""
        ...

    async def open_easy_apply(self, external_id: str) -> list[FormQuestion]:
        """Open the Easy Apply modal and return the fields of the current step."""
        ...

    async def fill_and_advance(
        self, answers: list[FormAnswer], *, cover_letter: str | None = None
    ) -> ApplicationDraft:
        """Fill in, advance through the steps and **stop** at the review. Never submits."""
        ...

    async def submit(self) -> bool:
        """Click submit. Only ever called after explicit user approval."""
        ...

    async def discard(self) -> None:
        """Close the modal, discarding the draft."""
        ...

    async def capture_screenshot(self, name: str) -> str | None:
        """Capture the current screen (for the dashboard and for debugging)."""
        ...


@dataclass(slots=True)
class ProfileContext:
    """User data handed to the AI and to the form filling (without touching the ORM)."""

    full_name: str | None = None
    email: str | None = None
    headline: str | None = None
    location: str | None = None
    phone: str | None = None
    years_of_experience: int | None = None
    summary: str | None = None
    resume_text: str | None = None
    resume_path: str | None = None
    skills: list[str] = field(default_factory=list)
    answer_bank: dict[str, Any] = field(default_factory=dict)
    preferred_languages: list[str] = field(default_factory=list)
