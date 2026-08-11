"""Automation layer: the browser-agnostic boundary and its error types."""

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

__all__ = [
    "AlreadyAppliedError",
    "ApplicationDraft",
    "AutomationError",
    "BrowserNotReadyError",
    "EasyApplyUnavailableError",
    "ElementNotFoundError",
    "FormAnswer",
    "FormQuestion",
    "JobPosting",
    "LinkedInService",
    "ManualInputRequiredError",
    "NotLoggedInError",
    "ProfileContext",
    "QuestionKind",
    "SearchFilters",
    "SecurityCheckpointError",
    "SessionState",
    "StopRequestedError",
    "ThrottleLimitError",
    "UnexpectedPageError",
]
