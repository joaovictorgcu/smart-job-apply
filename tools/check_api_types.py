#!/usr/bin/env python3
"""Do the hand-written mirrors of this API still describe the API?

Two claims, neither of which anything enforced before this file existed:
`frontend/src/types/api.ts` mirrors the Pydantic schemas, and `docs/api.md`
documents routes that exist.

The types file says so itself: "Source of truth: backend/app/schemas/*.py ...
Field names must match byte-for-byte." A field added to a model and forgotten
there fails no build, no test and no type check — it simply becomes a value the
frontend is told does not exist. `JobRead.is_stale`, `deadline` and `expired_at`
were exactly that: the backend refuses to prepare a stale posting, and the job
card could not say so because its type denied the field.

The docs go stale the same way and cost more: three sections described
`/api/applications/{id}/resume` long after the real endpoints moved, so sixty-
four lines told a reader to call something that answers 404.

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
    0 when every mirrored type matches and every documented route exists.
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
API_DOC = Path("docs") / "api.md"

# Headings in `api.md` that name something other than a REST path. The WebSocket
# is documented with the query string a client actually opens it with.
DOC_EXEMPT: frozenset[str] = frozenset({"GET /api/ws"})

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


def load_openapi(root: Path) -> dict:
    """The live OpenAPI document, built from the real routes and models."""
    sys.path.insert(0, str(root / "backend"))
    from app.main import create_app

    return create_app().openapi()


_DOC_HEADING = re.compile(r"^### `(GET|POST|PUT|PATCH|DELETE) (/api/[^`]+)`", re.M)
_PATH_PARAM = re.compile(r"\{[^}]+\}")


def _normalise(method: str, path: str) -> str:
    """One spelling for a route, whichever side it came from.

    The schema spells methods lowercase and names its own parameters
    (`{job_id}`); the docs spell them uppercase and shorten to `{id}`. Both
    differences have to collapse here or every route looks like a mismatch.
    """
    return f"{method.upper()} {_PATH_PARAM.sub('{}', path.split('?')[0].rstrip('/'))}"


def check_documented_routes(root: Path, openapi: dict) -> int:
    """Every route `api.md` documents must exist.

    Three whole sections described `/api/applications/{id}/resume` — a GET, a
    POST and a PATCH — after the real endpoints moved to `/api/resumes/...`.
    Sixty-four lines telling a reader to call something that answers 404. Docs
    do not fail a build on their own, which is the entire reason this is here.

    Deliberately one-directional: an undocumented route is a gap someone can
    close later, but a documented route that does not exist is a false
    instruction, and those are worth failing over.
    """
    doc_path = root / API_DOC
    if not doc_path.is_file():
        print(f"MISSING  {API_DOC}")
        return 1

    live = {
        _normalise(method, path)
        for path, operations in openapi.get("paths", {}).items()
        for method in operations
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }

    problems = 0
    for match in _DOC_HEADING.finditer(doc_path.read_text(encoding="utf-8")):
        entry = _normalise(match.group(1), match.group(2))
        if entry in DOC_EXEMPT or entry in live:
            continue
        print(
            f"PHANTOM  {API_DOC} documents `{match.group(1)} {match.group(2)}`, "
            "which the app does not serve — a reader following it gets a 404."
        )
        problems += 1
    return problems


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    root = Path(arguments[0]).resolve() if arguments else Path(__file__).resolve().parents[1]

    types_path = root / TYPES_FILE
    if not types_path.is_file():
        print(f"MISSING  {TYPES_FILE}")
        return 1

    own, parents = parse_interfaces(types_path.read_text(encoding="utf-8"))
    openapi = load_openapi(root)
    schemas = openapi["components"]["schemas"]

    problems = check_documented_routes(root, openapi)
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
            f"\n{problems} mismatch(es). A PHANTOM line means {API_DOC} describes a route "
            f"that does not exist; a DRIFT line means {TYPES_FILE} and the schema "
            "disagree. A deliberate omission goes in ALLOWED_MISSING with its reason."
        )
        return 1

    print(f"All {len(MIRRORS)} mirrored types match the API, and every documented route exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
