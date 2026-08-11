# Development

How to work on this codebase. For getting it running at all, see [installation.md](installation.md); for the
reasoning behind the structure, [architecture.md](architecture.md).

## Project layout

```text
.
├── backend/
│   ├── app/
│   │   ├── ai/                 # provider-agnostic AI contracts + the Claude client
│   │   │   └── schemas.py      #   JobScore, ScreeningAnswer, CoverLetter, JobAnalysis, AIUsage
│   │   ├── api/
│   │   │   └── routes/         # one module per resource, mounted under /api
│   │   ├── auth/
│   │   │   ├── crypto.py       # Fernet encrypt/decrypt for data at rest
│   │   │   └── security.py     # bcrypt hashing, JWT issue/decode
│   │   ├── automation/
│   │   │   ├── contracts.py    # SearchFilters, JobPosting, ..., LinkedInService protocol
│   │   │   ├── errors.py       # the error hierarchy
│   │   │   └── linkedin/       # the Playwright implementation + selectors.py
│   │   ├── database/
│   │   │   ├── base.py         # Base, TimestampMixin, UtcDateTime, utcnow()
│   │   │   └── session.py      # engine, get_session, session_scope, init_models
│   │   ├── models/             # SQLAlchemy ORM + lifecycle enums
│   │   ├── observability/
│   │   │   ├── audit.py        # record_event(), to_live_event()
│   │   │   ├── events.py       # EventName, Event, make_event
│   │   │   └── logger.py       # get_logger, bind_context, configure_logging
│   │   ├── schemas/            # Pydantic request/response models
│   │   ├── websocket/manager.py# the per-user broadcast singleton
│   │   ├── config.py           # Settings, get_settings()
│   │   └── main.py             # the FastAPI app
│   ├── migrations/             # Alembic
│   ├── tests/
│   └── data/                   # runtime state — gitignored
├── frontend/
│   └── src/
│       ├── api/                # typed HTTP client
│       ├── components/
│       ├── hooks/
│       ├── pages/
│       └── types/              # mirrors backend schemas, incl. events.ts
├── docker/
├── docs/
├── scripts/
└── pyproject.toml
```

## Commands

Every `make` target below is a thin wrapper over the raw command beside it. If a target is missing from your
checkout, the raw command always works.

| Task | Command |
|---|---|
| Run both processes | `make dev` |
| Backend only | `uvicorn app.main:app --reload --port 8000` |
| Frontend only | `cd frontend && npm run dev` |
| Tests | `pytest` |
| One test file | `pytest backend/tests/test_engine.py -v` |
| One test | `pytest backend/tests/test_engine.py::test_stops_at_review -v` |
| Lint | `ruff check .` |
| Lint with fixes | `ruff check --fix .` |
| Format | `ruff format .` |
| Types (backend) | `mypy backend/app` |
| Types (frontend) | `cd frontend && npm run typecheck` |
| Production frontend build | `cd frontend && npm run build` |
| Apply migrations | `cd backend && alembic upgrade head` |

On Windows, activate the venv first (`.\.venv\Scripts\Activate.ps1`); the commands themselves are identical.

## Code style

Configured in [`pyproject.toml`](../pyproject.toml) — read it rather than guessing.

- **Ruff**, line length 100, target `py311`, rules `E, F, I, UP, B, SIM, ASYNC`. `B008` is ignored because
  `Depends()` in a default argument is idiomatic FastAPI. `src = ["backend"]` is what lets isort recognize
  `app` as first-party; without it every `from app...` import gets sorted into the third-party block.
- **mypy** with the Pydantic plugin, `ignore_missing_imports = true`. Non-blocking in CI, because Playwright
  and SQLAlchemy typing produce noise that is not worth failing a build over. Do not let that become an
  excuse for untyped code.
- **English only** — identifiers, comments, docstrings, log messages, error messages, UI copy, docs. No
  exceptions.
- **Never `print()`.** Use the structured logger:

  ```python
  from app.observability import get_logger

  logger = get_logger(__name__)
  logger.info("Job scored", extra={"job_id": job.id, "action": "score", "status": "ok"})
  ```

  `extra` keys become top-level JSON fields. `bind_context(user_id=..., run_id=...)` attaches fields to every
  line emitted by the current task, which is what makes a run's logs greppable.
- **Comment the "why", not the "what".** A comment that restates the next line is noise; a comment
  explaining why `check_same_thread=False` is needed, or why a validator is a model validator rather than a
  field validator, earns its place. The existing code is the reference for the register.
- **Type everything at boundaries.** Route handlers, service functions, and the dataclasses in
  `contracts.py` are typed fully. Internal helpers can be looser.

## Adding a route

1. **Schema first**, in `app/schemas/`. Request and response models are the contract; write them before the
   handler. Reuse `ORMModel` for anything read from the ORM and `Page[T]` for lists.

2. **The handler**, in `app/api/routes/<resource>.py`:

   ```python
   from fastapi import APIRouter, Depends
   from sqlalchemy.ext.asyncio import AsyncSession

   from app.api.deps import get_current_user
   from app.database.session import get_session
   from app.models import User
   from app.observability import get_logger
   from app.schemas import WidgetRead

   router = APIRouter(prefix="/widgets", tags=["widgets"])
   logger = get_logger(__name__)


   @router.get("/{widget_id}", response_model=WidgetRead)
   async def get_widget(
       widget_id: int,
       user: User = Depends(get_current_user),
       session: AsyncSession = Depends(get_session),
   ) -> WidgetRead:
       ...
   ```

3. **Scope every query to the user.** Filter on `user_id` in the query itself, and return `404` — not `403` —
   when a row exists but belongs to someone else, so ids stay unenumerable.

4. **Register the router** in `app/main.py` under the `/api` prefix.

5. **Document it** in [api.md](api.md) and, if the frontend calls it, add the client function and its types.

6. **Test it** — the happy path, the unauthenticated case, and the wrong-user case.

Business logic does not belong in handlers. A handler validates input, calls a service, and shapes the
response.

## Adding a service

Services own the orchestration. They take a session and typed inputs, and they never touch FastAPI or
Playwright types.

```python
async def prepare_application(
    session: AsyncSession,
    *,
    user: User,
    job: Job,
    linkedin: LinkedInService,
    ai: AIClient,
) -> Application:
    ...
```

Passing `LinkedInService` and `AIClient` in as parameters — rather than constructing them inside — is what
makes the function testable with fakes. Keep it that way.

Every meaningful step calls `record_event()` and publishes the live event:

```python
from app.observability.audit import record_event, to_live_event
from app.websocket.manager import manager

event = await record_event(
    session,
    application_id=application.id,
    event_type=ApplicationEventType.FORM_STEP_COMPLETED,
    message="Step 2 of 4 completed",
    payload={"step": 2, "total": 4},
    run_id=run.id,
    job_id=job.id,
    user_id=user.id,
)
if (live := to_live_event(event, job_id=job.id)) is not None:
    await manager.publish(user.id, live)
```

The durable trail and the live feed come from one place, so they cannot drift.

## Adding a frontend page

1. Types in `src/types/`, mirroring the backend schema. `events.ts` must stay identical to
   `app/observability/events.py` — a mismatch there breaks the activity feed silently.
2. An API function in `src/api/`, returning the typed response.
3. A hook in `src/hooks/` for the data fetching and mutations.
4. The page component in `src/pages/`, and a route entry.
5. Handle the states that actually happen: loading, empty, error, and — for anything touching automation —
   `blocked`.

**Any UI that can submit an application must require a distinct, deliberate click**, with the letter and the
answers visible on screen at that moment. Do not add a "submit all" button, and do not make submit the
default action of a form.

## Touching the LinkedIn layer

Everything Playwright-specific lives in `app/automation/linkedin/`, and every selector lives in
`selectors.py`. Nothing outside that package imports Playwright.

When LinkedIn changes its markup:

1. Reproduce with a headed browser (below) and find what moved.
2. Fix the selector in `selectors.py`. Prefer stable attributes — `aria-label`, `data-*`,
   `role` — over generated class names, which change constantly.
3. If a *step* changed rather than a selector, the fix belongs in the `LinkedInService` implementation.
   `contracts.py` should not need to change; if it does, that is an interface change and needs a look at
   every caller.
4. Add or update the fake so the tests cover the new shape.

Two rules that are not negotiable:

- **`fill_and_advance()` must never submit.** It advances the form and stops at review. Submission lives
  only in `submit()`.
- **`SecurityCheckpointError` must never be caught and worked around.** Detect, raise, stop. No retry loop,
  no alternative selector, no attempt to read or solve a challenge.

## Testing

The whole suite runs offline. No LinkedIn account, no Anthropic key, no network.

```bash
pytest                     # everything
pytest -v                  # names
pytest -x                  # stop at the first failure
pytest --lf                # rerun last failures
pytest -k "review"         # by name
```

`pyproject.toml` sets `asyncio_mode = "auto"`, so `async def test_...` needs no decorator, and
`pythonpath = ["backend"]`, so `from app...` resolves in tests.

### The database fixture

Tests run against in-memory SQLite. Point `DATABASE_URL` at `sqlite+aiosqlite:///:memory:`, call
`init_models()`, and clear the settings cache — `get_settings` is `lru_cache`d, so a test that changes
environment variables must invalidate it:

```python
import pytest
from app.config import get_settings
from app.database.session import dispose_engine, init_models


@pytest.fixture
async def db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-tests-only")
    get_settings.cache_clear()
    await init_models()
    yield
    await dispose_engine()
    get_settings.cache_clear()
```

`dispose_engine()` at teardown matters: the module-level engine is a singleton and would otherwise leak
between tests.

### The LinkedIn fake

`LinkedInService` is a `runtime_checkable` `Protocol`, so a plain class satisfying the signatures works —
no inheritance, no mocking library. The fake returns canned dataclasses and records what it was asked to do:

```python
class FakeLinkedIn:
    """In-memory LinkedInService. Records calls; never opens a browser."""

    def __init__(self, *, jobs: list[JobPosting], questions: list[FormQuestion] | None = None):
        self._jobs = jobs
        self._questions = questions or []
        self.submitted: list[str] = []
        self.state = SessionState(browser_open=False, logged_in=False)

    async def start(self) -> SessionState:
        self.state = SessionState(browser_open=True, logged_in=True)
        return self.state

    async def stop(self) -> None:
        self.state = SessionState()

    async def get_state(self) -> SessionState:
        return self.state

    async def wait_for_login(self, timeout_seconds: int = 300) -> SessionState:
        return self.state

    async def search_jobs(self, filters: SearchFilters) -> list[JobPosting]:
        return self._jobs[: filters.max_results]

    async def fetch_job_details(self, external_id: str) -> JobPosting:
        return next(j for j in self._jobs if j.external_id == external_id)

    async def open_easy_apply(self, external_id: str) -> list[FormQuestion]:
        return self._questions

    async def fill_and_advance(
        self, answers: list[FormAnswer], *, cover_letter: str | None = None
    ) -> ApplicationDraft:
        # Mirrors the real contract: stops at review, never submits.
        return ApplicationDraft(
            job_external_id=self._jobs[0].external_id,
            answers=answers,
            total_steps=2,
            current_step=2,
            ready_to_submit=True,
        )

    async def submit(self) -> bool:
        self.submitted.append(self._jobs[0].external_id)
        return True

    async def discard(self) -> None: ...

    async def capture_screenshot(self, name: str) -> str | None:
        return None
```

Variants worth keeping around: one that raises `SecurityCheckpointError` from `search_jobs`, one that raises
`ElementNotFoundError`, and one whose `open_easy_apply` returns a question the answer bank cannot cover so
`ManualInputRequiredError` is exercised.

`assert isinstance(FakeLinkedIn(jobs=[]), LinkedInService)` gives you a cheap guard that the fake has not
drifted from the protocol.

### The AI fake

Same idea: return the Pydantic models from `app/ai/schemas.py` directly.

```python
class FakeAI:
    def __init__(self, *, score: int = 85, refuse: bool = False):
        self._score = score
        self._refuse = refuse

    async def score_job(self, *, job, profile) -> JobScore:
        return JobScore(
            score=self._score,
            reasons=["deterministic test score"],
            missing_requirements=[],
            recommend_apply=self._score >= 70,
        )

    async def write_cover_letter(self, *, job, profile) -> CoverLetter:
        return CoverLetter(content="Test letter.", language="en")

    async def answer_screening(self, *, questions, profile) -> ScreeningAnswerSet:
        return ScreeningAnswerSet(answers=[
            ScreeningAnswer(question=q.label, answer="42",
                            confidence=AnswerConfidence.LOW)  # -> needs_review becomes True
            for q in questions
        ])
```

Note the last one: constructing a `LOW`-confidence answer without setting `needs_review` is the fixture for
the model validator that flags it, so a test can assert the UI would surface it.

### What to test

| Layer | Cover |
|---|---|
| Schemas | Boundary values, cross-field validators, the `needs_review` auto-flag |
| Models | Enum round-trips, timezone-aware datetimes on both backends |
| Auth | Hash/verify, token issue/decode, expiry, the 72-byte bcrypt limit |
| Crypto | Round-trip, and that a changed key raises `DecryptionError` |
| Engine | Guard rails (cap, working hours, min score), checkpoint halt, kill switch, resume from `checkpoint` |
| **Approval invariant** | **That preparing never submits, and that submit requires `confirm: true`** |
| Routes | Happy path, `401`, and cross-user `404` |
| WebSocket | Per-user isolation, history replay, that a dead socket does not raise |

The approval-invariant tests are the ones that matter most. Assert on the fake:

```python
async def test_prepare_never_submits(db, fake_linkedin, fake_ai):
    await prepare_applications(job_ids=[job.id], confirmed=True, linkedin=fake_linkedin, ai=fake_ai)
    assert fake_linkedin.submitted == []          # nothing was sent
    assert application.status is ApplicationStatus.AWAITING_REVIEW
```

If that test ever fails, stop and fix it before anything else.

## Debugging the automation with a headed browser

The default is already a visible browser (`HEADLESS=false`), which is most of the battle. Beyond that:

**Slow it down** so you can watch what happens. Playwright's `slow_mo` adds a delay to every action:

```python
browser = await playwright.chromium.launch(headless=False, slow_mo=500)
```

**Use Playwright Inspector** to step through actions and try selectors live:

```bash
PWDEBUG=1 pytest backend/tests/test_linkedin.py -k easy_apply -s
```

```powershell
$env:PWDEBUG=1; pytest backend/tests/test_linkedin.py -k easy_apply -s
```

The Inspector's selector playground is the fastest way to find a replacement for a broken selector.

**Capture a trace** and inspect it after the fact — DOM snapshots, network, screenshots per action:

```python
await context.tracing.start(screenshots=True, snapshots=True, sources=True)
# ... run the flow ...
await context.tracing.stop(path="trace.zip")
```

```bash
playwright show-trace trace.zip
```

**Read the audit trail first.** Before reaching for the browser, check
`GET /api/applications/{id}/events` — the `payload` on each event usually names the field, the options, and
the step where things went wrong. `application_events` exists to make this the first step rather than the
last.

**Turn off JSON logs** while debugging locally; the human formatter is easier to scan:

```python
configure_logging(level="DEBUG", as_json=False)
```

**Under Docker**, the browser is on the virtual display: open <http://localhost:6080> and watch it there.
`docker compose logs -f backend` gives you the structured log alongside it.

## Migrations

Alembic lives in `backend/`, so run these from that directory.

```bash
cd backend

alembic revision --autogenerate -m "add widget table"   # generate
alembic upgrade head                                     # apply
alembic downgrade -1                                     # roll back one
alembic current                                          # where am I
alembic history --verbose                                # what exists
```

**Always read the generated migration before committing it.** Autogenerate is good at added tables and
columns and bad at renames — it will happily emit a drop-and-create that destroys data. Rewrite those as
`op.alter_column(..., new_column_name=...)` by hand.

`backend/migrations/versions` is excluded from ruff, so generated files are not reformatted into
inconsistency.

The workflow for a schema change:

1. Edit the model in `app/models/`.
2. `alembic revision --autogenerate -m "..."`.
3. Read the file. Fix the renames. Check that the downgrade actually reverses the upgrade.
4. `alembic upgrade head`, then `alembic downgrade -1`, then `alembic upgrade head` again — a migration that
   cannot round-trip is a migration you cannot back out of.
5. Update the schema section of [architecture.md](architecture.md) if a table's purpose changed.
6. Commit the model change and the migration together.

`init_models()` creates missing tables on startup as a convenience for people running without Alembic. It
does not alter existing tables, so it is not a substitute for a migration.

## CI

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on push and pull request:

- **backend**, matrixed over Python 3.11 and 3.12 — `ruff check`, `ruff format --check`, `mypy`
  (`continue-on-error`), `pytest`.
- **frontend** — `npm ci`, `npm run typecheck`, `npm run build`.

pip and npm caches are keyed on the lockfiles. No secrets are configured and none are needed, because the
tests are offline. If a test of yours needs a network call or an API key, it belongs behind a marker and
outside CI.

Run the same checks locally before pushing:

```bash
ruff check . && ruff format --check . && mypy backend/app && pytest
cd frontend && npm run typecheck && npm run build
```
