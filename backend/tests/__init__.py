"""Backend test suite.

The suite runs fully offline. The two boundaries that could reach the network are
replaced by fakes at the seams the application itself uses:

* `get_ai_client` — patched in `app.ai.scoring`, `app.ai.client` and `app.ai`, so
  every caller receives `tests.fixtures.fake_ai.FakeAIClient`;
* `LinkedInBrowserService` — patched in `app.automation.engine`, so the engine
  drives `tests.fixtures.fake_linkedin.FakeLinkedInService` instead of Chromium.

On top of that, `conftest.block_network` replaces the Anthropic and Playwright
entry points with functions that raise, so an unpatched path fails loudly instead
of quietly opening a socket.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Any

__all__ = ["find_attr", "import_first"]


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
    wanted = (names,) if isinstance(names, str) else names
    for path in module_paths:
        module = import_first(path)
        if module is None:
            continue
        for name in wanted:
            attribute = getattr(module, name, None)
            if attribute is not None:
                return attribute
    return None
