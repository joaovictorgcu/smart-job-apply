"""A pure-Python stand-in for `LinkedInBrowserService` — no browser, no network.

It satisfies the `LinkedInService` protocol plus the extra surface the engine uses
(`configure`, `browser.is_open`, `has_open_draft`, storage-state import/export), so
it can replace the real service wholesale.

It is scriptable to return a chosen set of postings, to raise
`SecurityCheckpointError` at a chosen call, and to leave questions unanswered.
Most importantly it records whether `submit()` was ever reached — the assertion
that guards assisted mode.

`FakePage` is separate and much smaller: just the slice of the Playwright page API
that `BrowserSession.detect_checkpoint` touches, so checkpoint detection can be
tested against the real detector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.automation.contracts import (
    ApplicationDraft,
    FormAnswer,
    FormQuestion,
    JobPosting,
    SearchFilters,
    SessionState,
)
from app.automation.errors import (
    AlreadyAppliedError,
    EasyApplyUnavailableError,
    NotLoggedInError,
    SecurityCheckpointError,
)

CHECKPOINT_URL = "https://www.linkedin.com/checkpoint/challenge/AgH9x"

# Every language the detector has to recognize, taken from the marker list it
# actually uses. A test that drifts from `selectors.Checkpoint` should fail.
CHECKPOINT_MARKERS = (
    "Security verification",
    "Unusual activity",
    "Suspicious activity",
    "Verificação de segurança",
    "Atividade incomum",
    "Atividade suspeita",
)

# Browser-driving calls. Dry-run and kill-switch tests assert these never happen.
BROWSER_CALLS = frozenset(
    {"search_jobs", "fetch_job_details", "open_easy_apply", "fill_and_advance", "submit"}
)


@dataclass
class FakeLocator:
    """Playwright locator, reduced to what checkpoint detection calls."""

    matches: int = 0
    text: str = ""

    async def count(self) -> int:
        return self.matches

    # `timeout` mirrors Playwright's own signature; the detector passes it.
    async def inner_text(self, timeout: float | None = None) -> str:  # noqa: ASYNC109
        return self.text


@dataclass
class FakePage:
    """The slice of a Playwright page that `detect_checkpoint` reads."""

    url: str = "https://www.linkedin.com/jobs/search/?keywords=python"
    body_text: str = "Python jobs"
    elements: tuple[str, ...] = ()
    closed: bool = False
    title_text: str = "Jobs | LinkedIn"

    def is_closed(self) -> bool:
        return self.closed

    def locator(self, selector: str) -> FakeLocator:
        if selector == "body":
            return FakeLocator(matches=1, text=self.body_text)
        return FakeLocator(matches=1 if selector in self.elements else 0)

    async def content(self) -> str:
        return f"<html><body>{self.body_text}</body></html>"

    async def title(self) -> str:
        return self.title_text

    @classmethod
    def checkpoint(
        cls, *, marker: str = CHECKPOINT_MARKERS[0], url: str = CHECKPOINT_URL
    ) -> FakePage:
        return cls(
            url=url,
            body_text=f"{marker}\nPlease confirm it is you.",
            title_text="Security Verification | LinkedIn",
        )


def make_postings(count: int, *, prefix: str = "job", easy_apply: bool = True) -> list[JobPosting]:
    return [
        JobPosting(
            external_id=f"{prefix}-{index}",
            title=f"Backend Engineer {index}",
            company=f"Company {index}",
            location="Remote",
            url=f"https://www.linkedin.com/jobs/view/{prefix}-{index}",
            description=f"Python role number {index}. FastAPI and SQL required.",
            workplace_type="remote",
            easy_apply=easy_apply,
        )
        for index in range(1, count + 1)
    ]


class FakeBrowser:
    """Stands in for `service.browser`, which the engine inspects directly."""

    def __init__(self, service: FakeLinkedInService) -> None:
        self._service = service
        self.profile_dir = Path("/tmp/fake-browser-profile")

    @property
    def is_open(self) -> bool:
        return self._service.browser_open

    @property
    def blocked_reason(self) -> str | None:
        return self._service.blocked_reason


@dataclass
class FakeLinkedInService:
    """In-memory `LinkedInBrowserService`.

    Knobs:
        postings / job_count: what `search_jobs` returns.
        checkpoint_on:        method name that raises `SecurityCheckpointError`.
        checkpoint_after:     how many successful calls to that method first.
        error_on / error:     raise an arbitrary error at a chosen method.
        unanswered:           questions `fill_and_advance` reports as unanswered,
                              which keeps `ready_to_submit` False.
        logged_in:            when False, browser-driving calls raise
                              `NotLoggedInError`.
    """

    user_id: int = 1
    postings: list[JobPosting] | None = None
    job_count: int = 3
    questions: list[FormQuestion] | None = None
    unanswered: list[FormQuestion] = field(default_factory=list)
    total_steps: int = 3
    checkpoint_on: str | None = None
    checkpoint_after: int = 0
    checkpoint_reason: str = "Security verification detected."
    error_on: str | None = None
    error: Exception | None = None
    logged_in: bool = True
    browser_open: bool = True
    submit_result: bool = True
    already_applied_ids: set[str] = field(default_factory=set)
    no_easy_apply_ids: set[str] = field(default_factory=set)

    calls: list[str] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)
    submitted: list[str] = field(default_factory=list)
    filled: list[list[FormAnswer]] = field(default_factory=list)
    cover_letters: list[str | None] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    storage_state: dict[str, Any] = field(default_factory=dict)
    submit_called: bool = False
    blocked: bool = False
    blocked_reason: str | None = None
    current_external_id: str | None = None
    throttle: Any = None
    resume_path: str | None = None

    def __post_init__(self) -> None:
        self.browser = FakeBrowser(self)

    # --- bookkeeping ------------------------------------------------------

    def _record(self, name: str, *, needs_login: bool = False) -> None:
        self.calls.append(name)
        if self.error_on == name and self.error is not None:
            raise self.error
        if self.checkpoint_on == name and self.calls.count(name) > self.checkpoint_after:
            self.blocked = True
            self.blocked_reason = self.checkpoint_reason
            raise SecurityCheckpointError(self.checkpoint_reason)
        if needs_login and not self.logged_in:
            raise NotLoggedInError("The stored LinkedIn session is no longer valid.")

    def call_count(self, name: str) -> int:
        return self.calls.count(name)

    @property
    def browser_calls(self) -> list[str]:
        return [name for name in self.calls if name in BROWSER_CALLS]

    @property
    def available_postings(self) -> list[JobPosting]:
        if self.postings is not None:
            return self.postings
        return make_postings(self.job_count)

    @property
    def default_questions(self) -> list[FormQuestion]:
        if self.questions is not None:
            return self.questions
        return [
            FormQuestion(
                field_id="q-years",
                label="Years of Python experience?",
                kind="number",
                required=True,
            ),
            FormQuestion(
                field_id="q-auth",
                label="Are you authorized to work in this country?",
                kind="radio",
                options=["Yes", "No"],
                required=True,
            ),
        ]

    # --- engine-facing extras ---------------------------------------------

    def configure(self, *, throttle: Any = None, resume_path: str | None = None) -> None:
        self.throttle = throttle
        self.resume_path = resume_path

    def has_open_draft(self, external_id: str | None = None) -> bool:
        if self.current_external_id is None:
            return False
        return external_id is None or external_id == self.current_external_id

    async def export_storage_state(self) -> dict[str, Any]:
        self.calls.append("export_storage_state")
        return {"cookies": [{"name": "li_at", "value": "fake-session"}], "origins": []}

    async def import_storage_state(self, state: dict[str, Any]) -> None:
        self.calls.append("import_storage_state")
        self.storage_state = dict(state)
        self.logged_in = True

    def page(self, *, blocked: bool = False) -> FakePage:
        return FakePage.checkpoint() if blocked else FakePage()

    # --- LinkedInService ---------------------------------------------------

    async def start(self) -> SessionState:
        self._record("start")
        self.browser_open = True
        return await self.get_state()

    async def stop(self) -> None:
        self._record("stop")
        self.browser_open = False
        self.current_external_id = None

    async def get_state(self) -> SessionState:
        self.calls.append("get_state")
        return SessionState(
            browser_open=self.browser_open,
            logged_in=self.logged_in,
            blocked=self.blocked,
            blocked_reason=self.blocked_reason,
            current_url=CHECKPOINT_URL if self.blocked else "https://www.linkedin.com/feed/",
            display_name="Test Candidate" if self.logged_in else None,
        )

    async def wait_for_login(self, timeout_seconds: int = 300) -> SessionState:
        self._record("wait_for_login")
        self.logged_in = True
        self.browser_open = True
        return await self.get_state()

    async def search_jobs(self, filters: SearchFilters) -> list[JobPosting]:
        self._record("search_jobs", needs_login=True)
        postings = self.available_postings
        if filters.easy_apply_only:
            postings = [posting for posting in postings if posting.easy_apply]
        return postings[: filters.max_results]

    async def fetch_job_details(self, external_id: str) -> JobPosting:
        self._record("fetch_job_details", needs_login=True)
        for posting in self.available_postings:
            if posting.external_id == external_id:
                return posting
        return JobPosting(
            external_id=external_id,
            title="Backend Engineer",
            company="Acme Corp",
            location="Remote",
            url=f"https://www.linkedin.com/jobs/view/{external_id}",
            description="Python role. FastAPI and SQL required.",
            easy_apply=True,
        )

    async def open_easy_apply(self, external_id: str) -> list[FormQuestion]:
        self._record("open_easy_apply", needs_login=True)
        if external_id in self.no_easy_apply_ids:
            raise EasyApplyUnavailableError(f"Job {external_id} has no Easy Apply.")
        if external_id in self.already_applied_ids:
            raise AlreadyAppliedError(f"Job {external_id} already has an application.")
        self.opened.append(external_id)
        self.current_external_id = external_id
        return list(self.default_questions)

    async def fill_and_advance(
        self, answers: list[FormAnswer], *, cover_letter: str | None = None
    ) -> ApplicationDraft:
        self._record("fill_and_advance", needs_login=True)
        self.filled.append(list(answers))
        self.cover_letters.append(cover_letter)
        return ApplicationDraft(
            job_external_id=self.current_external_id or "unknown",
            questions=list(self.default_questions),
            answers=list(answers),
            unanswered=list(self.unanswered),
            total_steps=self.total_steps,
            current_step=self.total_steps,
            resume_attached=True,
            cover_letter_attached=cover_letter is not None,
            # A form with open questions is never presented as ready.
            ready_to_submit=not self.unanswered,
            notes=[],
        )

    async def submit(self) -> bool:
        self._record("submit", needs_login=True)
        self.submit_called = True
        self.submitted.append(self.current_external_id or "unknown")
        self.current_external_id = None
        return self.submit_result

    async def discard(self) -> None:
        self._record("discard")
        self.current_external_id = None

    async def capture_screenshot(self, name: str) -> str | None:
        self.calls.append("capture_screenshot")
        path = f"/tmp/fake-screenshots/{name}.png"
        self.screenshots.append(path)
        return path
