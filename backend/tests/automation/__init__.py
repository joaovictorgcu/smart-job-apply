"""Automation-layer tests, plus the resolution of the engine that owns them.

Expected engine surface (`app/automation/engine.py`), resolved leniently so a
rename shows up as a precise xfail instead of an obscure error:

    class AutomationEngine:
        def __init__(self, session, user, *, linkedin=..., ai=...) -> None
        async def run_search(self, filters: SearchFilters, search=None) -> AutomationRun
        async def prepare_applications(self, job_ids: list[int]) -> AutomationRun
        async def submit_application(self, application_id: int) -> Application
        async def stop_all(self) -> int          # kill switch
"""

from __future__ import annotations

from typing import Any

from tests import call_maybe_async, find_attr, first_method

ENGINE_MODULES = (
    "app.automation.engine",
    "app.automation.orchestrator",
    "app.automation.runner",
    "app.services.automation",
)

ENGINE_NAMES = (
    "AutomationEngine",
    "Engine",
    "AutomationOrchestrator",
    "Orchestrator",
    "AutomationService",
)

AutomationEngine = find_attr(ENGINE_NAMES, *ENGINE_MODULES)


def build_engine(session: Any, user: Any, linkedin: Any, ai: Any) -> Any:
    """Instantiate the engine across the plausible constructor shapes."""
    attempts: tuple[tuple[tuple[Any, ...], dict[str, Any]], ...] = (
        ((session, user), {"linkedin": linkedin, "ai": ai}),
        ((session, user), {"linkedin": linkedin, "ai_client": ai}),
        ((session, user), {"service": linkedin, "ai": ai}),
        ((session, user, linkedin, ai), {}),
        ((session,), {"user": user, "linkedin": linkedin, "ai": ai}),
        ((session, user), {}),
        ((session,), {}),
    )
    last_error: Exception | None = None
    for args, kwargs in attempts:
        try:
            return AutomationEngine(*args, **kwargs)
        except TypeError as exc:  # signature mismatch, try the next shape
            last_error = exc
    raise TypeError(f"Could not construct {AutomationEngine!r}: {last_error}")


def search_method(engine: Any) -> Any:
    return first_method(engine, "run_search", "search", "run_search_job", "execute_search")


def prepare_method(engine: Any) -> Any:
    return first_method(
        engine, "prepare_applications", "prepare", "prepare_application", "run_prepare"
    )


def submit_method(engine: Any) -> Any:
    return first_method(engine, "submit_application", "submit", "run_submit")


def stop_method(engine: Any) -> Any:
    return first_method(engine, "stop_all", "stop", "request_stop", "kill")


_SIGNATURE_HINTS = ("argument", "parameter", "positional", "keyword")


async def invoke(func: Any, *variants: tuple[tuple[Any, ...], dict[str, Any]]) -> Any:
    """Call `func` with the first argument shape it accepts.

    Only signature mismatches are swallowed — a `TypeError` raised from inside the
    function still surfaces as a real failure.
    """
    last_error: TypeError | None = None
    for args, kwargs in variants:
        try:
            return await call_maybe_async(func, *args, **kwargs)
        except TypeError as exc:
            if not any(hint in str(exc) for hint in _SIGNATURE_HINTS):
                raise
            last_error = exc
    raise TypeError(f"No accepted call shape for {func!r}: {last_error}")
