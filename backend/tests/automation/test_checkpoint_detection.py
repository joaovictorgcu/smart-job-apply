"""Security-checkpoint detection.

Rule 3 of the project: a CAPTCHA or "unusual activity" page is never solved,
worked around, or retried. It raises `SecurityCheckpointError` and everything
stops. Detection has to fire on the checkpoint URL and on the page text in every
language the app is used in.

Expected surface, resolved leniently:

    app/automation/linkedin/checkpoints.py:
        async def detect_checkpoint(page) -> str | None   # reason, or None
        # or: async def assert_no_checkpoint(page) -> None  # raises instead
"""

from __future__ import annotations

import pytest

from app.automation.errors import AutomationError, SecurityCheckpointError, UnexpectedPageError
from tests import call_maybe_async, find_attr, missing
from tests.fixtures.fake_linkedin import CHECKPOINT_MARKERS, CHECKPOINT_URL, FakePage

CHECKPOINT_MODULES = (
    "app.automation.linkedin.checkpoints",
    "app.automation.linkedin.checkpoint",
    "app.automation.linkedin.guards",
    "app.automation.linkedin.session",
    "app.automation.linkedin",
    "app.automation.checkpoint",
    "app.automation.checkpoints",
)

DETECTOR_NAMES = (
    "detect_checkpoint",
    "detect_security_checkpoint",
    "find_checkpoint",
    "checkpoint_reason",
    "is_security_checkpoint",
    "assert_no_checkpoint",
    "raise_if_checkpoint",
    "ensure_no_checkpoint",
)

detector = find_attr(DETECTOR_NAMES, *CHECKPOINT_MODULES)

# URL fragments LinkedIn uses for its verification flows.
CHECKPOINT_URLS = (
    CHECKPOINT_URL,
    "https://www.linkedin.com/checkpoint/lg/login-submit",
    "https://www.linkedin.com/checkpoint/challengesV2/AgFabc123",
)

SAFE_URLS = (
    "https://www.linkedin.com/feed/",
    "https://www.linkedin.com/jobs/search/?keywords=python",
    "https://www.linkedin.com/jobs/view/4012345678/",
)


async def is_detected(page: FakePage) -> bool:
    """True when the detector flags the page, whichever style it uses."""
    try:
        result = await call_maybe_async(detector, page)
    except SecurityCheckpointError:
        return True
    return bool(result)


class TestErrorContract:
    """Holds regardless of who implements the detector."""

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


class TestFakePage:
    async def test_exposes_the_url_and_content_the_detector_needs(self) -> None:
        page = FakePage()
        assert page.url.startswith("https://www.linkedin.com/")
        assert "Python jobs" in await page.content()

    async def test_the_checkpoint_variant_carries_url_and_marker(self) -> None:
        page = FakePage.checkpoint()
        assert "/checkpoint/" in page.url
        assert CHECKPOINT_MARKERS[0] in await page.content()


@pytest.mark.xfail(detector is None, reason=missing("detect_checkpoint", *CHECKPOINT_MODULES))
class TestDetection:
    @pytest.mark.parametrize("url", CHECKPOINT_URLS)
    async def test_detects_the_checkpoint_url(self, url: str) -> None:
        page = FakePage(url=url, html="<html><body>Please wait</body></html>")
        assert await is_detected(page) is True

    @pytest.mark.parametrize("marker", CHECKPOINT_MARKERS)
    async def test_detects_the_text_marker_in_every_supported_language(self, marker: str) -> None:
        page = FakePage(
            url="https://www.linkedin.com/jobs/search/",
            html=f"<html><body><h1>{marker}</h1></body></html>",
        )
        assert await is_detected(page) is True

    async def test_detection_is_case_insensitive(self) -> None:
        page = FakePage(
            url="https://www.linkedin.com/jobs/search/",
            html="<html><body><h1>SECURITY VERIFICATION</h1></body></html>",
        )
        assert await is_detected(page) is True

    async def test_detects_a_captcha_challenge_frame(self) -> None:
        page = FakePage(
            url="https://www.linkedin.com/jobs/search/",
            html='<html><body><div id="captcha-internal">verify</div></body></html>',
        )
        assert await is_detected(page) is True

    @pytest.mark.parametrize("url", SAFE_URLS)
    async def test_does_not_fire_on_a_normal_page(self, url: str) -> None:
        page = FakePage(url=url, html="<html><body><h1>Python jobs</h1></body></html>")
        assert await is_detected(page) is False

    async def test_does_not_fire_on_a_job_that_merely_mentions_security(self) -> None:
        """A security engineering posting is not a security checkpoint."""
        page = FakePage(
            url="https://www.linkedin.com/jobs/view/4012345678/",
            html=(
                "<html><body><h1>Security Engineer</h1>"
                "<p>You will own our application security program.</p></body></html>"
            ),
        )
        assert await is_detected(page) is False

    async def test_reports_a_reason_when_it_returns_one(self) -> None:
        page = FakePage.checkpoint()
        try:
            result = await call_maybe_async(detector, page)
        except SecurityCheckpointError as error:
            assert error.reason
            return
        # A predicate style detector may answer True; a reason style answers text.
        assert result is True or (isinstance(result, str) and result)
