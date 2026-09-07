"""The automation orchestrator.

`AutomationEngine` is the only place where the browser, the AI layer and the
database meet. It owns one `LinkedInBrowserService` per user, serializes browser
work with a per-user lock, persists progress into `AutomationRun.checkpoint` so a
run can be resumed, and publishes every state change to the dashboard.

Assisted mode is enforced here, not in the UI:

* `prepare_application` fills the form and leaves it at the review step with
  `status = AWAITING_REVIEW`. In dry-run mode it never opens the real modal.
* `submit_application` is the ONLY path that reaches the submit button, and it
  refuses unless the application is awaiting review, dry run is off, the user
  approved it (`approved_at`), the daily cap is not reached and we are inside the
  configured working hours.
* A `SecurityCheckpointError` anywhere turns the run into `BLOCKED` and stops the
  session. We never try to get past a challenge.

The class is split across this package by phase of a run — `session`, `search`,
`prepare`, `submit`, plus `runs`, `events`, `context` and `answers` for the
support they share — and assembled into a single class in `core`. It stays one
class: the phases call into each other and share the concurrency state that
`core` owns.

`get_engine`, the singleton it caches and `LinkedInBrowserService` deliberately
live in this module rather than in a submodule: `app.automation.engine` is the
name the rest of the codebase and the test fixtures bind to, and both are
swapped there by name.
"""

from app.automation.engine.core import AutomationEngine
from app.automation.linkedin.service import LinkedInBrowserService

__all__ = ["AutomationEngine", "LinkedInBrowserService", "get_engine"]

_engine: AutomationEngine | None = None


def get_engine() -> AutomationEngine:
    """The process-wide engine instance."""
    global _engine
    if _engine is None:
        _engine = AutomationEngine()
    return _engine
