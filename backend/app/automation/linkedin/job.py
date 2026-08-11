"""Single job page: open one posting and extract everything the AI needs."""

from __future__ import annotations

import re

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.automation import selectors as sel
from app.automation.browser import BrowserSession
from app.automation.contracts import JobPosting
from app.automation.errors import ElementNotFoundError, UnexpectedPageError
from app.automation.linkedin.search import clean_text, workplace_type_from_text
from app.automation.throttle import Throttle
from app.observability import get_logger

logger = get_logger(__name__)

_MAX_DESCRIPTION_CHARS = 20_000


class JobDetailPage:
    """Page object for `https://www.linkedin.com/jobs/view/<id>/`."""

    def __init__(self, browser: BrowserSession, throttle: Throttle | None = None) -> None:
        self._browser = browser
        self._throttle = throttle or Throttle()

    async def open(self, external_id: str) -> None:
        url = sel.Urls.JOB_VIEW.format(external_id=external_id)
        await self._browser.goto(url)
        await self._throttle.wait_action()
        try:
            await self._browser.find_first(sel.JobDetail.TITLE, name="job title", timeout=8_000)
        except ElementNotFoundError as exc:
            raise UnexpectedPageError(
                f"Job {external_id} did not render a job page (removed or unavailable).",
                url=self._browser.current_url,
            ) from exc

    async def fetch(self, external_id: str) -> JobPosting:
        """Open the posting and return it fully populated."""
        await self.open(external_id)
        return await self.extract(external_id)

    async def extract(self, external_id: str) -> JobPosting:
        title = clean_text(await self._text(sel.JobDetail.TITLE))
        company = clean_text(await self._text(sel.JobDetail.COMPANY))
        location_blob = clean_text(await self._text(sel.JobDetail.LOCATION))
        description = await self._read_description()
        pills = clean_text(await self._text(sel.JobDetail.WORKPLACE_PILLS))

        easy_apply = await self._has_easy_apply()
        already_applied = await self._browser.any_visible(
            sel.JobDetail.APPLIED_BANNER, timeout=1_500
        )
        workplace = workplace_type_from_text(
            f"{pills} {location_blob}".lower()
        ) or workplace_type_from_text(description[:2_000].lower())

        posting = JobPosting(
            external_id=external_id,
            title=title or f"Job {external_id}",
            company=company or "Unknown",
            location=_first_segment(location_blob),
            url=sel.Urls.JOB_VIEW.format(external_id=external_id),
            description=description or None,
            workplace_type=workplace,
            easy_apply=easy_apply,
            already_applied=already_applied,
        )
        logger.info(
            "Job details extracted.",
            extra={
                "action": "job.extract",
                "status": "ok",
                "external_id": external_id,
                "easy_apply": easy_apply,
                "already_applied": already_applied,
                "description_chars": len(description),
            },
        )
        return posting

    async def has_easy_apply(self, external_id: str) -> bool:
        await self.open(external_id)
        return await self._has_easy_apply()

    async def _has_easy_apply(self) -> bool:
        button = await self._browser.find_first_or_none(
            sel.JobDetail.EASY_APPLY_BUTTON, timeout=3_000
        )
        if button is None:
            return False
        # The generic `.jobs-apply-button` also matches external "Apply" buttons,
        # which open the company's site instead of the Easy Apply modal.
        try:
            label = (await button.get_attribute("aria-label")) or await button.inner_text()
        except (PlaywrightError, PlaywrightTimeoutError):
            return False
        normalized = (label or "").strip().lower()
        return "easy apply" in normalized or "candidatura simplificada" in normalized

    async def _read_description(self) -> str:
        """Expand the collapsed description, then read it as plain text."""
        expand = await self._browser.find_first_or_none(
            sel.JobDetail.SHOW_MORE_DESCRIPTION, timeout=2_000
        )
        if expand is not None:
            try:
                await expand.click(timeout=3_000)
                await self._throttle.wait_action()
            except (PlaywrightError, PlaywrightTimeoutError):
                pass  # a collapsed description is still readable, just shorter

        text = await self._text(sel.JobDetail.DESCRIPTION)
        normalized = re.sub(r"\n{3,}", "\n\n", text).strip()
        return normalized[:_MAX_DESCRIPTION_CHARS]

    async def _text(self, selectors: tuple[str, ...]) -> str:
        for selector in selectors:
            try:
                locator = self._browser.page.locator(selector).first
                if await locator.count():
                    value = await locator.inner_text(timeout=3_000)
                    if value.strip():
                        return value
            except (PlaywrightError, PlaywrightTimeoutError):
                continue
        return ""


def _first_segment(blob: str) -> str | None:
    """LinkedIn packs "City, State · 2 days ago · 30 applicants" into one node."""
    if not blob:
        return None
    segment = blob.split("·")[0].strip()
    return segment or None
