"""Automation layer: the browser-agnostic boundary and its error types.

Layering is `AutomationEngine -> LinkedInBrowserService -> Playwright`. Business
logic imports from here and never touches Playwright, and every selector lives in
`app.automation.selectors`.
"""

from app.automation.browser import BrowserSession
from app.automation.contracts import (
    ApplicationDraft,
    FormAnswer,
    FormQuestion,
    JobPosting,
    LinkedInService,
    ProfileContext,
    QuestionKind,
    SearchFilters,
    SessionState,
)
from app.automation.engine import AutomationEngine, get_engine
from app.automation.errors import (
    AlreadyAppliedError,
    AutomationError,
    BrowserNotReadyError,
    EasyApplyUnavailableError,
    ElementNotFoundError,
    ManualInputRequiredError,
    NotLoggedInError,
    SecurityCheckpointError,
    StopRequestedError,
    ThrottleLimitError,
    UnexpectedPageError,
)
from app.automation.linkedin.service import LinkedInBrowserService
from app.automation.throttle import Throttle

__all__ = [
    "AlreadyAppliedError",
    "ApplicationDraft",
    "AutomationEngine",
    "AutomationError",
    "BrowserNotReadyError",
    "BrowserSession",
    "EasyApplyUnavailableError",
    "ElementNotFoundError",
    "FormAnswer",
    "FormQuestion",
    "JobPosting",
    "LinkedInBrowserService",
    "LinkedInService",
    "ManualInputRequiredError",
    "NotLoggedInError",
    "ProfileContext",
    "QuestionKind",
    "SearchFilters",
    "SecurityCheckpointError",
    "SessionState",
    "StopRequestedError",
    "Throttle",
    "ThrottleLimitError",
    "UnexpectedPageError",
    "get_engine",
]
