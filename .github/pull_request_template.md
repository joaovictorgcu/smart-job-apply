## What this changes

<!-- One or two sentences. Link the issue if there is one: Fixes #123 -->

## Why

<!-- Especially for selector fixes: what did LinkedIn change? -->

## Type

- [ ] `feat` — new behavior
- [ ] `fix` — bug fix
- [ ] `docs`
- [ ] `test`
- [ ] `refactor` — no behavior change
- [ ] `chore` / `deps` / `ci`

## Assisted mode

This project guarantees that **nothing submits a LinkedIn application without an explicit,
separate, user-confirmed action.** Every PR gets a conscious look at this.

- [ ] This change does not weaken that guarantee

Specifically, this PR does **not**:

- [ ] give `fill_and_advance()` any path to submission
- [ ] add a bulk-submit endpoint, or let `submit` act on more than the one application in its path
- [ ] make `confirm` / `confirmed` optional or default to `true`
- [ ] change the default of `ASSISTED_MODE_ONLY`, `require_manual_approval`, or `dry_run`
- [ ] move an application out of `awaiting_review` without a user action
- [ ] add a UI control that submits without the letter and answers visible on screen
- [ ] catch `SecurityCheckpointError` and continue, or otherwise work around a challenge
- [ ] store, request, or log a LinkedIn password

<!-- If any box above is unchecked, explain here. Expect a long conversation. -->

## Testing

- [ ] `pytest` passes
- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] `mypy backend/app` introduces no new errors
- [ ] `npm run typecheck` and `npm run build` pass (if the frontend changed)
- [ ] New behavior has a test; a fixed bug has a regression test

How you verified it by hand:

<!-- e.g. "dry-run search on my own account, reviewed two drafted applications end to end" -->

## Docs

- [ ] [docs/api.md](../docs/api.md) updated (endpoint changes)
- [ ] [docs/configuration.md](../docs/configuration.md) updated (new or changed settings)
- [ ] [docs/architecture.md](../docs/architecture.md) updated (schema or layer-boundary changes)
- [ ] README updated, if this changes setup or the first-run flow
- [ ] No docs needed

## Screenshots

<!-- Before and after, for UI changes. -->

## Anything reviewers should look at closely
