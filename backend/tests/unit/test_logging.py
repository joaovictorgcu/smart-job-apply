"""Structured logging: the `extra=` fields must actually reach the JSON line.

Every service in this codebase logs with `extra={"action": ..., "user_id": ...}`.
Those fields are the whole point of the JSON formatter, and for the life of the
module they were silently discarded: `logging.LoggerAdapter.process` overwrites
`kwargs["extra"]` with the adapter's own mapping. Nothing failed, nothing warned —
the lines just came out without their context.
"""

from __future__ import annotations

import ast
import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.observability.logger import (
    JsonFormatter,
    bind_context,
    clear_context,
    get_logger,
)

APP_ROOT = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture
def captured() -> Iterator[io.StringIO]:
    """Install the real `JsonFormatter` on a throwaway root handler."""
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    previous_handlers, previous_level = root.handlers[:], root.level
    root.handlers = [handler]
    root.setLevel(logging.DEBUG)
    clear_context()
    try:
        yield buffer
    finally:
        root.handlers = previous_handlers
        root.setLevel(previous_level)
        clear_context()


def emitted(buffer: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]


class TestExtraSurvives:
    def test_per_call_fields_reach_the_json_line(self, captured: io.StringIO) -> None:
        get_logger("probe").info(
            "Application submitted.",
            extra={"action": "engine.submit", "status": "ok", "user_id": 42, "run_id": 7},
        )
        line = emitted(captured)[0]
        assert line["message"] == "Application submitted."
        assert line["action"] == "engine.submit"
        assert line["status"] == "ok"
        assert line["user_id"] == 42
        assert line["run_id"] == 7

    def test_a_log_without_extra_still_works(self, captured: io.StringIO) -> None:
        get_logger("probe").info("Plain line.")
        line = emitted(captured)[0]
        assert line["message"] == "Plain line."
        assert line["level"] == "INFO"

    def test_bound_context_and_extra_are_both_present(self, captured: io.StringIO) -> None:
        bind_context(request_id="abc123", user_id=1)
        get_logger("probe").warning("Rate limited.", extra={"action": "http.rate_limit"})
        line = emitted(captured)[0]
        assert line["request_id"] == "abc123"
        assert line["user_id"] == 1
        assert line["action"] == "http.rate_limit"

    def test_the_call_site_wins_over_the_adapter(self, captured: io.StringIO) -> None:
        # Callers pass a field explicitly to override, never to be overridden.
        logger = get_logger("probe")
        logger.extra = {"action": "adapter.default"}
        logger.info("Overridden.", extra={"action": "call.site"})
        assert emitted(captured)[0]["action"] == "call.site"

    def test_an_exception_is_rendered_under_error(self, captured: io.StringIO) -> None:
        logger = get_logger("probe")
        try:
            raise ValueError("boom")
        except ValueError as exc:
            logger.error("Failed.", exc_info=exc, extra={"action": "engine.run"})
        line = emitted(captured)[0]
        assert line["action"] == "engine.run"
        assert "ValueError: boom" in line["error"]


def _reserved_record_attributes() -> set[str]:
    """Keys `Logger.makeRecord` refuses to let `extra` overwrite.

    Read off a real `LogRecord` rather than hard-coded, so a new attribute in a
    future CPython is covered without touching this test.
    """
    record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
    return set(record.__dict__) | {"message", "asctime"}


def _extra_keys_in(path: Path) -> Iterator[tuple[str, int]]:
    """Every literal string key of an `extra={...}` keyword in one module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "extra" or not isinstance(keyword.value, ast.Dict):
                continue
            for key in keyword.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    yield key.value, key.lineno


class TestNoReservedKeys:
    """A guard, not a unit test.

    While `extra` was being discarded, a reserved key such as `filename` was
    harmless. Now that it reaches `makeRecord`, the same line raises
    `KeyError: "Attempt to overwrite 'filename' in LogRecord"` — at runtime, on the
    error path, which is the worst possible place to discover it.
    """

    def test_no_log_call_uses_a_reserved_logrecord_key(self) -> None:
        reserved = _reserved_record_attributes()
        offenders = [
            f"{path.relative_to(APP_ROOT)}:{lineno} -> extra={{{key!r}: ...}}"
            for path in sorted(APP_ROOT.rglob("*.py"))
            for key, lineno in _extra_keys_in(path)
            if key in reserved
        ]
        assert not offenders, (
            "These log calls would raise KeyError in makeRecord. Rename the field:\n"
            + "\n".join(offenders)
        )

    def test_the_guard_can_actually_fail(self, tmp_path: Path) -> None:
        # A guard that cannot fail is decoration; prove the AST walk finds one.
        module = tmp_path / "offender.py"
        module.write_text('logger.info("x", extra={"filename": "cv.pdf"})\n', encoding="utf-8")
        found = {key for key, _ in _extra_keys_in(module)}
        assert found & _reserved_record_attributes() == {"filename"}
