"""Everything this account holds, in one file it can take elsewhere.

The companion to deleting the account. A product that asks for a CV, keeps a
year of applications and scores every posting against them owes the person both
doors: the one out, and the one that lets them leave with what they put in.

Two decisions shape the module, and they pull against each other on purpose.

**Completeness is automatic.** Rows are dumped column by column from the mapper
rather than from a hand-written field list. A hand-written list rots: a column
added next year is simply missing from the export, silently, and nobody notices
because nothing fails. Deriving it means new columns are exported the day they
exist.

**Secrecy is manual.** `NEVER_EXPORT` names every column that must not leave,
and it is the *only* thing standing between an automatic dump and a file with a
password hash in it. So it is backed by a test rather than by care: any column
whose name looks like a credential must appear there, and the three that exist
today are asserted by name. A new secret column is a failing test, not a leak.

What a JSON file cannot carry is the uploaded PDF and the rendered
per-application PDFs. Those are named in `not_included` with where to fetch
them, because an export that quietly omits them would read as complete.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import Select, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base, utcnow
from app.models import (
    AIAnalysis,
    Application,
    ApplicationEvent,
    ApplicationResume,
    AuditEvent,
    AutomationRun,
    Experience,
    InterviewStage,
    Job,
    JobPreferences,
    JobScore,
    LinkedInAccount,
    Profile,
    Search,
    TailoredResume,
    User,
    UserSettings,
)
from app.observability import get_logger

logger = get_logger(__name__)

#: Bumped when the shape changes in a way a reader would have to handle.
FORMAT_VERSION = 1

#: Columns that must never appear in an export, per table.
#:
#: Each is a credential rather than content: the password hash protects this
#: account, the storage state *is* the LinkedIn session, and the AI key spends
#: the owner's quota. Exporting any of them would turn a portability feature
#: into a way to walk off with working credentials — including for whoever
#: found the file afterwards.
NEVER_EXPORT: dict[str, frozenset[str]] = {
    "users": frozenset({"hashed_password"}),
    "linkedin_accounts": frozenset({"encrypted_storage_state"}),
    "user_settings": frozenset({"ai_api_key_encrypted"}),
}

#: What a credential tends to be called. Not a filter — the filter is
#: `NEVER_EXPORT` — but the pattern a test uses to insist that a column named
#: like a secret was classified by a human before it could be exported.
SECRET_COLUMN_PATTERN = re.compile(
    r"password|passwd|secret|token|encrypted|api_key|apikey|credential|hash", re.IGNORECASE
)

#: Columns the pattern above flags that a person has looked at and cleared,
#: written as `table.column`.
#:
#: The escape hatch is the point rather than a weakness: a heuristic that cannot
#: be overruled gets loosened instead, and a loosened pattern stops catching the
#: real thing. Each entry here is a decision somebody made and left behind.
REVIEWED_NOT_SECRET: frozenset[str] = frozenset(
    {
        # Token *counts*, for cost accounting. Nothing to authenticate with.
        "ai_analyses.input_tokens",
        "ai_analyses.output_tokens",
    }
)


@dataclass(frozen=True)
class _Section:
    """One table in the export, and how to find this account's rows in it."""

    key: str
    model: type[Base]
    #: `application_events` is the one table with no `user_id` of its own; it is
    #: reached through the application it belongs to. Everything else is a
    #: direct filter, which is also what makes the scoping auditable at a glance.
    via_application: bool = False


SECTIONS: tuple[_Section, ...] = (
    _Section("profile", Profile),
    _Section("experiences", Experience),
    _Section("settings", UserSettings),
    _Section("preferences", JobPreferences),
    _Section("linkedin_account", LinkedInAccount),
    _Section("searches", Search),
    _Section("jobs", Job),
    _Section("job_scores", JobScore),
    _Section("applications", Application),
    _Section("application_events", ApplicationEvent, via_application=True),
    _Section("application_resumes", ApplicationResume),
    _Section("tailored_resumes", TailoredResume),
    _Section("interview_stages", InterviewStage),
    _Section("ai_analyses", AIAnalysis),
    _Section("automation_runs", AutomationRun),
    _Section("audit_events", AuditEvent),
)

#: Said in the file itself, because an export that omits something without
#: saying so reads as complete.
NOT_INCLUDED: tuple[str, ...] = (
    "The resume file you uploaded. Download it from the profile screen.",
    "The rendered PDF of each application's resume. Download each from its "
    "application screen, or from GET /api/applications/{id}/resume.pdf.",
    "Your password, your LinkedIn session cookies and your AI API key. These "
    "are credentials, not content: an exported copy would be a working key in "
    "a file, for you and for anyone who later found it.",
)


def _jsonable(value: Any) -> Any:
    """A column value as JSON, without losing what it meant.

    Timestamps keep their timezone by going out as ISO 8601, and a `StrEnum`
    goes out as the same lowercase string the API already uses — so a reader of
    this file sees `awaiting_review`, exactly as the API documentation spells it.
    """
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, bytes):
        # Nothing in the schema stores bytes today; if something starts to, a
        # length is a truthful placeholder and a base64 blob in a "portability"
        # file usually is not what the reader wanted.
        return f"<{len(value)} bytes>"
    return str(value)


def exportable_columns(model: type[Base]) -> list[str]:
    """Every column of `model` except the ones deliberately withheld."""
    table = str(model.__tablename__)
    withheld = NEVER_EXPORT.get(table, frozenset())
    return [column.key for column in inspect(model).columns if column.key not in withheld]


def _row_to_dict(model: type[Base], row: Base) -> dict[str, Any]:
    return {name: _jsonable(getattr(row, name, None)) for name in exportable_columns(model)}


def _scoped(section: _Section, user_id: int) -> Select[Any]:
    """Rows of one table belonging to one account, newest last where ordered.

    Ordered by primary key rather than by date: two exports of an unchanged
    account should produce the same file, and `created_at` ties are common when
    a run writes several rows in the same transaction.
    """
    model = section.model
    if section.via_application:
        return (
            select(model)
            .join(Application, Application.id == model.application_id)  # type: ignore[attr-defined]
            .where(Application.user_id == user_id)
            .order_by(model.id)  # type: ignore[attr-defined]
        )
    return select(model).where(model.user_id == user_id).order_by(model.id)  # type: ignore[attr-defined]


async def build_export(session: AsyncSession, user: User) -> dict[str, Any]:
    """The whole account as a plain dict, ready to be serialised.

    Read in one pass and held in memory. An account is one person's year of job
    hunting — thousands of rows at the outside — and a streaming writer would
    trade a real simplification for a saving nobody here can measure. If that
    stops being true, this is the function that changes, and the endpoint and
    the file format do not.
    """
    data: dict[str, list[dict[str, Any]]] = {}
    for section in SECTIONS:
        result = await session.execute(_scoped(section, user.id))
        data[section.key] = [_row_to_dict(section.model, row) for row in result.scalars().all()]

    account = _row_to_dict(User, user)
    counts = {key: len(rows) for key, rows in data.items()}

    logger.info(
        "Account exported.",
        extra={
            "action": "account.export",
            "status": "ok",
            "user_id": user.id,
            "rows": sum(counts.values()),
        },
    )

    return {
        "format_version": FORMAT_VERSION,
        "exported_at": utcnow().isoformat(),
        "account": account,
        "counts": counts,
        "not_included": list(NOT_INCLUDED),
        "data": data,
    }


def to_json(export: dict[str, Any]) -> str:
    """Indented and UTF-8 as written, because a person opens this file.

    `ensure_ascii=False` matters more than it looks: a Brazilian resume is full
    of accented words, and `Jo\\u00e3o` in a file someone opens to check their
    own data is a worse answer than the two extra bytes.
    """
    return json.dumps(export, indent=2, ensure_ascii=False, sort_keys=False)


def filename_for(user: User, *, moment: datetime | None = None) -> str:
    """A name that says whose data it is and when it was taken."""
    stamp = (moment or utcnow()).date().isoformat()
    return f"smart-job-apply-{user.id}-{stamp}.json"
