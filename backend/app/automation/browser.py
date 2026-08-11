"""Playwright lifecycle owner.

`BrowserSession` is the only object in the project that holds a Playwright
handle. It runs a *persistent* context under one directory per user, so a manual
login (including 2FA) survives an application restart, and it funnels every
navigation through checkpoint detection: if LinkedIn shows a CAPTCHA or a
security-verification page, we stop instead of trying to get past it.

The browser is visible by default (`headless=False`) because the human must be
able to log in and watch what happens.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.async_api import (
    BrowserContext,
    Locator,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from app.automation import selectors as sel
from app.automation.errors import (
    BrowserNotReadyError,
    ElementNotFoundError,
    SecurityCheckpointError,
)
from app.config import get_settings
from app.observability import get_logger

logger = get_logger(__name__)

# A current, ordinary desktop Chrome fingerprint. Playwright's default UA
# advertises HeadlessChrome, which is an immediate giveaway.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
DEFAULT_VIEWPORT = {"width": 1440, "height": 900}
# English UI keeps the selectors in `selectors.py` on their primary variants;
# Portuguese fallbacks are there for accounts whose LinkedIn language is pt-BR.
DEFAULT_LOCALE = "en-US"
DEFAULT_TIMEZONE = "America/Sao_Paulo"

DEFAULT_TIMEOUT_MS = 20_000
_CHECKPOINT_PROBE_TIMEOUT_MS = 1_500

_LAUNCH_ARGS = (
    # Removes the `navigator.webdriver` flag Chromium sets for automated runs.
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-default-browser-check",
    "--no-first-run",
    "--disable-features=Translate,MediaRouter",
    "--start-maximized",
)

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


class BrowserSession:
    """Owns one persistent browser context for one user."""

    def __init__(
        self,
        user_id: int,
        *,
        headless: bool | None = None,
        locale: str = DEFAULT_LOCALE,
        timezone_id: str = DEFAULT_TIMEZONE,
        user_agent: str = DEFAULT_USER_AGENT,
        viewport: dict[str, int] | None = None,
    ) -> None:
        settings = get_settings()
        self.user_id = user_id
        self.headless = settings.headless if headless is None else headless
        self.locale = locale
        self.timezone_id = timezone_id
        self.user_agent = user_agent
        self.viewport = dict(viewport or DEFAULT_VIEWPORT)
        self.profile_dir: Path = settings.browser_profiles_dir / f"user_{user_id}"

        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._blocked_reason: str | None = None

    # --- Lifecycle --------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._context is not None and self._page is not None and not self._page.is_closed()

    @property
    def blocked_reason(self) -> str | None:
        return self._blocked_reason

    @property
    def page(self) -> Page:
        if self._page is None or self._page.is_closed():
            raise BrowserNotReadyError("The browser is not open. Start a session first.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise BrowserNotReadyError("The browser is not open. Start a session first.")
        return self._context

    async def start(self) -> None:
        """Launch the persistent context, reusing the user's browser profile."""
        if self.is_open:
            return

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                str(self.profile_dir),
                headless=self.headless,
                args=list(_LAUNCH_ARGS),
                user_agent=self.user_agent,
                viewport=self.viewport,
                locale=self.locale,
                timezone_id=self.timezone_id,
                accept_downloads=True,
                ignore_default_args=["--enable-automation"],
            )
        except PlaywrightError as exc:
            await self._teardown()
            raise BrowserNotReadyError(
                f"Could not launch the browser: {exc}. "
                "Run `playwright install chromium` if the browser is missing."
            ) from exc

        self._context.set_default_timeout(DEFAULT_TIMEOUT_MS)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        self._blocked_reason = None
        logger.info(
            "Browser session started.",
            extra={
                "action": "browser.start",
                "status": "ok",
                "user_id": self.user_id,
                "headless": self.headless,
            },
        )

    async def stop(self) -> None:
        """Close the browser. Cookies live on disk in the persistent profile."""
        await self._teardown()
        logger.info(
            "Browser session stopped.",
            extra={"action": "browser.stop", "status": "ok", "user_id": self.user_id},
        )

    async def _teardown(self) -> None:
        for closer in (
            getattr(self._context, "close", None),
            getattr(self._playwright, "stop", None),
        ):
            if closer is None:
                continue
            try:
                await closer()
            except Exception as exc:  # a dead browser must not block shutdown
                logger.debug(
                    "Ignored error while closing the browser.",
                    extra={"action": "browser.teardown", "error": str(exc)},
                )
        self._page = None
        self._context = None
        self._playwright = None

    # --- Navigation -------------------------------------------------------

    @property
    def current_url(self) -> str | None:
        if self._page is None or self._page.is_closed():
            return None
        try:
            return self._page.url
        except PlaywrightError:
            return None

    async def goto(self, url: str, **kwargs: Any) -> None:
        """Navigate and immediately verify we did not land on a challenge page."""
        page = self.page
        kwargs.setdefault("wait_until", "domcontentloaded")
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT_MS)
        try:
            await page.goto(url, **kwargs)
        except PlaywrightTimeoutError as exc:
            # A slow feed is common; only treat it as fatal if the page is unusable.
            logger.warning(
                "Navigation timed out.",
                extra={"action": "browser.goto", "status": "timeout", "url": url},
            )
            if self.current_url in (None, "about:blank"):
                raise BrowserNotReadyError(f"Could not load {url}: {exc}") from exc
        await self.raise_if_blocked()

    # --- Checkpoint detection --------------------------------------------

    async def detect_checkpoint(self) -> str | None:
        """Return a human-readable reason when a security challenge is on screen."""
        if self._page is None or self._page.is_closed():
            return None

        url = (self.current_url or "").lower()
        for fragment in sel.Checkpoint.URL_FRAGMENTS:
            if fragment in url:
                return f"LinkedIn redirected to a security checkpoint ({fragment})."

        for selector in sel.Checkpoint.ELEMENTS:
            try:
                if await self._page.locator(selector).count():
                    return f"A security challenge element is present ({selector})."
            except PlaywrightError:
                continue

        try:
            body = await self._page.locator("body").inner_text(
                timeout=_CHECKPOINT_PROBE_TIMEOUT_MS
            )
        except (PlaywrightError, PlaywrightTimeoutError):
            return None

        haystack = body.lower()
        for marker in sel.Checkpoint.TEXT_MARKERS:
            if marker in haystack:
                return f'The page shows a security verification message ("{marker}").'
        return None

    async def raise_if_blocked(self) -> None:
        """Stop everything when a challenge is detected. Never bypass it."""
        reason = await self.detect_checkpoint()
        if reason is None:
            return
        self._blocked_reason = reason
        logger.error(
            "Security checkpoint detected; stopping.",
            extra={
                "action": "browser.checkpoint",
                "status": "blocked",
                "user_id": self.user_id,
                "url": self.current_url,
            },
        )
        raise SecurityCheckpointError(reason)

    # --- Authentication ---------------------------------------------------

    async def is_logged_in(self) -> bool:
        """Navigate to the feed and check for a logged-in marker."""
        await self.goto(sel.Urls.FEED)
        url = (self.current_url or "").lower()
        if any(fragment in url for fragment in sel.Urls.LOGGED_OUT_FRAGMENTS):
            return False
        for selector in sel.Auth.LOGGED_IN_MARKERS:
            try:
                await self.page.locator(selector).first.wait_for(state="attached", timeout=3_000)
                return True
            except (PlaywrightError, PlaywrightTimeoutError):
                continue
        return False

    async def wait_for_login(self, timeout_seconds: int = 300) -> bool:
        """Poll until the user finishes logging in manually in the open window.

        A challenge shown here is *not* raised: the human is at the keyboard in a
        visible browser and completes their own verification. We only report it.
        """
        deadline = asyncio.get_running_loop().time() + max(5, timeout_seconds)
        await self.goto(sel.Urls.LOGIN)
        while asyncio.get_running_loop().time() < deadline:
            url = (self.current_url or "").lower()
            if not any(fragment in url for fragment in sel.Urls.LOGGED_OUT_FRAGMENTS):
                for selector in sel.Auth.LOGGED_IN_MARKERS:
                    try:
                        await self.page.locator(selector).first.wait_for(
                            state="attached", timeout=2_000
                        )
                        logger.info(
                            "Manual login completed.",
                            extra={
                                "action": "browser.wait_for_login",
                                "status": "ok",
                                "user_id": self.user_id,
                            },
                        )
                        return True
                    except (PlaywrightError, PlaywrightTimeoutError):
                        continue
            reason = await self.detect_checkpoint()
            if reason:
                logger.warning(
                    "Waiting for the user to complete LinkedIn's own verification.",
                    extra={
                        "action": "browser.wait_for_login",
                        "status": "verification",
                        "user_id": self.user_id,
                    },
                )
            await asyncio.sleep(3)
        return False

    async def read_display_name(self) -> str | None:
        """Best-effort LinkedIn display name, for labelling the connection."""
        for selector in sel.Auth.DISPLAY_NAME:
            try:
                locator = self.page.locator(selector).first
                await locator.wait_for(state="attached", timeout=2_000)
                text = (await locator.get_attribute("alt")) or (await locator.inner_text())
                cleaned = (text or "").strip()
                if cleaned:
                    return cleaned[:200]
            except (PlaywrightError, PlaywrightTimeoutError):
                continue
        return None

    # --- Session state ----------------------------------------------------

    async def export_storage_state(self) -> dict[str, Any]:
        """Cookies + localStorage, for the caller to encrypt and persist."""
        try:
            return await self.context.storage_state()
        except PlaywrightError as exc:
            raise BrowserNotReadyError(f"Could not export the session state: {exc}") from exc

    async def import_storage_state(self, state: dict[str, Any]) -> None:
        """Restore previously saved cookies into the live persistent context.

        A persistent context cannot be launched with `storage_state`, so cookies
        are injected after launch. Malformed entries are skipped rather than
        aborting the session restore.
        """
        cookies = [cookie for cookie in state.get("cookies") or [] if cookie.get("name")]
        if not cookies:
            return
        try:
            await self.context.add_cookies(cookies)
        except PlaywrightError as exc:
            logger.warning(
                "Could not restore saved cookies; a manual login may be required.",
                extra={
                    "action": "browser.import_storage_state",
                    "status": "failed",
                    "user_id": self.user_id,
                    "error": str(exc),
                },
            )

    # --- Utilities --------------------------------------------------------

    async def screenshot(self, name: str) -> str | None:
        """Capture the viewport under `data_dir/screenshots`; None on failure."""
        if self._page is None or self._page.is_closed():
            return None
        directory = get_settings().data_dir / "screenshots"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        safe = _UNSAFE_NAME.sub("-", name).strip("-") or "capture"
        path = directory / f"user{self.user_id}_{safe}_{stamp}.png"
        try:
            await self._page.screenshot(path=str(path))
        except (PlaywrightError, PlaywrightTimeoutError, OSError) as exc:
            logger.warning(
                "Could not capture a screenshot.",
                extra={"action": "browser.screenshot", "status": "failed", "error": str(exc)},
            )
            return None
        return str(path)

    async def find_first(
        self,
        selectors: tuple[str, ...],
        *,
        name: str = "element",
        timeout: int = 5_000,
        state: str = "visible",
        root: Locator | None = None,
    ) -> Locator:
        """Try each fallback selector in order; raise when none resolves."""
        scope: Any = root if root is not None else self.page
        per_try = max(500, timeout // max(1, len(selectors)))
        for selector in selectors:
            try:
                locator = scope.locator(selector).first
                await locator.wait_for(state=state, timeout=per_try)
                return locator
            except (PlaywrightError, PlaywrightTimeoutError):
                continue
        raise ElementNotFoundError(
            f'Could not find "{name}" with any known selector — '
            "LinkedIn's markup probably changed (see automation/selectors.py).",
            url=self.current_url,
        )

    async def find_first_or_none(
        self,
        selectors: tuple[str, ...],
        *,
        timeout: int = 2_000,
        state: str = "visible",
        root: Locator | None = None,
    ) -> Locator | None:
        """`find_first` for optional elements."""
        try:
            return await self.find_first(
                selectors, timeout=timeout, state=state, root=root, name="optional"
            )
        except ElementNotFoundError:
            return None

    async def any_visible(
        self, selectors: tuple[str, ...], *, root: Locator | None = None, timeout: int = 1_500
    ) -> bool:
        return await self.find_first_or_none(selectors, root=root, timeout=timeout) is not None
