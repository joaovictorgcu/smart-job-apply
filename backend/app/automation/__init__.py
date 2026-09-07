"""Automation layer: the browser-agnostic boundary and its error types.

Layering is `AutomationEngine -> LinkedInBrowserService -> Playwright`. Business
logic imports from here and never touches Playwright, and every selector lives in
`app.automation.selectors`.

Names are resolved lazily, and that is load-bearing rather than a micro-optimisation.
Importing a submodule runs its package's `__init__` first, so while this module
imported the engine eagerly, `from app.automation.errors import ...` pulled in
`engine -> services.job_service -> app.api.errors` — and `app.api.errors` is
itself what wanted the automation errors. The cycle made `import app.main` fail
outright, so the server could not start at all; only an import that happened to
touch `app.automation` first would succeed.

With `__getattr__`, importing the leaf `app.automation.errors` initialises an
empty package and stops there. `from app.automation import AutomationEngine`
still works and still loads the engine, just at the moment it is asked for.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Only for type checkers and editors; never executed, so no cycle.
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

# Public name -> the submodule that defines it.
_EXPORTS: dict[str, str] = {
    "BrowserSession": "app.automation.browser",
    "ApplicationDraft": "app.automation.contracts",
    "FormAnswer": "app.automation.contracts",
    "FormQuestion": "app.automation.contracts",
    "JobPosting": "app.automation.contracts",
    "LinkedInService": "app.automation.contracts",
    "ProfileContext": "app.automation.contracts",
    "QuestionKind": "app.automation.contracts",
    "SearchFilters": "app.automation.contracts",
    "SessionState": "app.automation.contracts",
    "AutomationEngine": "app.automation.engine",
    "get_engine": "app.automation.engine",
    "AlreadyAppliedError": "app.automation.errors",
    "AutomationError": "app.automation.errors",
    "BrowserNotReadyError": "app.automation.errors",
    "EasyApplyUnavailableError": "app.automation.errors",
    "ElementNotFoundError": "app.automation.errors",
    "ManualInputRequiredError": "app.automation.errors",
    "NotLoggedInError": "app.automation.errors",
    "SecurityCheckpointError": "app.automation.errors",
    "StopRequestedError": "app.automation.errors",
    "ThrottleLimitError": "app.automation.errors",
    "UnexpectedPageError": "app.automation.errors",
    "LinkedInBrowserService": "app.automation.linkedin.service",
    "Throttle": "app.automation.throttle",
}


def __getattr__(name: str) -> Any:
    """Import the submodule that owns `name` on first access (PEP 562)."""
    module_path = _EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_path), name)
    # Cached in the module namespace, so the lookup happens once per name.
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(_EXPORTS)


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
