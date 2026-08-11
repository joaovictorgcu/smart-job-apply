# LinkedIn Auto Apply

An assisted job application agent for LinkedIn Easy Apply. It searches for jobs, scores them
against your profile with an LLM, drafts screening answers and a cover letter, fills the
application form — and then **stops and waits for you to review and approve** before anything
is submitted.

> **Not affiliated with LinkedIn.** Browser automation is against LinkedIn's User Agreement and
> can get your account restricted. This project is a personal experiment in assisted automation
> and human-in-the-loop design. Use it at your own risk.

---

## Status: early development

The foundation is in place; the application does not run end-to-end yet.

**Implemented**

- Domain model — users, jobs, applications, automation runs, and the enums driving their
  lifecycles ([`models/`](backend/app/models/))
- API schemas for auth, profile, jobs, applications, automation, and stats
  ([`schemas/`](backend/app/schemas/))
- Provider-agnostic AI output contracts — scoring, screening answers, cover letters, token
  usage ([`ai/schemas.py`](backend/app/ai/schemas.py))
- Automation boundary — the `LinkedInService` protocol that isolates every Playwright detail
  behind typed dataclasses ([`automation/contracts.py`](backend/app/automation/contracts.py))
- Settings, JWT handling, at-rest encryption, async DB session, WebSocket manager, structured
  logging and audit events

**Not built yet**

- FastAPI app and routes (`main.py`, `api/`)
- Playwright implementation behind `LinkedInService`
- Claude client and prompt layer
- Alembic migrations
- Frontend (not started)
- Docker setup and tests

---

## Design

Two ideas shape the codebase.

**Assisted mode is not a setting, it's the contract.** `LinkedInService.fill_and_advance()` is
documented and typed to stop at the review step and never submit. `submit()` is a separate call
made only after explicit user approval. `ASSISTED_MODE_ONLY` defaults to `true`, and the
`AWAITING_REVIEW` application state is where every run is expected to pause.

**Playwright is quarantined.** The engine and services speak only in `SearchFilters`,
`JobPosting`, `FormQuestion`, `ApplicationDraft` — plain dataclasses with no browser types. When
LinkedIn changes its markup, the fix stays inside `automation/linkedin/` and `selectors.py`.

The same applies to the LLM: `JobScore`, `ScreeningAnswer`, and `CoverLetter` are the contract,
so swapping models or providers doesn't leak into the API layer.

## Guardrails

Conservative by default, adjustable per user:

| Guardrail | Default |
|---|---|
| Submit without explicit approval | Never (`ASSISTED_MODE_ONLY=true`) |
| Daily application cap | 15 |
| Minimum compatibility score | 70 |
| Delay between actions | 2.5–7s, randomized |
| Delay between applications | 45–120s, randomized |
| Working-hours window | 08:00–20:00 |
| Concurrent browser sessions | 1 |

Beyond the limits: LinkedIn session cookies are **encrypted at rest**, low-confidence AI answers
are flagged `needs_review` and surfaced in the UI rather than silently guessed, every application
carries a full event audit trail, a security checkpoint (CAPTCHA) moves the run to `BLOCKED` and
halts everything, and a kill switch stops a run mid-flight.

## How it works

```text
Search (Easy Apply only)
    ↓
Filters                    keywords, location, remote, date, seniority
    ↓
AI scoring                 0-100 + reasons + missing requirements
    ↓
Below min score → skipped
    ↓
Draft                      screening answers + cover letter + form filled
    ↓
AWAITING_REVIEW            ← you review, edit, approve or discard
    ↓
Submit
    ↓
History + audit trail
```

## Tech stack

- **Backend** — Python 3.11+, FastAPI, SQLAlchemy 2 (async), SQLite by default / PostgreSQL optional, Alembic
- **AI** — Claude API (`anthropic`), structured outputs
- **Automation** — Playwright
- **Frontend** — React, Vite, Tailwind CSS
- **Auth** — JWT (python-jose), bcrypt, Fernet-encrypted secrets at rest

## Getting started

> The backend has no entrypoint yet, so there is nothing to serve. These steps get you a working
> development environment.

**Requirements:** Python 3.11+ and an Anthropic API key. (Node.js 20+ once the frontend exists.)

```bash
git clone https://github.com/joaovictorgcu/smart-job-apply.git
cd smart-job-apply

pip install -e ".[dev]"
playwright install chromium
```

Create a `.env` in the project root:

```dotenv
# Required
ANTHROPIC_API_KEY=sk-ant-...
SECRET_KEY=<random string, signs JWTs>
ENCRYPTION_KEY=<random string, derives the at-rest encryption key>

# Optional
ANTHROPIC_MODEL=claude-opus-5
DATABASE_URL=                      # empty → SQLite at backend/data/app.db
HEADLESS=false                     # false so you can watch and intervene
DEFAULT_DAILY_CAP=15
DEFAULT_MIN_SCORE=70
CORS_ORIGINS=http://localhost:5173
```

Two notes on those keys. Leaving `SECRET_KEY` unset generates a random one per process, which
invalidates every session on restart. Changing `ENCRYPTION_KEY` makes already-stored credentials
permanently unreadable.

Generate both with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Project layout

```text
backend/
├── app/
│   ├── ai/              # provider-agnostic AI contracts
│   ├── auth/            # JWT, password hashing, at-rest encryption
│   ├── automation/      # LinkedInService protocol, errors
│   ├── database/        # async engine and session
│   ├── models/          # SQLAlchemy ORM + lifecycle enums
│   ├── observability/   # structured logging, audit, events
│   ├── schemas/         # Pydantic request/response models
│   ├── websocket/       # live run status
│   └── config.py
├── migrations/
└── tests/
```

## Development

```bash
pytest              # tests
ruff check .        # lint
mypy backend/app    # types
```

Ruff runs with `E, F, I, UP, B, SIM, ASYNC` at a 100-character line length; pytest is in
`asyncio_mode = "auto"`. Both are configured in [`pyproject.toml`](pyproject.toml).

## License

MIT.
