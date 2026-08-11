"""Backend test suite.

The suite runs fully offline: the Anthropic API and LinkedIn are replaced at their
boundaries (``app.ai.get_ai_client`` and the ``LinkedInService`` protocol) by the
fakes in ``tests.fixtures``.

Parts of the backend are still being written (the FastAPI app and routers, the
Claude client, the automation engine, the throttle and the service layer). The
resolution helpers below let a test declare the symbol it needs, look for it
across the plausible module paths, and be reported as ``xfail`` naming the
missing symbol instead of blowing up at collection time. Once the module lands,
the same test runs for real with no edit.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable, Iterable, Sequence
from typing import Any

__all__ = [
    "call_maybe_async",
    "construct",
    "find_attr",
    "first_method",
    "import_first",
    "missing",
]


def import_first(*module_paths: str) -> Any | None:
    """Import the first importable module among `module_paths`, else None."""
    for path in module_paths:
        try:
            return importlib.import_module(path)
        except ImportError:
            continue
    return None


def find_attr(names: str | Sequence[str], *module_paths: str) -> Any | None:
    """First attribute named in `names` found on any of `module_paths`, else None."""
    wanted: Iterable[str] = (names,) if isinstance(names, str) else names
    for path in module_paths:
        module = import_first(path)
        if module is None:
            continue
        for name in wanted:
            attribute = getattr(module, name, None)
            if attribute is not None:
                return attribute
    return None


def first_method(obj: object, *names: str) -> Callable[..., Any] | None:
    """First callable attribute among `names`, so a rename does not break a test."""
    for name in names:
        candidate = getattr(obj, name, None)
        if callable(candidate):
            return candidate
    return None


def construct(cls: Any, *args: Any, **kwargs: Any) -> Any:
    """Instantiate `cls`, falling back to fewer arguments when it takes fewer."""
    try:
        return cls(*args, **kwargs)
    except TypeError:
        try:
            return cls(**kwargs)
        except TypeError:
            return cls()


async def call_maybe_async(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call `func` and await it when it turns out to be a coroutine function."""
    result = func(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def missing(symbol: str, *module_paths: str) -> str:
    """An xfail reason that names exactly what is not implemented yet."""
    return f"{symbol} not found in any of: {', '.join(module_paths)} (owned by another agent)"
