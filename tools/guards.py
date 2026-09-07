#!/usr/bin/env python3
"""CI guards for the safety promises this repository only makes in prose.

The README, `docs/safety.md` and `CONTRIBUTING.md` all state the same thesis: this
tool never sends a job application without an explicit, per-application human
confirmation, and its decision core stays testable without a browser, a database or
a paid API. Prose does not fail a build. Every guard below is one of those
sentences rewritten as an assertion over the source tree.

They exist because the regressions they catch are effectively invisible in review:

* A diff that flips `dry_run` from `True` to `False` is one character wide and
  reads exactly like a default being tidied up.
* `await service.submit()` added inside some service is an ordinary line of code.
  It just happens to reach LinkedIn without passing through
  `AutomationEngine._submit_application`, the single place where
  `status == AWAITING_REVIEW`, `approved_at is not None`, working hours and the
  daily cap are checked. The promise is not "we ask for approval somewhere"; it is
  "there is exactly one door".
* A broad `except Exception` that neither re-raises nor logs looks defensive. In
  this codebase that exact shape silently disabled every AI call for months —
  nothing failed, nothing warned, no test went red, and the feature simply stopped
  existing.
* An `extra={"filename": ...}` on a log call raises `KeyError` inside
  `Logger.makeRecord` — at runtime, on the error path, which is the worst possible
  place to find out.

A reviewer scanning a 200-line pull request will not reliably catch any of these.
A five-second AST walk catches all of them, every time, on every push.

Guards
------
G1  `Settings.assisted_mode_only` still defaults to `True`.
G2  `UserSettings.dry_run` and `UserSettings.require_manual_approval` still
    default to `True`.
G3  `.submit()` is called only from the sanctioned approval path.
G4  Playwright is imported only by the two modules allowed to know about a browser.
G5  `app/domain/` imports no I/O: no SQLAlchemy, Anthropic, Playwright, FastAPI or
    ORM models.
G6  No broad `except` in `app/domain/` or `app/ai/` swallows an error in silence.
G7  No log call passes an `extra=` key that collides with a `LogRecord` attribute.

A guard that cannot locate its target reports a violation rather than passing:
renaming a field must break the build, not disable the check.

Stdlib only, and nothing imported from `app` or from the test suite — CI must be
able to run this before a single dependency is installed, and the guards must keep
working even when the application itself refuses to import. `print()` is banned in
application code for good reasons; here the printed lines *are* the output
contract, so this file is the one exception.

Usage:
    python tools/guards.py [REPO_ROOT]      # REPO_ROOT defaults to two levels up
Exit status:
    0 when every guard passes, 1 otherwise.
"""

from __future__ import annotations

import ast
import logging
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

# --- Policy -----------------------------------------------------------------

# The only modules allowed to call `.submit()`. `engine.py` and `engine/` are both
# accepted because that module is being split into a package; the guard should not
# depend on which layout won.
SUBMIT_ALLOWED_FILES = frozenset(
    {
        "automation/engine.py",
        "automation/linkedin/service.py",
        "automation/linkedin/apply.py",
    }
)
SUBMIT_ALLOWED_PACKAGE = "automation/engine/"

# Everything that knows a browser exists lives behind these two paths.
PLAYWRIGHT_ALLOWED_FILE = "automation/browser.py"
PLAYWRIGHT_ALLOWED_PACKAGE = "automation/linkedin/"

# `app/domain/` is the pure core: no network, no ORM, no framework.
DOMAIN_FORBIDDEN_IMPORTS = ("sqlalchemy", "anthropic", "playwright", "fastapi", "app.models")

# Packages whose error handling must never be silent.
NO_SILENT_EXCEPT_PACKAGES = ("domain", "ai")

BROAD_EXCEPTION_NAMES = frozenset({"Exception", "BaseException"})

# `logger.warn` is deprecated but still resolves; treat it as a log call anyway.
LOG_METHOD_NAMES = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
)


@dataclass(frozen=True)
class Violation:
    guard: str
    path: str
    line: int
    message: str

    def render(self) -> str:
        return f"GUARD {self.guard} FAILED  {self.path}:{self.line}  {self.message}"


# --- Shared AST helpers -----------------------------------------------------


def app_root(root: Path) -> Path:
    return root / "backend" / "app"


def python_files(base: Path) -> list[Path]:
    return sorted(base.rglob("*.py")) if base.is_dir() else []


def relative(path: Path, base: Path) -> str:
    """POSIX-style path for stable messages on Windows and Linux alike."""
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def class_body(tree: ast.Module, name: str) -> list[ast.stmt] | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node.body
    return None


def annotated_assignment(body: Sequence[ast.stmt], name: str) -> ast.AnnAssign | None:
    for node in body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            return node
    return None


def is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def imported_modules(tree: ast.Module) -> Iterator[tuple[str, int]]:
    """Every absolute dotted module name imported by a file, with its line."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            # Relative imports (`from . import x`) never reach a third-party
            # package, so they are irrelevant to the purity guards.
            yield node.module, node.lineno


def imports_package(module: str, package: str) -> bool:
    return module == package or module.startswith(f"{package}.")


# --- G1 ---------------------------------------------------------------------


def g1_assisted_mode_default(root: Path) -> list[Violation]:
    """`Settings.assisted_mode_only` must still default to True."""
    path = app_root(root) / "config.py"
    where = relative(path, root)
    if not path.is_file():
        return [Violation("G1", where, 0, "backend/app/config.py is missing.")]

    body = class_body(parse(path), "Settings")
    if body is None:
        return [Violation("G1", where, 0, "class Settings not found; the guard cannot verify it.")]

    node = annotated_assignment(body, "assisted_mode_only")
    if node is None:
        return [
            Violation(
                "G1",
                where,
                0,
                "Settings.assisted_mode_only is gone. Assisted mode is the product's "
                "core promise; it may not be removed or renamed silently.",
            )
        ]
    if not is_true(node.value):
        return [
            Violation(
                "G1",
                where,
                node.lineno,
                "Settings.assisted_mode_only no longer defaults to True. Shipping a "
                "default that submits without confirmation is the one change this "
                "project cannot make.",
            )
        ]
    return []


# --- G2 ---------------------------------------------------------------------


def mapped_column_default(node: ast.AnnAssign) -> ast.expr | None:
    """The `default=` argument of `mapped_column(...)`, if it is written literally.

    The AST shape in `models/user.py` is plain enough to read directly
    (`Mapped[bool] = mapped_column(Boolean, default=True)`), so no regex fallback
    is needed. If a refactor ever hides the default behind a helper, this returns
    None and the caller reports a violation — an unreadable default is treated as
    a failure, never as a pass.
    """
    call = node.value
    if not isinstance(call, ast.Call):
        return None
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name != "mapped_column":
        return None
    for keyword in call.keywords:
        if keyword.arg == "default":
            return keyword.value
    return None


def g2_user_settings_defaults(root: Path) -> list[Violation]:
    """`UserSettings.dry_run` and `.require_manual_approval` must still default to True."""
    path = app_root(root) / "models" / "user.py"
    where = relative(path, root)
    if not path.is_file():
        return [Violation("G2", where, 0, "backend/app/models/user.py is missing.")]

    body = class_body(parse(path), "UserSettings")
    if body is None:
        return [
            Violation("G2", where, 0, "class UserSettings not found; the guard cannot verify it.")
        ]

    violations: list[Violation] = []
    for field in ("dry_run", "require_manual_approval"):
        node = annotated_assignment(body, field)
        if node is None:
            violations.append(
                Violation(
                    "G2",
                    where,
                    0,
                    f"UserSettings.{field} is gone. Every new account must start in "
                    "the safe state; this column may not be removed or renamed silently.",
                )
            )
            continue
        default = mapped_column_default(node)
        if not is_true(default):
            violations.append(
                Violation(
                    "G2",
                    where,
                    node.lineno,
                    f"UserSettings.{field} no longer has a literal `default=True`. "
                    "Every account created after this change would start with the "
                    "guardrail off, silently and retroactively.",
                )
            )
    return violations


# --- G3 ---------------------------------------------------------------------


def submit_is_allowed(module: str) -> bool:
    return module in SUBMIT_ALLOWED_FILES or module.startswith(SUBMIT_ALLOWED_PACKAGE)


def g3_submit_call_sites(root: Path) -> list[Violation]:
    """`.submit()` may be called only from the sanctioned approval path.

    Matched on the attribute name exactly, so `submitted_today`,
    `submitted_last_days`, `submit_application` and `ready_to_submit` are ignored.
    A non-awaited call counts too: wrapping the coroutine does not make it safe.
    """
    app = app_root(root)
    violations: list[Violation] = []
    allowed = ", ".join(sorted(SUBMIT_ALLOWED_FILES))
    for path in python_files(app):
        module = relative(path, app)
        if submit_is_allowed(module):
            continue
        for node in ast.walk(parse(path)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "submit"
            ):
                violations.append(
                    Violation(
                        "G3",
                        relative(path, root),
                        node.lineno,
                        f"`{ast.unparse(node.func.value)}.submit()` is outside the approval "
                        f"path. Only {allowed} (or automation/engine/*.py) may call it: "
                        "every other route reaches LinkedIn without the "
                        "AWAITING_REVIEW / approved_at / dry-run / working-hours checks.",
                    )
                )
    return violations


# --- G4 ---------------------------------------------------------------------


def g4_playwright_imports(root: Path) -> list[Violation]:
    """Playwright stays behind the browser adapter and the LinkedIn package."""
    app = app_root(root)
    violations: list[Violation] = []
    for path in python_files(app):
        module = relative(path, app)
        if module == PLAYWRIGHT_ALLOWED_FILE or module.startswith(PLAYWRIGHT_ALLOWED_PACKAGE):
            continue
        for imported, line in imported_modules(parse(path)):
            if imports_package(imported, "playwright"):
                violations.append(
                    Violation(
                        "G4",
                        relative(path, root),
                        line,
                        f"imports `{imported}` outside app/{PLAYWRIGHT_ALLOWED_FILE} and "
                        f"app/{PLAYWRIGHT_ALLOWED_PACKAGE}. Browser types leaking into the "
                        "rest of the app is what makes a suite need a real Chromium to run.",
                    )
                )
    return violations


# --- G5 ---------------------------------------------------------------------


def g5_domain_purity(root: Path) -> list[Violation]:
    """`app/domain/` holds the rules; it must stay runnable with no I/O at all."""
    app = app_root(root)
    domain = app / "domain"
    violations: list[Violation] = []
    for path in python_files(domain):
        for imported, line in imported_modules(parse(path)):
            for forbidden in DOMAIN_FORBIDDEN_IMPORTS:
                if imports_package(imported, forbidden):
                    violations.append(
                        Violation(
                            "G5",
                            relative(path, root),
                            line,
                            f"app/domain/ imports `{imported}`. The domain package exists "
                            "precisely so the scoring and language rules can be tested "
                            "without a database, a browser or an API key.",
                        )
                    )
    return violations


# --- G6 ---------------------------------------------------------------------


def is_broad_handler(node: ast.expr | None) -> bool:
    """True for `except:`, `except Exception:` and any tuple containing one."""
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in BROAD_EXCEPTION_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in BROAD_EXCEPTION_NAMES
    if isinstance(node, ast.Tuple):
        return any(is_broad_handler(element) for element in node.elts)
    return False


def reraises_or_logs(handler: ast.ExceptHandler) -> bool:
    for statement in handler.body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Raise):
                return True
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in LOG_METHOD_NAMES
            ):
                return True
    return False


def g6_silent_broad_except(root: Path) -> list[Violation]:
    """A broad catch that neither re-raises nor logs deletes the failure entirely."""
    app = app_root(root)
    violations: list[Violation] = []
    for package in NO_SILENT_EXCEPT_PACKAGES:
        for path in python_files(app / package):
            for node in ast.walk(parse(path)):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if not is_broad_handler(node.type) or reraises_or_logs(node):
                    continue
                caught = ast.unparse(node.type) if node.type is not None else "<bare>"
                violations.append(
                    Violation(
                        "G6",
                        relative(path, root),
                        node.lineno,
                        f"`except {caught}` neither re-raises nor logs. This is the exact "
                        "shape that silently disabled every AI call in this codebase for "
                        "months: catch narrowly, or log before swallowing.",
                    )
                )
    return violations


# --- G7 ---------------------------------------------------------------------


def reserved_record_attributes() -> frozenset[str]:
    """Keys `Logger.makeRecord` refuses to let `extra` overwrite.

    Read off a real `LogRecord` instead of hard-coded, so an attribute added by a
    future CPython (`taskName` in 3.12, for instance) is covered for free.
    """
    record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
    return frozenset(record.__dict__) | {"message", "asctime"}


def extra_keys_in(tree: ast.Module) -> Iterator[tuple[str, int]]:
    """Every literal string key of an `extra={...}` keyword argument."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "extra" or not isinstance(keyword.value, ast.Dict):
                continue
            for key in keyword.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    yield key.value, key.lineno


def g7_reserved_log_keys(root: Path) -> list[Violation]:
    """No structured-logging field may shadow a LogRecord attribute."""
    app = app_root(root)
    reserved = reserved_record_attributes()
    violations: list[Violation] = []
    for path in python_files(app):
        for key, line in extra_keys_in(parse(path)):
            if key in reserved:
                violations.append(
                    Violation(
                        "G7",
                        relative(path, root),
                        line,
                        f"extra={{{key!r}: ...}} collides with a reserved LogRecord "
                        "attribute; makeRecord raises KeyError at runtime, on the error "
                        "path. Rename the field.",
                    )
                )
    return violations


# --- Runner -----------------------------------------------------------------

ALL_GUARDS: tuple[Callable[[Path], list[Violation]], ...] = (
    g1_assisted_mode_default,
    g2_user_settings_defaults,
    g3_submit_call_sites,
    g4_playwright_imports,
    g5_domain_purity,
    g6_silent_broad_except,
    g7_reserved_log_keys,
)


def default_root() -> Path:
    """The repository root: two levels up from this file (`<root>/tools/guards.py`)."""
    return Path(__file__).resolve().parents[1]


def run_all(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for guard in ALL_GUARDS:
        violations.extend(guard(root))
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    root = Path(arguments[0]).resolve() if arguments else default_root()

    try:
        violations = run_all(root)
    except SyntaxError as exc:
        # Unparsable source means the guards ran on nothing; that is a failure,
        # not a pass.
        print(f"GUARD SETUP FAILED  {exc.filename}:{exc.lineno}  cannot parse: {exc.msg}")
        return 1

    for violation in violations:
        print(violation.render())

    if violations:
        failed = len({violation.guard for violation in violations})
        print(f"\n{len(violations)} violation(s) across {failed} guard(s). See docs/safety.md.")
        return 1

    print(f"All {len(ALL_GUARDS)} guards passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
