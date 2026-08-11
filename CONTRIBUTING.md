# Contributing

Thanks for wanting to help. This is a small, self-hosted project, so the process is light — but two rules
below are absolute, and it is worth reading those before you write code.

## The two rules

### 1. No pull request may weaken the human-approval guarantee

**Nothing may submit a LinkedIn application without an explicit, separate, user-confirmed action.** That is
not a feature flag; it is the premise of the project. Concretely, a PR will be rejected if it:

- gives `fill_and_advance()` any path to submission — it advances the Easy Apply form and stops at review,
  full stop;
- adds a bulk-submit endpoint, or lets `POST /api/applications/{id}/submit` act on more than the one
  application named in its path;
- makes `confirm` or `confirmed` optional, or gives either a default of `true`;
- flips the default of `ASSISTED_MODE_ONLY`, `require_manual_approval`, or `dry_run`;
- moves an application out of `awaiting_review` without a user action;
- adds a UI control that submits without the cover letter and screening answers visible on screen at that
  moment;
- adds any "auto-apply", "unattended", or "run overnight" mode.

A fully automatic mode is a deliberate refusal, not a missing feature. If you want one, fork the project —
please do not ask for it here.

### 2. Never bypass a security challenge

If a CAPTCHA, "security verification", or "unusual activity" page appears, the code raises
`SecurityCheckpointError` and stops. A PR will be rejected if it catches that error and retries, tries an
alternative selector, attempts to read or solve a challenge, adds a fingerprint-evasion or stealth layer, or
adds a setting to skip the halt.

Related, and equally firm: **the project never stores a LinkedIn password.** No schema field, no API
parameter, no UI prompt, no "remember my credentials" convenience. The user logs in by hand in the visible
browser; only session cookies are persisted, encrypted.

If a change you want to make runs into either rule, open an issue and describe the problem you are trying to
solve. There is usually another way.

## Setup

Follow [docs/installation.md](docs/installation.md) — the local path. In short:

```bash
git clone https://github.com/joaovictorgcu/smart-job-apply.git
cd smart-job-apply
python -m venv .venv && source .venv/bin/activate   # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
playwright install chromium
cd frontend && npm ci && cd ..
```

Then read [docs/development.md](docs/development.md) for the layout, how to add a route or a service, how the
LinkedIn and AI fakes work, and how to debug the automation with a headed browser.

## Before you open a PR

Everything below must pass. CI runs the same checks, so running them locally saves a round trip.

```bash
pytest                          # all tests pass
ruff check .                    # no lint errors
ruff format --check .           # formatting is clean
mypy backend/app                # advisory — read the output, don't add new errors
cd frontend && npm run typecheck && npm run build
```

The test suite is entirely offline: no LinkedIn account, no Anthropic key, no network. Keep it that way. A
test that needs either belongs behind a marker and outside CI.

**New behavior needs a test.** New guard-rail behavior, or anything near the submission path, needs a test
that would fail if the guarantee broke. The most important test in the repo is the one asserting that
preparing an application submits nothing:

```python
async def test_prepare_never_submits(...):
    await prepare_applications(job_ids=[job.id], confirmed=True, linkedin=fake_linkedin, ai=fake_ai)
    assert fake_linkedin.submitted == []
    assert application.status is ApplicationStatus.AWAITING_REVIEW
```

## Code style

The full version is in [docs/development.md](docs/development.md#code-style). The parts most often missed:

- **English only** — identifiers, comments, docstrings, log messages, error messages, UI copy, documentation.
  No exceptions.
- **Never `print()`.** Use `from app.observability import get_logger` and pass structured fields via `extra`.
- **Comment the "why", not the "what".** A comment restating the next line is noise. A comment explaining a
  constraint — why a validator is a model validator, why `check_same_thread=False` is needed — earns its
  place.
- Ruff is configured in [`pyproject.toml`](pyproject.toml) at 100 columns with `E, F, I, UP, B, SIM, ASYNC`.
  Do not add per-file ignores to get a change through; fix the code.
- Keep Playwright inside `app/automation/linkedin/`, and every selector inside `selectors.py`. If a change
  makes the engine import Playwright, the layering is wrong.
- Keep `app/observability/events.py` and `frontend/src/types/events.ts` in step. A mismatch breaks the
  activity feed silently.

## Branches and commits

Branch from `main`, named for the change:

```
feat/screening-answer-editor
fix/selector-easy-apply-modal
docs/postgres-setup
refactor/engine-checkpoint
test/kill-switch
chore/bump-playwright
```

Commits follow [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`, in the
imperative, no trailing period.

```
feat(api): add screening answer editing endpoint
fix(automation): update Easy Apply modal selector after LinkedIn redesign
docs(safety): explain what the guard rails do not protect against
test(engine): cover kill switch during a randomized delay
refactor(ai): move refusal handling into the client
chore(deps): bump playwright to 1.50
```

Types in use: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`, `ci`.

Scopes match the code: `api`, `ai`, `automation`, `auth`, `models`, `schemas`, `database`, `observability`,
`websocket`, `frontend`, `docker`, `deps`.

Explain *why* in the body when the reason is not obvious from the diff. A selector fix should say what
LinkedIn changed.

## Pull requests

- One logical change per PR. A refactor bundled with a feature is two PRs.
- Fill in the [template](.github/pull_request_template.md), including the assisted-mode checkbox — it exists
  so the invariant gets a conscious look on every change.
- Screenshots for UI changes, before and after.
- Update the docs in the same PR: [api.md](docs/api.md) for endpoints,
  [configuration.md](docs/configuration.md) for settings, [architecture.md](docs/architecture.md) when a
  table's purpose or a layer boundary changes.
- Say how you tested it. "Ran a dry-run search against my own account and reviewed two drafts" is useful
  information the test suite cannot give.

## Reporting bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md). Two things make a report actionable:

**The structured log lines, redacted.** Logs are JSON, one object per line, and they contain the ids and the
action names needed to place a failure. Remove your email, your name, cookie values, tokens, and API keys
before pasting — and paste the whole object, not a summary of it.

**Whether the LinkedIn UI may have changed.** A large share of bugs here are LinkedIn shipping a redesign,
and the fix is a one-line change in `selectors.py`. Saying "the Easy Apply modal looks different from the
screenshots" moves a report straight to the right file. `ElementNotFoundError` or `UnexpectedPageError` in
the logs is a strong hint.

Also attach `GET /api/applications/{id}/events` for a failed application if you have it. That is the audit
trail, and it usually names the exact field and step.

**Never paste cookies, tokens, `.env` contents, or a real API key into an issue.** If you think you already
have, rotate the key.

## Suggesting features

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md). Lead with the problem rather
than the solution, and say how you hit it. Features that reduce human oversight are out of scope; see rule 1.

## Reporting a security issue

Do not open a public issue. Email **joao.uchoa@globalthings.net** with what you found and how to reproduce
it. Credential handling, at-rest encryption, and cross-user data isolation are the areas most worth looking
at.

## Licence

Contributions are released under the [MIT Licence](LICENSE), same as the project.
