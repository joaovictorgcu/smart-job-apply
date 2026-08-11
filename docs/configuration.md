# Configuration

There are two layers of configuration, and they answer different questions.

| Layer | Where it lives | Scope | Changed by |
|---|---|---|---|
| **Settings** | `.env` file or environment variables | Process-wide | Editing `.env` and restarting |
| **UserSettings** | `user_settings` table in the database | Per user | The Settings page, or `PUT /api/settings` |

Settings are deployment concerns: keys, database URL, whether the browser is visible. UserSettings are
operating concerns: how many applications a day, how long to wait between actions, whether dry-run is on.
Several `DEFAULT_*` settings seed a new user's UserSettings row; after that, the per-user values win.

---

## Environment variables (`Settings`)

Defined in [`backend/app/config.py`](../backend/app/config.py). The env var name is the field name in
upper case — there is no prefix. Both `<repo root>/.env` and `backend/.env` are read, and real
environment variables take precedence over both.

### Application

| Variable | Type | Default | What it does |
|---|---|---|---|
| `APP_NAME` | string | `LinkedIn Auto Apply` | Display name used in the API title. |
| `ENVIRONMENT` | string | `development` | Free-form label for the deployment (`development`, `production`). |
| `DEBUG` | bool | `false` | Turns on SQLAlchemy statement echoing. Leave off outside local debugging — statements can contain your data. |

### Security

| Variable | Type | Default | What it does |
|---|---|---|---|
| `SECRET_KEY` | string | random per process | Signs JWTs. **Set this explicitly.** With the default, a new random key is generated on every start, so every login is invalidated by a restart. |
| `ENCRYPTION_KEY` | string | falls back to `SECRET_KEY` | Source material for the HKDF-derived Fernet key that encrypts LinkedIn session cookies at rest. **Changing it makes already-stored sessions permanently unreadable** — the fix is to reconnect LinkedIn, but you will have to. |
| `JWT_ALGORITHM` | string | `HS256` | JWT signing algorithm. No reason to change it. |
| `ACCESS_TOKEN_TTL_MINUTES` | int | `720` (12 h) | Access-token lifetime. Shorter means more re-logins; longer means a stolen token is useful for longer. |

Generate both keys with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### AI

| Variable | Type | Default | What it does |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | string | `""` | Your Anthropic API key. Empty means `Settings.ai_enabled` is `false`: scoring, cover letters, and screening suggestions are unavailable and `GET /api/ai/status` reports `configured: false`. Everything else still works; you fill the forms yourself. |
| `ANTHROPIC_MODEL` | string | `claude-opus-5` | The model used for scoring, cover letters, and screening answers. |
| `SCORING_EFFORT` | string | `low` | Reasoning effort for bulk scoring, where many jobs are graded and cost dominates. Cover-letter generation uses `high` regardless. Valid values are `low`, `medium`, `high`, `xhigh`, `max`. |

A user can override the model for their own account with `UserSettings.ai_model`; when that is null, `ANTHROPIC_MODEL` applies.

### Database

| Variable | Type | Default | What it does |
|---|---|---|---|
| `DATABASE_URL` | string | `""` | Empty means SQLite at `<DATA_DIR>/app.db` (WAL mode). Set to a full async URL to switch backends — for PostgreSQL, `postgresql+asyncpg://user:pass@host:5432/dbname`, which needs the `postgres` extra installed. |

The driver must be async: `sqlite+aiosqlite://…` or `postgresql+asyncpg://…`. A synchronous URL such as
`postgresql://…` will fail at engine creation.

### Automation

| Variable | Type | Default | What it does |
|---|---|---|---|
| `HEADLESS` | bool | `false` | Whether Chromium runs without a window. Keep it `false`: you need to see the browser to log into LinkedIn, and a visible browser is how you notice something going wrong. In Docker the browser runs inside a virtual display you reach over noVNC, so `false` is still correct there. |
| `MAX_CONCURRENT_SESSIONS` | int | `1` | Browser sessions allowed at once. |
| `ASSISTED_MODE_ONLY` | bool | `true` | The hard guarantee that nothing is submitted without an explicit, separate, user-confirmed action. |
| `DEFAULT_DAILY_CAP` | int | `15` | Seeds `UserSettings.daily_cap`. |
| `DEFAULT_MIN_SCORE` | int | `70` | Seeds `UserSettings.min_score`. |
| `DEFAULT_ACTION_DELAY_RANGE` | JSON `[float, float]` | `[2.5, 7.0]` | Seeds the per-action delay range, in seconds. |
| `DEFAULT_APPLY_DELAY_RANGE` | JSON `[float, float]` | `[45.0, 120.0]` | Seeds the between-applications delay range, in seconds. |
| `DEFAULT_WORKING_HOURS` | JSON `[int, int]` | `[8, 20]` | Seeds the working-hours window, as local hours. |

> **The three range settings must be written as JSON arrays in `.env`.** `DEFAULT_ACTION_DELAY_RANGE=[3, 9]`
> works; `DEFAULT_ACTION_DELAY_RANGE=3,9` raises `SettingsError: error parsing value for field
> "default_action_delay_range"` at import time. Pydantic-settings JSON-decodes complex fields before any
> validator runs, so the comma-splitting helper in `config.py` only applies to values passed in code and
> tests. The same is true of `CORS_ORIGINS`.

### Network

| Variable | Type | Default | What it does |
|---|---|---|---|
| `CORS_ORIGINS` | JSON `[string]` | `["http://localhost:5173", "http://127.0.0.1:5173"]` | Origins allowed to call the API. Must be a JSON array in `.env` — for example `CORS_ORIGINS=["http://localhost:5173"]`. Add your LAN address here if you open the dashboard from another machine. |
| `RATE_LIMIT_DEFAULT` | string | `120/minute` | slowapi rate limit for general endpoints. |
| `RATE_LIMIT_AUTH` | string | `10/minute` | Tighter limit on the auth endpoints, so `/api/auth/login` cannot be brute-forced. |

### Paths

| Variable | Type | Default | What it does |
|---|---|---|---|
| `DATA_DIR` | path | `backend/data` | Root for everything the app writes: `app.db`, `browser_profiles/`, `resumes/`, screenshots. Gitignored, and it contains live session cookies plus your CV — treat it as secret and back it up. |

### A working `.env`

```dotenv
# --- Required ---
ANTHROPIC_API_KEY=sk-ant-...
SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(48))">
ENCRYPTION_KEY=<a second, different value from the same command>

# --- Common ---
ANTHROPIC_MODEL=claude-opus-5
SCORING_EFFORT=low
DATABASE_URL=
HEADLESS=false
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]

# --- Guard-rail seeds (per-user values override these once a user exists) ---
DEFAULT_DAILY_CAP=15
DEFAULT_MIN_SCORE=70
DEFAULT_ACTION_DELAY_RANGE=[2.5, 7.0]
DEFAULT_APPLY_DELAY_RANGE=[45.0, 120.0]
DEFAULT_WORKING_HOURS=[8, 20]
```

---

## Per-user settings (`UserSettings`)

Read with `GET /api/settings`, changed with `PUT /api/settings`. Bounds below are enforced by
[`UserSettingsUpdate`](../backend/app/schemas/user.py); a value outside them is a `422`, not a silent clamp.

### Guard rails

Loosening these is the one part of configuration that carries real risk, so each row says what you are
trading away.

| Field | Type | Default | Range | What it does — and the risk of loosening it |
|---|---|---|---|---|
| `daily_cap` | int | `15` | 1–50 | Maximum applications submitted per day. The hard ceiling is 50 because above that the volume stops resembling a person job-hunting and starts resembling a script. Raising it is the single change most likely to draw attention to your account. |
| `min_score` | int | `70` | 0–100 | Minimum AI fit score before a job is eligible for an application. Lowering it means applying to jobs you are a weaker match for: more employer-side noise, more screening questions the AI cannot answer confidently, and a worse response rate. |
| `action_delay_min` | float | `2.5` | 0.5–60 | Lower bound of the randomized pause between individual page actions. Below roughly two seconds, click-to-click timing is faster than a human reading the page. |
| `action_delay_max` | float | `7.0` | 0.5–120 | Upper bound of that pause. Must be ≥ `action_delay_min`. The *range* matters as much as the values: a fixed delay is a fingerprint, a randomized one is not. |
| `apply_delay_min` | float | `45.0` | 5–600 | Lower bound of the pause between whole applications. Set to 5 s and fifteen applications land inside two minutes — the clearest possible automated pattern. |
| `apply_delay_max` | float | `120.0` | 5–1800 | Upper bound of that pause. Must be ≥ `apply_delay_min`. |
| `working_hour_start` | int | `8` | 0–23 | First local hour in which the automation will act. |
| `working_hour_end` | int | `20` | 1–24 | Last local hour. Must be greater than `working_hour_start`. Opening the window to 0–24 produces 3 a.m. activity every day, which no real job search looks like. |
| `require_manual_approval` | bool | `true` | — | Requires explicit approval before submission. Along with `ASSISTED_MODE_ONLY`, this is the human-in-the-loop guarantee. Do not turn it off; nothing in the project needs it off. |
| `dry_run` | bool | `true` | — | While true, the engine performs the whole flow — search, score, open the form, fill it, stop at review — and **never submits**. The only reason to turn it off is that you have watched a few dry runs and are ready to submit real applications. Turn it off deliberately, and turn it back on when you are done. |

### AI preferences

| Field | Type | Default | What it does |
|---|---|---|---|
| `ai_model` | string \| null | `null` | Overrides `ANTHROPIC_MODEL` for this user. Null uses the environment value. Max 100 chars. |
| `cover_letter_tone` | string | `profissional` | Tone hint passed to the cover-letter prompt. Any short descriptor works — `professional`, `direct`, `warm`. Max 50 chars. |
| `content_language` | string | `job` | `job` writes the letter and answers in the language detected from the posting. Pin it to a tag such as `en` or `pt-BR` to always use that language. Max 20 chars. |
| `generate_cover_letter` | bool | `true` | Whether to draft a cover letter during preparation. Turn it off if you would rather write your own, or to save tokens. |

> `cover_letter_tone` and `content_language` default to values that read as Portuguese
> (`profissional`, `pt-BR` inside `CoverLetter`). They are free-form strings passed to the model, not
> enumerations — set them to whatever you want.

### Example

```bash
curl -X PUT http://localhost:8000/api/settings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"daily_cap": 10, "min_score": 75, "content_language": "en", "dry_run": true}'
```

---

## Which knob do I actually want?

| Goal | Change |
|---|---|
| Watch the whole flow without sending anything | `dry_run: true` (the default) |
| Actually submit applications | `dry_run: false`, then approve each one individually |
| Fewer, better-matched applications | Raise `min_score`, lower `daily_cap` |
| Look less like a script | Widen `action_delay_*` and `apply_delay_*`; narrow the working-hours window |
| Spend less on the API | `SCORING_EFFORT=low`, `generate_cover_letter: false`, lower `Search.max_results` |
| Write applications in English regardless of the posting | `content_language: "en"` |
| Move off SQLite | `DATABASE_URL=postgresql+asyncpg://…` plus `pip install -e ".[postgres]"` |
| Stop losing logins on restart | Set `SECRET_KEY` explicitly |
