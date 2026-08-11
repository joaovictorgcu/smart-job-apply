"""The single LinkedIn facade the engine is allowed to talk to.

`LinkedInBrowserService` implements the `LinkedInService` Protocol by delegating
to the page objects. Everything Playwright-shaped stops here: raw
`playwright.Error` / `TimeoutError` are translated into the project's error
hierarchy, and `raise_if_blocked()` runs before and after every navigation so a
security challenge can never be silently worked around.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.automation.browser import BrowserSession
from app.automation.contracts import (
    ApplicationDraft,
    FormAnswer,
    FormQuestion,
    JobPosting,
    SearchFilters,
    SessionState,
)
from app.automation.errors import (
    AutomationError,
    NotLoggedInError,
    UnexpectedPageError,
)
from app.automation.linkedin.apply import EasyApplyModal
from app.automation.linkedin.job import JobDetailPage
from app.automation.linkedin.search import JobSearchPage
from app.automation.throttle import Throttle
from app.observability import get_logger

logger = get_logger(__name__)


class LinkedInBrowserService:
    """Playwright-backed implementation of `LinkedInService`."""

    def __init__(
        self,
        user_id: int,
        *,
        throttle: Throttle | None = None,
        resume_path: str | None = None,
        browser: BrowserSession | None = None,
    ) -> None:
        self.user_id = user_id
        self.throttle = throttle or Throttle()
        self.browser = browser or BrowserSession(user_id)
        self._search = JobSearchPage(self.browser, self.throttle)
        self._job = JobDetailPage(self.browser, self.throttle)
        self._apply = EasyApplyModal(self.browser, self.throttle, resume_path=resume_path)
        self._display_name: str | None = None
        self._logged_in = False

    # --- Configuration ----------------------------------------------------

    def configure(
        self, *, throttle: Throttle | None = None, resume_path: str | None = None
    ) -> None:
        """Refresh the per-user knobs without recreating the browser session."""
        if throttle is not None:
            self.throttle = throttle
            self._search = JobSearchPage(self.browser, throttle)
            self._job = JobDetailPage(self.browser, throttle)
            self._apply = EasyApplyModal(
                self.browser, throttle, resume_path=resume_path or self._apply.resume_path
            )
        elif resume_path is not None:
            self._apply.resume_path = resume_path

    @property
    def resume_path(self) -> str | None:
        return self._apply.resume_path

    def has_open_draft(self, external_id: str | None = None) -> bool:
        """True when a filled form is still open, waiting at the review step."""
        if not self._apply.is_open:
            return False
        return external_id is None or self._apply.job_external_id == external_id

    # --- Lifecycle --------------------------------------------------------

    async def start(self) -> SessionState:
        async with _guard("linkedin.start"):
            await self.browser.start()
            self._logged_in = await self.browser.is_logged_in()
            if self._logged_in:
                self._display_name = await self.browser.read_display_name()
        return await self.get_state()

    async def stop(self) -> None:
        async with _guard("linkedin.stop"):
            await self.browser.stop()
        self._logged_in = False

    async def get_state(self) -> SessionState:
        return SessionState(
            browser_open=self.browser.is_open,
            logged_in=self._logged_in,
            blocked=self.browser.blocked_reason is not None,
            blocked_reason=self.browser.blocked_reason,
            current_url=self.browser.current_url,
            display_name=self._display_name,
        )

    async def wait_for_login(self, timeout_seconds: int = 300) -> SessionState:
        async with _guard("linkedin.wait_for_login"):
            self._logged_in = await self.browser.wait_for_login(timeout_seconds)
            if self._logged_in:
                self._display_name = await self.browser.read_display_name()
        return await self.get_state()

    async def export_storage_state(self) -> dict:
        async with _guard("linkedin.export_state"):
            return await self.browser.export_storage_state()

    async def import_storage_state(self, state: dict) -> None:
        async with _guard("linkedin.import_state"):
            await self.browser.import_storage_state(state)

    # --- Read operations --------------------------------------------------

    async def search_jobs(self, filters: SearchFilters) -> list[JobPosting]:
        await self._require_login()
        async with _guard("linkedin.search_jobs"):
            await self.browser.raise_if_blocked()
            postings = await self._search.collect(filters)
            await self.browser.raise_if_blocked()
        return postings

    async def fetch_job_details(self, external_id: str) -> JobPosting:
        await self._require_login()
        async with _guard("linkedin.fetch_job_details"):
            await self.browser.raise_if_blocked()
            posting = await self._job.fetch(external_id)
            await self.browser.raise_if_blocked()
        return posting

    # --- Application flow -------------------------------------------------

    async def open_easy_apply(self, external_id: str) -> list[FormQuestion]:
        await self._require_login()
        async with _guard("linkedin.open_easy_apply"):
            await self.browser.raise_if_blocked()
            questions = await self._apply.open(external_id)
            await self.browser.raise_if_blocked()
        return questions

    async def fill_and_advance(
        self, answers: list[FormAnswer], *, cover_letter: str | None = None
    ) -> ApplicationDraft:
        async with _guard("linkedin.fill_and_advance"):
            draft = await self._apply.fill_and_advance(answers, cover_letter=cover_letter)
            await self.browser.raise_if_blocked()
        return draft

    async def submit(self) -> bool:
        """Send the application. Reachable only from `AutomationEngine.submit_application`."""
        async with _guard("linkedin.submit"):
            return await self._apply.submit()

    async def discard(self) -> None:
        async with _guard("linkedin.discard"):
            await self._apply.discard()

    async def capture_screenshot(self, name: str) -> str | None:
        try:
            return await self.browser.screenshot(name)
        except AutomationError:
            return None

    # --- Internals --------------------------------------------------------

    async def _require_login(self) -> None:
        if not self.browser.is_open:
            raise NotLoggedInError(
                "The browser session is closed. Start a session and sign in to LinkedIn."
            )
        if self._logged_in:
            return
        self._logged_in = await self.browser.is_logged_in()
        if not self._logged_in:
            raise NotLoggedInError(
                "Not signed in to LinkedIn. Sign in manually in the open browser window."
            )


@asynccontextmanager
async def _guard(action: str) -> AsyncIterator[None]:
    """Translate raw Playwright failures into the project's error hierarchy."""
    try:
        yield
    except AutomationError:
        raise
    except PlaywrightTimeoutError as exc:
        logger.warning(
            "LinkedIn action timed out.",
            extra={"action": action, "status": "timeout", "error": str(exc)},
        )
        raise UnexpectedPageError(f"{action} timed out: {exc}") from exc
    except PlaywrightError as exc:
        logger.warning(
            "LinkedIn action failed in the browser.",
            extra={"action": action, "status": "failed", "error": str(exc)},
        )
        raise UnexpectedPageError(f"{action} failed in the browser: {exc}") from exc
