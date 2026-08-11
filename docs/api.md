# API reference

Every route is under `/api`. Request and response bodies are JSON unless noted.

> **Live docs beat this page.** The running app serves interactive OpenAPI at
> **<http://localhost:8000/docs>** (and the raw schema at `/openapi.json`), generated from the actual
> Pydantic models. Use it to try calls and to confirm exact field types; use this page for the shape of the
> whole surface and the reasoning behind it.

## Authentication

All routes except `POST /api/auth/register`, `POST /api/auth/login`, and `GET /api/health` require a bearer
token:

```
Authorization: Bearer <access_token>
```

Get one from `/api/auth/login`. It is a JWT signed with `SECRET_KEY`, valid for
`ACCESS_TOKEN_TTL_MINUTES` (12 hours by default). There is no refresh token — log in again when it expires.

Every query is scoped to the authenticated user. Requesting another user's job or application returns `404`,
not `403`, so ids are not enumerable.

## Conventions

| | |
|---|---|
| Timestamps | ISO 8601, UTC, timezone-aware — `2026-08-11T14:23:05+00:00` |
| Enums | lower-case snake_case strings (`awaiting_review`, `job_found`) |
| Pagination | `?limit=&offset=` on list endpoints, wrapped in `Page` |
| Rate limits | `120/minute` by default, `10/minute` on auth routes |

`Page<T>`:

```json
{ "items": [], "total": 0, "limit": 50, "offset": 0 }
```

`Message`:

```json
{ "detail": "..." }
```

### Status codes

| Code | Meaning |
|---|---|
| `200` | Success |
| `201` | Created (only `POST /api/auth/register`) |
| `204` | Success, no body (only `DELETE /api/searches/{id}`) |
| `401` | Missing, malformed, or expired token |
| `404` | Not found, or not yours |
| `409` | Conflict — e.g. registering an email that exists, or preparing a job that already has an application |
| `422` | Validation error — Pydantic's standard `{"detail": [...]}` shape |
| `429` | Rate limited |

---

## Auth

### `POST /api/auth/register`

Creates a local account. This is the application's own login, unrelated to LinkedIn.

```json
{ "email": "you@example.com", "password": "at-least-ten-chars", "full_name": "Your Name" }
```

`password` is 10–72 characters; 72 bytes is bcrypt's limit and longer inputs are rejected rather than
silently truncated. `full_name` is optional.

The new account is created with an empty profile and conservative default guard rails — dry-run on, manual
approval required — so it cannot submit anything before you configure it.

→ `201` with `TokenResponse`:

```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 43200,
  "user": { "id": 1, "email": "you@example.com", "full_name": "Your Name",
            "is_active": true, "is_admin": false,
            "created_at": "2026-08-11T12:00:00+00:00", "last_login_at": null }
}
```

### `POST /api/auth/login`

```json
{ "email": "you@example.com", "password": "..." }
```

→ `TokenResponse`. `401` on bad credentials, without distinguishing a wrong password from an unknown email.

### `GET /api/auth/me`

→ `UserRead` for the bearer token's subject.

---

## Profile

Your CV and the answer bank the AI draws on. Everything here is optional, but a thin profile produces weak
scores and vague cover letters.

### `GET /api/profile`

→ `ProfileRead`:

```json
{
  "headline": "Backend Engineer",
  "location": "Fortaleza, Brazil",
  "phone": "+55 85 ...",
  "years_of_experience": 6,
  "summary": "...",
  "resume_text": "...",
  "resume_filename": "cv.pdf",
  "skills": ["Python", "FastAPI", "PostgreSQL"],
  "preferred_languages": ["pt-BR", "en"],
  "answer_bank": { "salary_expectation": "R$ 15.000", "notice_period": "30 days" },
  "updated_at": "2026-08-11T12:00:00+00:00"
}
```

### `PUT /api/profile`

`ProfileUpdate` — every field optional; omitted fields are left alone.

| Field | Constraint |
|---|---|
| `headline` | ≤ 300 chars |
| `location` | ≤ 200 chars |
| `phone` | ≤ 50 chars |
| `years_of_experience` | 0–70 |
| `summary`, `resume_text` | free text |
| `skills`, `preferred_languages` | arrays of strings — replaced wholesale, not merged |
| `answer_bank` | free-form object — replaced wholesale |

→ `ProfileRead`.

The `answer_bank` is what turns recurring screening questions into reliable answers. Keys are yours to
choose; the model matches them semantically against the question text:

```json
{ "salary_expectation": "R$ 15.000/month",
  "notice_period": "30 days",
  "work_authorization": "Brazilian citizen",
  "years_python": "6" }
```

### `POST /api/profile/resume`

`multipart/form-data`, one field named `file`, a PDF.

```bash
curl -X POST http://localhost:8000/api/profile/resume \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/cv.pdf"
```

The file is stored under `DATA_DIR/resumes/`, its text is extracted into `resume_text`, and both are
returned in the updated `ProfileRead`. The same file is attached to Easy Apply forms.

---

## Settings

Per-user guard rails and AI preferences. Field-by-field meanings, ranges, and the risk of loosening each
guard rail are in [configuration.md](configuration.md#per-user-settings-usersettings).

### `GET /api/settings`

→ `UserSettingsRead`:

```json
{
  "daily_cap": 15, "min_score": 70,
  "action_delay_min": 2.5, "action_delay_max": 7.0,
  "apply_delay_min": 45.0, "apply_delay_max": 120.0,
  "working_hour_start": 8, "working_hour_end": 20,
  "require_manual_approval": true, "dry_run": true,
  "ai_model": null, "cover_letter_tone": "profissional",
  "content_language": "job", "generate_cover_letter": true
}
```

### `PUT /api/settings`

`UserSettingsUpdate` — all fields optional. Cross-field rules are enforced and return `422` when broken:
`action_delay_min ≤ action_delay_max`, `apply_delay_min ≤ apply_delay_max`, and
`working_hour_start < working_hour_end`.

→ `UserSettingsRead`.

---

## Searches

A saved filter set. Saved rather than ad-hoc so a run is reproducible and `max_results` bounds the scan.

### `GET /api/searches`

→ `SearchRead[]`.

### `POST /api/searches`

`SearchCreate`:

```json
{
  "name": "Senior Python — remote",
  "keywords": "senior python engineer",
  "location": "Brazil",
  "remote_filter": "remote",
  "experience_levels": ["mid_senior", "director"],
  "date_posted": "week",
  "easy_apply_only": true,
  "max_results": 25
}
```

| Field | Notes |
|---|---|
| `name` | required, ≤ 200 chars |
| `keywords` | required, 1–300 chars |
| `location` | ≤ 200 chars |
| `remote_filter` | free-form string, ≤ 50 — `remote`, `hybrid`, `onsite` |
| `experience_levels` | array of strings |
| `date_posted` | ≤ 30 chars — `day`, `week`, `month` |
| `easy_apply_only` | defaults `true`. Only Easy Apply jobs can be auto-filled at all |
| `max_results` | 1–100, default 25. A per-run ceiling that keeps sweeps short |

→ `SearchRead` (adds `id`, `is_active`, `last_run_at`, `created_at`).

### `PATCH /api/searches/{id}`

`SearchUpdate` — the same fields, all optional, plus `is_active`. → `SearchRead`.

### `DELETE /api/searches/{id}`

→ `204`. Jobs already found by the search are kept; their `search_id` becomes `null`.

---

## Jobs

### `GET /api/jobs`

| Query param | Type | Notes |
|---|---|---|
| `status` | `JobStatus` | `discovered`, `analyzed`, `skipped`, `queued`, `applied`, `failed` |
| `min_score` | int | Jobs scoring at least this |
| `search_id` | int | Only jobs from one saved search |
| `limit` | int | Page size |
| `offset` | int | Page offset |

→ `Page<JobRead>`:

```json
{
  "items": [{
    "id": 42,
    "external_id": "3812345678",
    "title": "Senior Python Engineer",
    "company": "Example Co",
    "location": "Remote — Brazil",
    "url": "https://www.linkedin.com/jobs/view/3812345678",
    "workplace_type": "remote",
    "easy_apply": true,
    "status": "analyzed",
    "score": 87,
    "score_reasons": ["6 years of Python matches the 5+ requirement", "FastAPI is named in the posting"],
    "missing_requirements": ["Kubernetes in production"],
    "skip_reason": null,
    "detected_language": "en",
    "posted_at": "2026-08-10T09:00:00+00:00",
    "created_at": "2026-08-11T12:05:00+00:00",
    "search_id": 3,
    "application_id": null
  }],
  "total": 1, "limit": 50, "offset": 0
}
```

`score_reasons` and `missing_requirements` come straight from the model. The second list is the useful one:
it tells you what a recruiter will ask about.

### `GET /api/jobs/{id}`

→ `JobDetail` — `JobRead` plus the full `description`.

### `POST /api/jobs/{id}/skip`

Marks the job `skipped` so it is excluded from future runs. → `JobRead`.

### `POST /api/jobs/{id}/analyze`

Scores (or re-scores) one job with the AI. Useful for a job that arrived before you finished your profile,
or when `analyze: false` was used on the search run. → `JobRead` with `score`, `score_reasons`, and
`missing_requirements` populated, and `status` set to `analyzed`.

Requires `ANTHROPIC_API_KEY`; without it the call fails rather than inventing a score.

---

## Applications

### `GET /api/applications`

| Query param | Type |
|---|---|
| `status` | `ApplicationStatus` — `draft`, `preparing`, `awaiting_review`, `submitting`, `submitted`, `discarded`, `failed` |
| `limit`, `offset` | int |

→ `Page<ApplicationRead>`:

```json
{
  "items": [{
    "id": 7,
    "job_id": 42,
    "status": "awaiting_review",
    "cover_letter": "Dear hiring team, ...",
    "screening_answers": [{
      "question": "How many years of Python experience do you have?",
      "answer": "6",
      "question_type": "number",
      "confidence": "high",
      "needs_review": false,
      "reasoning": "Profile states 6 years",
      "field_id": "urn:li:fs_easyApplyFormElement:123"
    }],
    "resume_filename": "cv.pdf",
    "total_steps": 4,
    "current_step": 4,
    "needs_human_input": false,
    "was_dry_run": true,
    "approved_at": null,
    "submitted_at": null,
    "error_message": null,
    "created_at": "2026-08-11T12:10:00+00:00",
    "updated_at": "2026-08-11T12:12:00+00:00"
  }],
  "total": 1, "limit": 50, "offset": 0
}
```

Two fields drive the review UI. `needs_review` on an answer means the model was not confident — a `low`
confidence value sets it automatically, so a low-confidence answer can never reach you unflagged.
`needs_human_input` on the application means at least one field could not be filled at all.

`was_dry_run` records whether this was a rehearsal, so your history distinguishes drills from real
submissions.

### `GET /api/applications/{id}`

→ `ApplicationDetail` — `ApplicationRead` plus the nested `job` (`JobRead`) and the full `events` array
(`ApplicationEventOut[]`).

### `PATCH /api/applications/{id}`

Your edits during review, before approving.

```json
{
  "cover_letter": "My edited letter...",
  "screening_answers": [
    { "question": "Years of Python?", "answer": "4", "question_type": "number",
      "confidence": "high", "needs_review": false,
      "field_id": "urn:li:fs_easyApplyFormElement:123" }
  ]
}
```

Both fields are optional. `screening_answers` is validated against `ScreeningAnswer` and replaces the whole
array — send every answer, not just the ones you changed. Preserve each `field_id`; that is how an answer is
matched back to its form field.

→ `ApplicationDetail`. Records a `USER_EDITED` event.

### `POST /api/applications/{id}/submit`

**The only endpoint that submits anything to LinkedIn.**

```json
{ "confirm": true }
```

`confirm` is required and must be `true` — it is the consent, and there is no default. The endpoint acts on
exactly one application, identified in the path. There is no bulk-submit route, by design.

→ `ApplicationDetail` with `status: "submitted"`, `approved_at` and `submitted_at` set. Records
`USER_APPROVED` and `SUBMITTED` events.

Refuses when the application is not in `awaiting_review`, when the daily cap is reached, or when the current
time is outside the working-hours window.

With `dry_run: true` the flow completes without a real submission and the application is marked
`was_dry_run: true`.

### `POST /api/applications/{id}/discard`

Abandons the draft and closes the LinkedIn modal. → `ApplicationDetail` with `status: "discarded"`. Records
a `DISCARDED` event.

### `GET /api/applications/{id}/events`

The audit trail, oldest first.

→ `ApplicationEventOut[]`:

```json
[
  { "id": 1, "event_type": "form_opened", "message": "Easy Apply modal opened",
    "payload": { "total_steps": 4 }, "is_error": false,
    "created_at": "2026-08-11T12:10:05+00:00" },
  { "id": 2, "event_type": "question_answered", "message": "Years of Python experience",
    "payload": { "field_id": "...", "value": "6", "confidence": "high" },
    "is_error": false, "created_at": "2026-08-11T12:10:12+00:00" }
]
```

Event types: `job_found`, `job_analyzed`, `score_assigned`, `cover_letter_generated`, `form_opened`,
`form_step_completed`, `question_answered`, `resume_uploaded`, `awaiting_review`, `user_edited`,
`user_approved`, `submitted`, `discarded`, `error`.

This is the first place to look when an application fails. The `payload` carries the specifics —
which field, which options, which selector — so a failure is diagnosable without reproducing it.

---

## Automation

The engine. Search, prepare, and submit are separate operations that you invoke separately.

### `GET /api/automation/session`

→ `SessionStatus`:

```json
{
  "browser_open": true,
  "logged_in": true,
  "blocked": false,
  "blocked_reason": null,
  "active_run_id": null,
  "applications_today": 3,
  "daily_cap": 15,
  "dry_run": true,
  "ai_configured": true
}
```

`blocked: true` means a security checkpoint was detected. Solve it yourself in the browser; see
[safety.md](safety.md#security-checkpoints).

### `POST /api/automation/session/start`

Opens Chromium, restoring the saved session if one exists. → `SessionStatus`.

If `logged_in` is `false`, log in **manually in the browser window** — through noVNC at
<http://localhost:6080> under Docker, or the desktop window locally. The project never receives your
LinkedIn password.

### `POST /api/automation/session/stop`

Closes the browser and persists the encrypted session state. → `SessionStatus`.

### `POST /api/automation/search`

Runs a search and, by default, scores what it finds. Never applies to anything.

`SearchRunRequest`:

```json
{ "search_id": 3, "analyze": true }
```

or with ad-hoc filters:

```json
{
  "keywords": "senior python engineer",
  "location": "Brazil",
  "remote_filter": "remote",
  "date_posted": "week",
  "experience_levels": ["mid_senior"],
  "max_results": 25,
  "analyze": true
}
```

`max_results` is 1–100 (default 25). `analyze: false` skips AI scoring — faster and free, and you can score
individual jobs later with `POST /api/jobs/{id}/analyze`.

→ `AutomationRunRead`:

```json
{
  "id": 12, "kind": "search", "status": "running", "dry_run": true, "search_id": 3,
  "jobs_found": 0, "jobs_analyzed": 0, "jobs_skipped": 0,
  "applications_prepared": 0, "applications_submitted": 0,
  "stop_requested": false, "blocked_reason": null, "error_message": null,
  "started_at": "2026-08-11T12:05:00+00:00", "finished_at": null,
  "created_at": "2026-08-11T12:05:00+00:00"
}
```

The run proceeds in the background. Follow it on the WebSocket, or poll
`GET /api/automation/runs/{id}`.

### `POST /api/automation/preview`

**Always call this before `prepare`.** It reports what would happen, and changes nothing.

`PrepareRequest`:

```json
{ "job_ids": [42, 43, 44], "confirmed": false }
```

→ `PreviewResponse`:

```json
{
  "jobs_to_process": 2,
  "already_applied": 1,
  "below_threshold": 0,
  "remaining_today": 12,
  "daily_cap": 15,
  "dry_run": true,
  "requires_confirmation": true,
  "jobs": [],
  "warnings": ["Job 44 already has an application"]
}
```

The point is that you see the volume and the conditions before anything runs. There is no path where
dozens of applications are prepared without you having been shown the number first.

### `POST /api/automation/prepare`

Opens the Easy Apply form for each job, fills it, and **stops at the review step**.

```json
{ "job_ids": [42, 43], "confirmed": true }
```

`job_ids` holds 1–50 entries. `confirmed` must be `true` — it means you have seen the preview.

→ `AutomationRunRead` with `kind: "prepare"`. Each job gets an application in `awaiting_review`.

**This never submits.** `LinkedInService.fill_and_advance()` has no code path to submission; submission is
`POST /api/applications/{id}/submit`, one application at a time, with its own confirmation.

### `POST /api/automation/stop`

**The kill switch.** Sets `stop_requested` on the active run. The engine checks the flag between steps and
raises `StopRequestedError`, so it stops cleanly rather than mid-click — no half-submitted form, no torn
database state.

→ `Message`. The run's status becomes `stopped`.

Stopping is not instantaneous: it takes effect at the next step boundary, which can be a few seconds into a
randomized delay.

### `GET /api/automation/runs`

| Query param | Type |
|---|---|
| `limit` | int |

→ `AutomationRunRead[]`, newest first.

### `GET /api/automation/runs/{id}`

→ `AutomationRunRead`. Poll this if you would rather not hold a WebSocket open.

Statuses: `pending`, `running`, `paused`, `completed`, `stopped` (kill switch), `failed`, `blocked`
(security checkpoint).

---

## AI

### `GET /api/ai/status`

```json
{ "configured": true, "model": "claude-opus-5" }
```

`configured: false` means `ANTHROPIC_API_KEY` is unset. Search and form-filling still work; scoring, cover
letters, and answer suggestions do not.

### `POST /api/ai/cover-letter/{job_id}`

Generates (or regenerates) a cover letter for one job.

```json
{ "content": "Dear hiring team, ...", "language": "en" }
```

`language` reflects `UserSettings.content_language`: `job` means the language detected from the posting,
otherwise the tag you pinned. This call uses `high` effort — the letter is worth more than the tokens it
costs, unlike bulk scoring.

The model may decline. That is recorded on `AIAnalysis.was_refusal` and the application falls back to manual
entry; write the letter yourself.

---

## Stats

### `GET /api/stats`

→ `DashboardStats`:

```json
{
  "jobs_total": 128,
  "jobs_by_status": { "discovered": 12, "analyzed": 80, "skipped": 30, "applied": 6 },
  "applications_total": 6,
  "applications_today": 3,
  "awaiting_review": 2,
  "daily_cap": 15,
  "remaining_today": 12,
  "average_score": 71.4,
  "score_distribution": [{ "label": "80-100", "count": 24 }],
  "applications_last_7_days": [{ "date": "2026-08-11", "count": 3 }],
  "ai_calls_total": 92,
  "ai_tokens_input": 481203,
  "ai_tokens_output": 38112
}
```

The last three fields are your cost meter.

---

## Health

### `GET /api/health`

No auth required.

```json
{ "status": "ok", "version": "0.1.0" }
```

---

## WebSocket

### `GET /api/ws?token=<jwt>`

The live activity feed. The token goes in the query string because browsers cannot set headers on a
WebSocket handshake.

```javascript
const ws = new WebSocket(`ws://localhost:8000/api/ws?token=${token}`);
ws.onmessage = (e) => {
  const event = JSON.parse(e.data);
  console.log(event.name, event.level, event.message);
};
```

On connect, the last 200 events for your user are replayed, so a page reload rebuilds the feed instead of
starting empty. Events are addressed per user — you never see another user's activity.

Publishing never raises on the server side: a closed tab cannot break a run in progress.

### Envelope

```json
{
  "name": "job.analyzed",
  "timestamp": "2026-08-11T12:06:31.482913+00:00",
  "run_id": 12,
  "job_id": 42,
  "application_id": null,
  "message": "Senior Python Engineer — 87",
  "level": "info",
  "data": { "score": 87, "recommend_apply": true }
}
```

| Field | Type | Notes |
|---|---|---|
| `name` | `EventName` | See the catalogue below |
| `timestamp` | ISO 8601 UTC | |
| `run_id` | int \| null | Present for engine events |
| `job_id` | int \| null | |
| `application_id` | int \| null | |
| `message` | string \| null | Human-readable line |
| `level` | string | `info`, `warning`, `error`, `success` |
| `data` | object | Event-specific payload |

The Python source of truth is
[`app/observability/events.py`](../backend/app/observability/events.py); the frontend mirror is
`frontend/src/types/events.ts`. Keep them in step.

### Event catalogue

| `name` | Typical `level` | When it fires | What is usually in `data` |
|---|---|---|---|
| `automation.started` | `info` | A run begins | `kind`, `dry_run` |
| `automation.progress` | `info` | Step-level progress | counters — `jobs_found`, `jobs_analyzed` |
| `automation.stopped` | `warning` | Kill switch took effect | `reason` |
| `automation.error` | `error` | A run failed | `error`, `error_type` |
| `automation.blocked` | `error` | **Security checkpoint detected — everything halted** | `blocked_reason` |
| `job.found` | `info` | A posting was discovered | `title`, `company` |
| `job.analyzed` | `info` | Scoring finished | `score`, `recommend_apply`, `missing_requirements` |
| `application.started` | `info` | The Easy Apply modal opened | `total_steps` |
| `application.awaiting_review` | `success` | **Filled and waiting for you** | `needs_human_input`, `questions_flagged` |
| `application.completed` | `success` | Submitted after your approval | `was_dry_run` |
| `session.status` | `info` | Browser opened/closed, LinkedIn login state changed | `browser_open`, `logged_in` |
| `log` | any | A log line for the activity feed | free-form |

`application.awaiting_review` and `automation.blocked` are the two the UI should make impossible to miss:
the first is the moment you are needed, the second the moment everything stopped.

---

## A full session, start to finish

```bash
BASE=http://localhost:8000/api

# 1. Log in
TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"..."}' | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"

# 2. Open the browser, then log into LinkedIn by hand in the window
curl -s -X POST $BASE/automation/session/start -H "$AUTH" | jq
curl -s $BASE/automation/session -H "$AUTH" | jq .logged_in   # wait for true

# 3. Save a search and run it
SEARCH=$(curl -s -X POST $BASE/searches -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"Remote Python","keywords":"senior python engineer","remote_filter":"remote","max_results":25}' \
  | jq -r .id)
curl -s -X POST $BASE/automation/search -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"search_id\": $SEARCH, \"analyze\": true}" | jq .id

# 4. Look at what scored well
curl -s "$BASE/jobs?status=analyzed&min_score=80" -H "$AUTH" | jq '.items[] | {id, title, score}'

# 5. Preview, then prepare — always in that order
curl -s -X POST $BASE/automation/preview -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"job_ids":[42,43]}' | jq
curl -s -X POST $BASE/automation/prepare -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"job_ids":[42,43],"confirmed":true}' | jq .id

# 6. Read the draft in full — letter and every answer
curl -s $BASE/applications/7 -H "$AUTH" | jq '{cover_letter, screening_answers}'

# 7. Fix anything that is wrong
curl -s -X PATCH $BASE/applications/7 -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"cover_letter":"My edited letter..."}' | jq .status

# 8. Approve this one application
curl -s -X POST $BASE/applications/7/submit -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"confirm":true}' | jq '{status, submitted_at, was_dry_run}'

# Kill switch, at any point
curl -s -X POST $BASE/automation/stop -H "$AUTH" | jq
```

Note that steps 5 through 8 cannot be collapsed. Preview precedes prepare, prepare stops at review, and
submit takes one id and an explicit `confirm`. That separation is the product.
