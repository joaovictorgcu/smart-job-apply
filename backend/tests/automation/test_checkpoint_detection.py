"""Security-checkpoint detection.

Rule 3 of the project: a CAPTCHA or "unusual activity" page is never solved,
worked around, or retried. `BrowserSession.detect_checkpoint` is the sensor and
`raise_if_blocked` is the stop. Detection has to fire on the checkpoint URL, on a
challenge element, and on the page text in every language the app is used in — and
it must not fire on an ordinary job posting.

The real detector runs here against a `FakePage`: no browser is launched, only the
handful of page methods the detector actually calls are provided.
"""

from __future__ import annotations

import pytest

from app.automation import selectors as sel
from app.automation.browser import BrowserSession
from app.automation.errors import AutomationError, SecurityCheckpointError, UnexpectedPageError
from tests.fixtures.fake_linkedin import CHECKPOINT_MARKERS, CHECKPOINT_URL, FakePage

SAFE_URLS = (
    "https://www.linkedin.com/feed/",
    "https://www.linkedin.com/jobs/search/?keywords=python",
    "https://www.linkedin.com/jobs/view/4012345678/",
)


def session_with(page: FakePage) -> BrowserSession:
    """A `BrowserSession` whose page is the fake — nothing is launched."""
    browser = BrowserSession(user_id=1, headless=True)
    browser._page = page  # type: ignore[assignment]
    return browser


class TestErrorContract:
    def test_carries_a_reason(self) -> None:
        error = SecurityCheckpointError("Security verification detected.")
        assert error.reason == "Security verification detected."
        assert str(error) == "Security verification detected."

    def test_has_a_default_reason(self) -> None:
        assert SecurityCheckpointError().reason

    def test_is_never_treated_as_recoverable(self) -> None:
        # `recoverable` is what a retry loop reads; a checkpoint must never retry.
        assert SecurityCheckpointError().recoverable is False
        assert isinstance(SecurityCheckpointError(), AutomationError)

    def test_is_not_confused_with_a_plain_unexpected_page(self) -> None:
        assert not issubclass(SecurityCheckpointError, UnexpectedPageError)
        assert UnexpectedPageError("changed markup").recoverable is True


class TestUrlDetection:
    @pytest.mark.parametrize("fragment", sel.Checkpoint.URL_FRAGMENTS)
    async def test_every_declared_url_fragment_is_detected(self, fragment: str) -> None:
        browser = session_with(FakePage(url=f"https://www.linkedin.com/x{fragment}y"))

        assert await browser.detect_checkpoint() is not None

    async def test_the_real_challenge_url_is_detected(self) -> None:
        browser = session_with(FakePage(url=CHECKPOINT_URL))

        reason = await browser.detect_checkpoint()

        assert reason is not None
        assert "checkpoint" in reason.lower()

    async def test_detection_is_case_insensitive_on_the_url(self) -> None:
        browser = session_with(
            FakePage(url="https://www.linkedin.com/CHECKPOINT/Challenge/AgH9x")
        )

        assert await browser.detect_checkpoint() is not None


class TestTextDetection:
    @pytest.mark.parametrize("marker", sel.Checkpoint.TEXT_MARKERS)
    async def test_every_declared_text_marker_is_detected(self, marker: str) -> None:
        browser = session_with(
            FakePage(url="https://www.linkedin.com/feed/", body_text=f"Hello. {marker}. Bye.")
        )

        assert await browser.detect_checkpoint() is not None

    @pytest.mark.parametrize("marker", CHECKPOINT_MARKERS)
    async def test_the_multilingual_markers_are_detected_as_written_on_screen(
        self, marker: str
    ) -> None:
        """As LinkedIn renders them: title-cased, accented, and mixed case."""
        browser = session_with(
            FakePage(url="https://www.linkedin.com/feed/", body_text=marker)
        )

        assert await browser.detect_checkpoint() is not None

    async def test_detection_is_case_insensitive_on_the_text(self) -> None:
        browser = session_with(
            FakePage(url="https://www.linkedin.com/feed/", body_text="SECURITY VERIFICATION")
        )

        assert await browser.detect_checkpoint() is not None

    async def test_the_reason_quotes_the_marker_it_matched(self) -> None:
        browser = session_with(
            FakePage(url="https://www.linkedin.com/feed/", body_text="Unusual activity detected")
        )

        reason = await browser.detect_checkpoint()

        assert reason is not None
        assert "unusual activity" in reason.lower()


class TestElementDetection:
    @pytest.mark.parametrize("selector", sel.Checkpoint.ELEMENTS)
    async def test_every_declared_challenge_element_is_detected(self, selector: str) -> None:
        browser = session_with(
            FakePage(url="https://www.linkedin.com/feed/", elements=(selector,))
        )

        reason = await browser.detect_checkpoint()

        assert reason is not None
        assert selector in reason


class TestNoFalsePositives:
    @pytest.mark.parametrize("url", SAFE_URLS)
    async def test_an_ordinary_page_is_not_a_checkpoint(self, url: str) -> None:
        browser = session_with(FakePage(url=url, body_text="Python jobs in Remote"))

        assert await browser.detect_checkpoint() is None

    async def test_a_security_engineering_posting_is_not_a_checkpoint(self) -> None:
        """A job about security is not a security challenge."""
        browser = session_with(
            FakePage(
                url="https://www.linkedin.com/jobs/view/4012345678/",
                body_text=(
                    "Security Engineer. You will own our application security program "
                    "and run verification of our controls."
                ),
            )
        )

        assert await browser.detect_checkpoint() is None

    async def test_a_closed_page_reports_nothing_instead_of_crashing(self) -> None:
        browser = session_with(FakePage(url=CHECKPOINT_URL, closed=True))

        assert await browser.detect_checkpoint() is None


class TestRaiseIfBlocked:
    async def test_raises_and_records_the_reason(self) -> None:
        browser = session_with(FakePage.checkpoint())

        with pytest.raises(SecurityCheckpointError) as caught:
            await browser.raise_if_blocked()

        assert caught.value.reason
        assert browser.blocked_reason == caught.value.reason

    async def test_stays_silent_on_a_normal_page(self) -> None:
        browser = session_with(FakePage())

        await browser.raise_if_blocked()

        assert browser.blocked_reason is None

    async def test_never_offers_a_way_past_the_challenge(self) -> None:
        """Guards the intent: the session exposes no solve/bypass/click-through path."""
        forbidden = {"solve_captcha", "bypass_checkpoint", "answer_challenge", "skip_checkpoint"}

        assert forbidden.isdisjoint(dir(BrowserSession))
