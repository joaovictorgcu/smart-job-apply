"""Job-search results page.

Turns a `SearchFilters` into a LinkedIn search URL, scrolls the result list
politely, and returns plain `JobPosting` objects. Nothing here leaks a Playwright
handle to the caller.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.automation import selectors as sel
from app.automation.browser import BrowserSession
from app.automation.contracts import JobPosting, SearchFilters
from app.automation.throttle import Throttle
from app.observability import get_logger

logger = get_logger(__name__)

# LinkedIn's `f_WT` (workplace type) facet.
REMOTE_FILTER_PARAM: dict[str, str] = {
    "onsite": "1",  # f_WT=1 -> On-site
    "on-site": "1",
    "remote": "2",  # f_WT=2 -> Remote
    "hybrid": "3",  # f_WT=3 -> Hybrid
}

# LinkedIn's `f_TPR` (time posted range) facet, expressed in seconds.
DATE_POSTED_PARAM: dict[str, str] = {
    "day": "r86400",  # last 24 hours
    "24h": "r86400",
    "week": "r604800",  # last 7 days
    "month": "r2592000",  # last 30 days
}

# LinkedIn's `f_E` (experience level) facet.
EXPERIENCE_LEVEL_PARAM: dict[str, str] = {
    "internship": "1",
    "entry": "2",
    "entry_level": "2",
    "associate": "3",
    "mid_senior": "4",
    "mid-senior": "4",
    "senior": "4",
    "director": "5",
    "executive": "6",
}

# Results per page in LinkedIn's paginated job search; `start` moves in this step.
PAGE_SIZE = 25
_MAX_SCROLL_ROUNDS = 30
_JOB_ID_IN_URL = re.compile(r"/jobs/view/(\d+)")
_DIGITS = re.compile(r"(\d{6,})")


class JobSearchPage:
    """Page object for `https://www.linkedin.com/jobs/search/`."""

    def __init__(self, browser: BrowserSession, throttle: Throttle | None = None) -> None:
        self._browser = browser
        self._throttle = throttle or Throttle()

    # --- URL building -----------------------------------------------------

    @staticmethod
    def build_url(filters: SearchFilters, *, start: int = 0) -> str:
        params: dict[str, str] = {"keywords": filters.keywords}

        if filters.location:
            params["location"] = filters.location

        if filters.remote_filter:
            mapped = REMOTE_FILTER_PARAM.get(filters.remote_filter.strip().lower())
            if mapped:
                params["f_WT"] = mapped

        if filters.date_posted:
            mapped = DATE_POSTED_PARAM.get(filters.date_posted.strip().lower())
            if mapped:
                params["f_TPR"] = mapped

        levels = [
            EXPERIENCE_LEVEL_PARAM[level.strip().lower()]
            for level in filters.experience_levels
            if level.strip().lower() in EXPERIENCE_LEVEL_PARAM
        ]
        if levels:
            # Multi-select facets are comma separated: f_E=2,3,4
            params["f_E"] = ",".join(dict.fromkeys(levels))

        if filters.easy_apply_only:
            # f_AL=true restricts results to Easy Apply postings.
            params["f_AL"] = "true"

        # Most recent first, so a repeated run surfaces new postings at the top.
        params["sortBy"] = "DD"

        if start:
            params["start"] = str(start)

        return f"{sel.Urls.JOB_SEARCH}?{urlencode(params)}"

    # --- Collection -------------------------------------------------------

    async def collect(self, filters: SearchFilters) -> list[JobPosting]:
        """Walk the result pages until `max_results` postings are collected."""
        wanted = max(1, filters.max_results)
        postings: list[JobPosting] = []
        seen: set[str] = set()
        start = 0

        while len(postings) < wanted and start < wanted + PAGE_SIZE:
            url = self.build_url(filters, start=start)
            await self._browser.goto(url)
            await self._throttle.wait_action()

            if await self._browser.any_visible(sel.Search.NO_RESULTS, timeout=2_000):
                logger.info(
                    "Search returned no results.",
                    extra={"action": "search.collect", "status": "empty", "page": start // PAGE_SIZE},
                )
                break

            await self._scroll_result_list()
            cards = await self._cards()
            if not cards:
                break

            page_new = 0
            for card in cards:
                if len(postings) >= wanted:
                    break
                posting = await self._read_card(card)
                if posting is None or posting.external_id in seen:
                    continue
                seen.add(posting.external_id)
                page_new += 1
                if posting.already_applied:
                    logger.info(
                        "Skipping a job already marked as applied.",
                        extra={
                            "action": "search.collect",
                            "status": "skipped",
                            "external_id": posting.external_id,
                        },
                    )
                    continue
                if filters.easy_apply_only and not posting.easy_apply:
                    # The f_AL facet is not always honoured for every card variant.
                    continue
                postings.append(posting)

            if page_new == 0:
                break
            start += PAGE_SIZE
            await self._throttle.wait_action()

        logger.info(
            "Search finished.",
            extra={"action": "search.collect", "status": "ok", "found": len(postings)},
        )
        return postings

    async def _cards(self) -> list[Locator]:
        for selector in sel.Search.JOB_CARD:
            try:
                locator = self._browser.page.locator(selector)
                if await locator.count():
                    return await locator.all()
            except PlaywrightError:
                continue
        return []

    async def _scroll_result_list(self) -> None:
        """Lazy-loaded list: scroll in small increments until the count settles."""
        page = self._browser.page
        container = await self._browser.find_first_or_none(
            sel.Search.RESULTS_CONTAINER, timeout=3_000
        )
        previous = -1
        for _ in range(_MAX_SCROLL_ROUNDS):
            cards = await self._cards()
            if len(cards) == previous:
                break
            previous = len(cards)
            try:
                if container is not None:
                    await container.evaluate(
                        "node => node.scrollBy(0, Math.floor(node.clientHeight * 0.8))"
                    )
                else:
                    await page.mouse.wheel(0, 600)
            except PlaywrightError:
                break
            await self._throttle.human_pause(page)

    async def _read_card(self, card: Locator) -> JobPosting | None:
        external_id = await self._card_external_id(card)
        if not external_id:
            return None

        title = await self._text_in(card, sel.Search.CARD_TITLE)
        company = await self._text_in(card, sel.Search.CARD_COMPANY)
        location = await self._text_in(card, sel.Search.CARD_LOCATION)
        if not title:
            return None

        card_text = (await self._safe_inner_text(card)).lower()
        already_applied = await self._has_in(card, sel.Search.CARD_APPLIED_MARKER)
        easy_apply = await self._has_in(card, sel.Search.CARD_EASY_APPLY_MARKER) or (
            "easy apply" in card_text or "candidatura simplificada" in card_text
        )

        return JobPosting(
            external_id=external_id,
            title=clean_text(title),
            company=clean_text(company) or "Unknown",
            location=clean_text(location) or None,
            url=sel.Urls.JOB_VIEW.format(external_id=external_id),
            workplace_type=workplace_type_from_text(card_text),
            easy_apply=easy_apply,
            already_applied=already_applied,
        )

    async def _card_external_id(self, card: Locator) -> str | None:
        for attribute in sel.Search.CARD_ID_ATTRIBUTES:
            try:
                value = await card.get_attribute(attribute)
            except PlaywrightError:
                value = None
            if value and value.isdigit():
                return value

        # Fall back to the job link, then to any long digit run in the markup.
        for selector in sel.Search.CARD_LINK:
            try:
                href = await card.locator(selector).first.get_attribute("href")
            except (PlaywrightError, PlaywrightTimeoutError):
                href = None
            if href:
                match = _JOB_ID_IN_URL.search(href)
                if match:
                    return match.group(1)

        try:
            nested = await card.locator("[data-job-id]").first.get_attribute("data-job-id")
        except (PlaywrightError, PlaywrightTimeoutError):
            nested = None
        if nested and nested.isdigit():
            return nested

        try:
            html = await card.inner_html()
        except PlaywrightError:
            return None
        match = _DIGITS.search(html)
        return match.group(1) if match else None

    @staticmethod
    async def _safe_inner_text(locator: Locator) -> str:
        try:
            return await locator.inner_text(timeout=2_000)
        except (PlaywrightError, PlaywrightTimeoutError):
            return ""

    async def _text_in(self, root: Locator, selectors: tuple[str, ...]) -> str:
        for selector in selectors:
            try:
                target = root.locator(selector).first
                if await target.count():
                    text = await target.inner_text(timeout=1_500)
                    if text.strip():
                        return text
            except (PlaywrightError, PlaywrightTimeoutError):
                continue
        return ""

    @staticmethod
    async def _has_in(root: Locator, selectors: tuple[str, ...]) -> bool:
        for selector in selectors:
            try:
                if await root.locator(selector).count():
                    return True
            except PlaywrightError:
                continue
        return False


def clean_text(value: str | Any) -> str:
    """Collapse whitespace and drop LinkedIn's duplicated accessibility text."""
    if not isinstance(value, str):
        return ""
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    # LinkedIn renders the visible text twice (visually hidden + aria-hidden).
    if len(lines) >= 2 and lines[0] == lines[1]:
        lines = lines[1:]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def workplace_type_from_text(text: str) -> str | None:
    for value in sel.Search.REMOTE_TEXTS:
        if value in text:
            return "remote"
    for value in sel.Search.HYBRID_TEXTS:
        if value in text:
            return "hybrid"
    for value in sel.Search.ONSITE_TEXTS:
        if value in text:
            return "onsite"
    return None
