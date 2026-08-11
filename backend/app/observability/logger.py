"""Logging estruturado em JSON, com contexto por request/execução.

Nada de `print()`: cada linha sai como JSON com `user_id`, `job_id`,
`application_id`, `run_id`, `action`, `status` e `error` quando existirem.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

# No module-level default: a single dict instance would be shared by every context.
# Each read supplies its own empty mapping instead.
_context: ContextVar[dict[str, Any]] = ContextVar("log_context")

_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name",
    "pathname", "process", "processName", "relativeCreated", "stack_info",
    "thread", "threadName", "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(_context.get({}))
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO", *, as_json: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if as_json
        else logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    # O access log do uvicorn duplica o que já registramos por request.
    logging.getLogger("uvicorn.access").propagate = False


def get_logger(name: str) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logging.getLogger(name), {})


def bind_context(**values: Any) -> None:
    """Acrescenta campos a todas as linhas de log da task atual."""
    merged = {**_context.get({}), **{k: v for k, v in values.items() if v is not None}}
    _context.set(merged)


def clear_context() -> None:
    _context.set({})


def current_context() -> dict[str, Any]:
    return dict(_context.get({}))
