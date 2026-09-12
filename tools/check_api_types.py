#!/usr/bin/env python3
"""Does `frontend/src/types/api.ts` still describe the API it claims to mirror?

That file opens with "Source of truth: backend/app/schemas/*.py ... Field names
must match byte-for-byte." Nothing enforced it. A field added to a Pydantic
model and forgotten here does not fail a build, does not fail a test, and does
not fail a type check — it simply becomes a value the frontend is told does not
exist. `JobRead.is_stale`, `deadline` and `expired_at` were exactly that: the
backend refuses to prepare a stale posting, and the job card could not say so
because its type denied the field.

Why this is not in `tools/guards.py`: the guards are stdlib-only and must run
before a single dependency is installed. Reading the schema means importing the
app, which means FastAPI and Pydantic. So this is a separate check that runs
after `pip install`, from `make check-api-types` and from CI.

Why not code generation instead: the hand-written types carry documentation and
the ergonomic names the whole frontend imports (`Job`, not
`components["schemas"]["JobRead"]`). Replacing them would touch every file for
a class of bug that a hundred-line comparison catches on its own. Measured
before deciding — one type had drifted, out of twenty-two.

Usage:
    python tools/check_api_types.py [REPO_ROOT]
Exit status:
    0 when every mirrored type matches, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The TypeScript interface that mirrors each schema. Only types the frontend
# actually reads off a response are listed: request bodies are Partial<> shapes
# the server validates anyway, and a missing field there fails loudly.
MIRRORS: dict[str, str] = {
    "Application": "ApplicationRead",
    "ApplicationCard": "ApplicationCard",
    "ApplicationDetail": "ApplicationDetail",
    "ApplicationResume": "ApplicationResumeRead",
    "AutomationRun": "AutomationRunRead",
    "DashboardStats": "DashboardStats",
    "Experience": "ExperienceRead",
    "ExperienceMove": "ExperienceMoveRead",
    "Job": "JobRead",
    "JobDetail": "JobDetail",
    "JobPreferences": "JobPreferencesRead",
    "MasterResume": "MasterResumeRead",
    "OutcomeStats": "OutcomeStats",
    "Profile": "ProfileRead",
    "Recommendation": "RecommendationRead",
    "ResumeComparison": "ResumeComparisonRead",
    "ResumeIntake": "ResumeIntakeRead",
    "Search": "SearchRead",
    "SessionStatus": "SessionStatus",
    "User": "UserRead",
    "UserSettings": "UserSettingsRead",
}

# Fields the frontend deliberately does not mirror, with the reason. An entry
# here is a decision someone made; an unlisted mismatch is a mistake.
ALLOWED_MISSING: dict[str, set[str]] = {}

TYPES_FILE = Path("frontend") / "src" / "types" / "api.ts"

# `export interface Name extends Parent {` ... `\n}` — anchored on the name so
# `Job` does not match `JobPreferences`, and following `extends` so an inherited
# field counts as present.
_INTERFACE = re.compile(
    r"export interface (?P<name>\w+)(?:\s+extends\s+(?P<parents>[\w, ]+))?\s*\{(?P<body>.*?)\n\}",
    re.S,
)
_FIELD = re.compile(r"^\s{2}(\w+)\??:", re.M)


def parse_interfaces(source: str) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """Every interface's own fields, and what it extends."""
    own: dict[str, set[str]] = {}
    parents: dict[str, list[str]] = {}
    for match in _INTERFACE.finditer(source):
        name = match.group("name")
        own[name] = set(_FIELD.findall(match.group("body")))
        parents[name] = [
            part.strip() for part in (match.group("parents") or "").split(",") if part.strip()
        ]
    return own, parents


def fields_of(
    name: str, own: dict[str, set[str]], parents: dict[str, list[str]], seen: set[str] | None = None
) -> set[str]:
    """An interface's fields including everything it inherits."""
    seen = seen if seen is not None else set()
    if name in seen or name not in own:
        return set()
    seen.add(name)
    result = set(own[name])
    for parent in parents.get(name, []):
        result |= fields_of(parent, own, parents, seen)
    return result


def load_schemas(root: Path) -> dict[str, dict]:
    """The live OpenAPI components, built from the real Pydantic models."""
    sys.path.insert(0, str(root / "backend"))
    from app.main import create_app

    return create_app().openapi()["components"]["schemas"]


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    root = Path(arguments[0]).resolve() if arguments else Path(__file__).resolve().parents[1]

    types_path = root / TYPES_FILE
    if not types_path.is_file():
        print(f"MISSING  {TYPES_FILE}")
        return 1

    own, parents = parse_interfaces(types_path.read_text(encoding="utf-8"))
    schemas = load_schemas(root)

    problems = 0
    for ts_name, schema_name in sorted(MIRRORS.items()):
        if ts_name not in own:
            print(f"GONE     interface {ts_name} — it mirrored {schema_name}")
            problems += 1
            continue
        if schema_name not in schemas:
            print(f"GONE     schema {schema_name} — {ts_name} still mirrors it")
            problems += 1
            continue

        api = set(schemas[schema_name].get("properties", {}))
        declared = fields_of(ts_name, own, parents)
        missing = api - declared - ALLOWED_MISSING.get(ts_name, set())
        extra = declared - api

        if missing:
            print(
                f"DRIFT    {ts_name} does not declare {', '.join(sorted(missing))} — "
                f"{schema_name} returns them, so the frontend is told they do not exist."
            )
            problems += 1
        if extra:
            print(
                f"DRIFT    {ts_name} declares {', '.join(sorted(extra))}, which "
                f"{schema_name} does not return — reading one yields undefined."
            )
            problems += 1

    if problems:
        print(
            f"\n{problems} mismatch(es). Fix {TYPES_FILE}, or add a documented entry to "
            "ALLOWED_MISSING when the omission is deliberate."
        )
        return 1

    print(f"All {len(MIRRORS)} mirrored types match the API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
