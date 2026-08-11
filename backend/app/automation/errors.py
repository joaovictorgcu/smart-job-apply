"""Automation errors.

The hierarchy separates what is recoverable (retry it) from what demands an
immediate stop — `SecurityCheckpointError` is the most important one: we never try
to work around a security verification.
"""

from __future__ import annotations


class AutomationError(RuntimeError):
    """Base class for every automation failure."""

    recoverable = False


class BrowserNotReadyError(AutomationError):
    """The browser is not open (or it died)."""

    recoverable = True


class NotLoggedInError(AutomationError):
    """LinkedIn session missing or expired; the user must log in manually."""


class SecurityCheckpointError(AutomationError):
    """CAPTCHA / security verification detected.

    Signals a full stop. Never attempt to solve or bypass it.
    """

    def __init__(self, reason: str = "Security verification detected.") -> None:
        super().__init__(reason)
        self.reason = reason


class UnexpectedPageError(AutomationError):
    """The page is not the expected one (UI change, redirect, error)."""

    recoverable = True

    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message)
        self.url = url


class ElementNotFoundError(UnexpectedPageError):
    """Selector not found — most likely a LinkedIn interface change."""


class EasyApplyUnavailableError(AutomationError):
    """The job does not offer Easy Apply (or it has already been answered)."""


class AlreadyAppliedError(AutomationError):
    """LinkedIn reports that an application already exists for this job."""


class ThrottleLimitError(AutomationError):
    """A guardrail blocked the action (daily cap or outside working hours)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class StopRequestedError(AutomationError):
    """Kill switch triggered by the user."""


class ManualInputRequiredError(AutomationError):
    """The form has a field we cannot fill in confidently."""

    def __init__(self, message: str, *, questions: list[str] | None = None) -> None:
        super().__init__(message)
        self.questions = questions or []
