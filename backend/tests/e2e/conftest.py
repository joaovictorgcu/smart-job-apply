"""Fixtures for the browser-level tests.

Two things differ from the rest of the suite and both are deliberate:

* `block_network` is overridden to a no-op. The parent conftest forbids
  constructing a real Playwright client, which is exactly right everywhere else
  and exactly wrong here. Requests are still fully contained: `portal.install`
  fulfils every linkedin.com request from Python and aborts everything else, so
  these tests remain offline.
* The throttle is zeroed. Its randomized delays are a production guard rail, not
  behaviour under test, and paying them per action would make the suite minutes
  long.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.automation.browser import BrowserSession
from app.automation.linkedin.service import LinkedInBrowserService
from app.automation.throttle import Throttle
from tests.e2e.portal import FakePortal, install

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def block_network() -> None:
    """Override the parent guard: these tests are allowed to launch Chromium.

    Containment comes from route interception instead — see the module docstring.
    """
    return None


@pytest.fixture
def portal() -> FakePortal:
    """A fresh fake portal per test, so recorded requests never bleed across."""
    return FakePortal()


@pytest.fixture
def fast_throttle() -> Throttle:
    """A throttle with every delay removed."""
    throttle = Throttle()
    throttle.action_delay = (0.0, 0.0)
    throttle.apply_delay = (0.0, 0.0)
    # 0,0 means "no window", so a test never fails because of the wall clock.
    throttle.working_hours = (0, 0)
    return throttle


@pytest.fixture
async def browser_session(fast_throttle: Throttle) -> AsyncIterator[BrowserSession]:
    """A real headless Chromium, torn down even if the test fails."""
    session = BrowserSession(user_id=1, headless=True)
    try:
        await session.start()
        yield session
    finally:
        await session.stop()


@pytest.fixture
async def service(
    browser_session: BrowserSession, portal: FakePortal, fast_throttle: Throttle
) -> AsyncIterator[LinkedInBrowserService]:
    """`LinkedInBrowserService` wired to the fake portal.

    Built around the already-started session rather than letting the service
    start its own, because the portal routes have to be installed on the context
    before any navigation happens.
    """
    await install(browser_session.context, portal)
    linkedin = LinkedInBrowserService(
        user_id=1, throttle=fast_throttle, browser=browser_session
    )
    yield linkedin


@pytest.fixture
async def logged_in_service(
    service: LinkedInBrowserService,
) -> AsyncIterator[LinkedInBrowserService]:
    """A service that has completed `start()` against a logged-in portal."""
    state = await service.start()
    assert state.logged_in, "the fake portal serves a logged-in feed by default"
    yield service
