# Development

How to work on this codebase. For getting it running at all, see [installation.md](installation.md); for the
reasoning behind the structure, [architecture.md](architecture.md).

## Project layout

```text
.
├── backend/
│   ├── alembic.ini             # Alembic config — migration commands run from backend/
│   ├── app/
│   │   ├── ai/
│   │   │   ├── client.py       # the Anthropic client wrapper
│   │   │   ├── scoring.py      # scoring orchestration
│   │   │   ├── prompts/        # scoring.py, cover_letter.py, screening.py
│   │   │   └── schemas.py      # JobScore, ScreeningAnswer, CoverLetter, JobAnalysis, AIUsage
│   │   ├── api/
│   │   │   ├── deps.py         # SessionDep, CurrentUser, LimitDep, OffsetDep, limiter
│   │   │   ├── errors.py       # exception handlers
│   │   │   └── routes/         # one module per resource, mounted under /api
│   │   ├── auth/
│   │   │   ├── crypto.py       # Fernet encrypt/decrypt for data at rest
│   │   │   ├── dependencies.py # get_current_user, get_current_user_ws
│   │   │   └── security.py     # bcrypt hashing, JWT issue/decode
│   │   ├── automation/
│   │   │   ├── contracts.py    # SearchFilters, JobPosting, ..., LinkedInService protocol
│   │   │   ├── errors.py       # the error hierarchy
│   │   │   ├── engine.py       # orchestration — imports no Playwright
│   │   │   ├── throttle.py     # delays, daily cap, working hours
│   │   │   ├── browser.py      # Playwright launch and lifecycle
│   │   │   ├── selectors.py    # EVERY CSS selector, in one file
│   │   │   └── linkedin/       # service.py, search.py, job.py, apply.py
│   │   ├── services/           # application, automation, job, search, stats, user
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
│   ├── migrations/             # env.py + versions/
│   ├── tests/                  # unit/ api/ automation/ integration/ fixtures/
│   └── data/                   # runtime state — gitignored
├── frontend/
│   └── src/
│       ├── components/         # AppShell, CheckpointBanner, KillSwitchButton, ...
│       ├── hooks/              # useApi, useAuth, useEvents
│       ├── lib/                # format, theme, utils
│       ├── pages/
│       ├── services/           # typed HTTP client — client.ts + one module per resource
│       └── types/              # api.ts, events.ts (mirrors the backend)
├── docker/                     # Dockerfile, entrypoint.sh, supervisord.conf
├── docs/
├── scripts/                    # setup.sh, setup.ps1, dev.sh, create_user.py
├── Makefile
├── docker-compose.yml
└── pyproject.toml
```

## Commands

`make help` lists every target, and the Makefile header gives the PowerShell equivalent of each one for
Windows without WSL. The raw command is in the third column when you need it.

| Task | Target | Raw command |
|---|---|---|
| First-time setup | `make install` | `bash scripts/setup.sh` |
| Run both processes | `make dev` | `bash scripts/dev.sh` |
| Backend only | `make dev-backend` | `.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend --port 8000` |
| Frontend only | `make dev-frontend` | `cd frontend && npm run dev` |
| Tests | `make test` | `pytest` |
| Lint | `make lint` | `ruff check .` |
| Format + safe fixes | `make format` | `ruff format . && ruff check . --fix` |
| Types (backend) | `make typecheck` | `mypy backend/app` |
| Types (frontend) | — | `cd frontend && npm run typecheck` |
| Frontend lint | — | `cd frontend && npm run lint` |
| Production build | `make build` | `cd frontend && npm run build` |
| Apply migrations | `make migrate` | `cd backend && alembic upgrade head` |
| New migration | `make migration m="add x"` | `cd backend && alembic revision --autogenerate -m "add x"` |
| Create an account | `make user` | `python scripts/create_user.py` |
| Docker up / down / logs | `make docker-up` / `-down` / `-logs` | the same `docker compose` commands |
| Clean caches and venv | `make clean` | — |

Narrower test selections:

```bash
pytest backend/tests/automation/test_kill_switch.py -v
pytest backend/tests/automation/test_engine_dry_run.py::test_dry_run_never_submits -v
pytest -k "checkpoint or kill_switch"
```

`make dev` honors `BACKEND_PORT` and `FRONTEND_PORT`, and stops both processes if either one dies — so a
crashed backend is not hidden behind a still-running Vite server.

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

2. **The handler**, in `app/api/routes/<resource>.py`. Use the annotated aliases from `app.api.deps` rather
   than spelling out `Depends(...)`; every existing route does:

   ```python
   from app.api.deps import CurrentUser, LimitDep, OffsetDep, SessionDep
   from app.schemas.common import Page
   from app.schemas.widget import WidgetRead
   from app.services import widget_service

   router = APIRouter(prefix="/widgets", tags=["widgets"])


   @router.get("", response_model=Page[WidgetRead])
   async def list_widgets(
       user: CurrentUser,
       session: SessionDep,
       limit: LimitDep = 50,
       offset: OffsetDep = 0,
   ) -> Page[WidgetRead]:
       """One-line docstring — it becomes the OpenAPI summary."""
       widgets, total = await widget_service.list_widgets(
           session, user_id=user.id, limit=limit, offset=offset
       )
       return Page(items=[WidgetRead.model_validate(w) for w in widgets], total=total,
                   limit=limit, offset=offset)
   ```

   `LimitDep` and `OffsetDep` carry the pagination bounds (1–200 and ≥ 0), so every list endpoint validates
   them the same way. Rate-limited routes take `request: Request` and the `@limiter.limit(...)` decorator —
   see `routes/auth.py`.

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

1. Types in `src/types/api.ts`, mirroring the backend schema. `src/types/events.ts` must stay identical to
   `app/observability/events.py` — a mismatch there breaks the activity feed silently.
2. A service function in `src/services/<resource>.ts`, built on the shared `client.ts`, returning the typed
   response.
3. A hook in `src/hooks/` for the fetching and mutations (React Query is already wired up).
4. The page component in `src/pages/`, plus a route entry in `App.tsx` behind `ProtectedRoute`.
5. Handle the states that actually happen: loading (`Spinner`), empty (`EmptyState`), error (`Toast`), and —
   for anything touching automation — `blocked` (`CheckpointBanner`).

**Any UI that can submit an application must require a distinct, deliberate click**, with the letter and the
answers visible on screen at that moment. Do not add a "submit all" button, and do not make submit the
default action of a form.

## Touching the LinkedIn layer

Playwright lives in exactly two places: `app/automation/browser.py` (launch and lifecycle) and
`app/automation/linkedin/` (`service.py` implements the protocol; `search.py`, `job.py`, and `apply.py` do
the work). Every selector lives in `app/automation/selectors.py`. Nothing else imports Playwright.

When LinkedIn changes its markup:

1. Reproduce with a headed browser (below) and find what moved.
2. Fix the selector in `app/automation/selectors.py`. Prefer stable attributes — `aria-label`, `data-*`,
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

The whole suite runs offline and enforces it: an autouse fixture blocks socket access, so a test that
reaches for the network fails rather than quietly depending on it. No LinkedIn account, no Anthropic key, no
browser.

```bash
pytest                     # everything
pytest -x                  # stop at the first failure
pytest --lf                # rerun last failures
pytest -k "checkpoint"     # by name
```

Tests are grouped by what they exercise: `tests/unit/` (schemas, crypto, security, throttle, scoring),
`tests/api/` (routes, auth, cross-user isolation), `tests/automation/` (dry run, kill switch, checkpoint
detection), and `tests/integration/` (the whole application flow, dedup, stats).

### Fixtures

`backend/tests/conftest.py` does the heavy lifting, and several fixtures are `autouse` — you get them
whether you ask or not:

| Fixture | Scope | What it does |
|---|---|---|
| `test_settings` | session, autouse | Points `Settings` at a temp `DATA_DIR` and deterministic keys, and clears the `get_settings` cache. `get_settings` is `lru_cache`d, so anything that changes the environment must invalidate it |
| `block_network` | autouse | Fails the test if it tries to open a socket. This is what keeps the suite honest about being offline |
| `cap_sleep` | autouse | Caps `asyncio.sleep`, so the randomized 45–120 s apply delays do not make the suite take an hour |
| `sleep_spy` | — | Records the durations that *would* have been slept, so guard-rail timing is assertable |
| `wire_fakes` | autouse | Injects `FakeLinkedInService` and `FakeAIClient` in place of the real adapters |
| `fake_linkedin` / `fake_ai` | — | The fake instances, for configuring and asserting against |
| `engine` / `sessionmaker` / `session` | — | In-memory SQLite with the schema created, disposed at teardown so the module-level engine does not leak |
| `user` / `other_user` | — | Two accounts — `other_user` is how cross-user isolation gets tested |
| `auth_headers` / `other_auth_headers` | — | Ready-made `Authorization` headers for each |
| `app` / `client` | — | The FastAPI app with the test sessionmaker wired in, and an `httpx.AsyncClient` against it |

`pyproject.toml` sets `asyncio_mode = "auto"`, so `async def test_...` needs no decorator, and
`pythonpath = ["backend"]`, so `from app...` resolves.

Build rows with the factories in `backend/tests/fixtures/factories.py` — `create_user`, `create_search`,
`create_job`, `create_application`, `create_run`, `create_analysis`, plus `make_job_posting`,
`make_form_question`, `make_profile_context`, and `days_ago` for time-relative data.

### The LinkedIn fake

`LinkedInService` is a `runtime_checkable` `Protocol`, so
[`FakeLinkedInService`](../backend/tests/fixtures/fake_linkedin.py) just satisfies the signatures — no
inheritance, no mocking library, no browser. It is a dataclass you configure by field and then assert
against.

Configure the scenario:

| Field | Effect |
|---|---|
| `postings` / `job_count` | The postings `search_jobs()` returns |
| `questions` / `unanswered` / `total_steps` | The shape of the Easy Apply form |
| `checkpoint_on` / `checkpoint_after` / `checkpoint_reason` | Raise `SecurityCheckpointError` from a chosen call, optionally after N successes |
| `error_on` / `error` | Raise any other error from a chosen call |
| `logged_in` / `browser_open` | Session state |
| `already_applied_ids` / `no_easy_apply_ids` | Trigger `AlreadyAppliedError` / `EasyApplyUnavailableError` |

Then assert on what happened:

| Field | Records |
|---|---|
| **`submitted`** | **Job ids that reached `submit()`. This is the assertion that guards assisted mode** |
| `calls` | Every method called, in order |
| `opened` | Jobs whose Easy Apply modal was opened |
| `filled` / `cover_letters` | The answers and letters passed to `fill_and_advance()` |
| `screenshots` | Capture requests |

The module also ships `FakePage`, `FakeLocator`, and `FakeBrowser` — including a `checkpoint()` helper that
serves the real challenge text in both English and Portuguese — so the *detector* itself can be tested
without a browser. `make_postings(count)` generates postings in bulk.

A useful guard, in case the fake drifts from the protocol:

```python
assert isinstance(FakeLinkedInService(), LinkedInService)
```

### The AI fake

[`FakeAIClient`](../backend/tests/fixtures/fake_ai.py) returns the real Pydantic models from
`app/ai/schemas.py` — `JobScore`, `CoverLetter`, `ScreeningAnswer`, `AIUsage` — deterministically. It
exposes `score_job()`, `write_cover_letter()`, and `answer_questions()`, plus `is_configured()`,
`call_count(name)` and `usage()` for asserting how often the model was called and what it reported. It can
be configured to return a chosen score, a chosen `AnswerConfidence`, or to raise `FakeAIError` so the
refusal-to-manual-entry path gets exercised.

Setting the confidence to `LOW` is how you test the flagging invariant: `ScreeningAnswer`'s model validator
sets `needs_review = True` for a low-confidence answer even when the field was left at its default.

### What to test

| Layer | Cover |
|---|---|
| Schemas | Boundary values, cross-field validators, the `needs_review` auto-flag |
| Models | Enum round-trips, timezone-aware datetimes on both backends |
| Auth | Hash/verify, token issue/decode, expiry, the 72-byte bcrypt limit |
| Crypto | Round-trip, and that a changed key raises `DecryptionError` |
| Throttle | Daily cap, working hours, delay ranges (assert via `sleep_spy`) |
| Engine | Checkpoint halt, kill switch, resume from `checkpoint`, dedup |
| **Approval invariant** | **That preparing never submits, and that submit requires `confirm: true`** |
| Routes | Happy path, `401`, and cross-user `404` (that is what `other_auth_headers` is for) |
| WebSocket | Per-user isolation, history replay, that a dead socket does not raise |

The approval-invariant tests matter most, and they are the reason `FakeLinkedInService.submitted` exists.
`backend/tests/automation/test_engine_dry_run.py` and
`backend/tests/integration/test_application_flow.py` are the ones to read first — and if either ever fails,
stop and fix it before anything else.

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

`alembic.ini` lives in `backend/`, so run these from that directory — or use `make migrate` and
`make migration m="..."` from the repository root, which `cd` for you.

```bash
cd backend

alembic revision --autogenerate -m "add widget table"   # generate
alembic upgrade head                                     # apply
alembic downgrade -1                                     # roll back one
alembic current                                          # where am I
alembic history --verbose                                # what exists
```

In Docker there is nothing to run: the entrypoint applies `alembic upgrade head` on every boot.

**Always read the generated migration before committing it.** Autogenerate is good at added tables and
columns and bad at renames — it will happily emit a drop-and-create that destroys data. Rewrite those as
`op.alter_column(..., new_column_name=...)` by hand.

`backend/migrations/versions` is excluded from ruff, so generated files are not reformatted into
inconsistency.

The workflow for a schema change:

1. Edit the model in `app/models/`.
2. `make migration m="..."`.
3. Read the file. Fix the renames. Check that the downgrade actually reverses the upgrade.
4. `alembic upgrade head`, then `alembic downgrade -1`, then `alembic upgrade head` again — a migration that
   cannot round-trip is a migration you cannot back out of.
5. Update the schema section of [architecture.md](architecture.md) if a table's purpose changed.
6. Commit the model change and the migration together.

`init_models()` creates missing tables on startup as a convenience for people running without Alembic. It
does not alter existing tables, so it is not a substitute for a migration.

## CI

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on push and pull request:

- **backend**, matrixed over Python 3.11 and 3.12 — `ruff check`, `mypy` (`continue-on-error`), `pytest`.
- **frontend** — `npm ci`, `npm run typecheck`, `npm run build`.

pip and npm caches are keyed on the lockfiles, and `concurrency` cancels superseded runs on a branch.
Chromium is deliberately **not** installed in CI: the suite runs against the fakes, so downloading a browser
would add minutes for nothing.

No secrets are configured and none are needed, because the tests are offline. If a test of yours needs a
network call or an API key, it belongs behind a marker and outside CI.

Run the same checks locally before pushing:

```bash
make lint && make typecheck && make test
cd frontend && npm run typecheck && npm run build
```
