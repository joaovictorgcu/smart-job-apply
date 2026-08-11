---
name: Bug report
about: Something does not work the way it should
title: "fix: "
labels: bug
---

<!--
Never paste cookies, JWTs, .env contents, or a real API key into an issue.
If you already have somewhere, rotate the key.
-->

## What happened

## What you expected instead

## Steps to reproduce

1.
2.
3.

## Did the LinkedIn UI change?

A large share of bugs here are LinkedIn shipping a redesign, and the fix is usually one line in
`backend/app/automation/linkedin/selectors.py`. This answer often routes the issue straight to the
right file.

- [ ] The page or modal looked different from what I expected
- [ ] No, the UI looked normal
- [ ] Not sure / did not see the browser

If it did change, what looked different? (A screenshot of the Easy Apply modal helps a lot.)

`ElementNotFoundError` or `UnexpectedPageError` in the logs is a strong hint that it did.

## Structured log lines — redacted

Logs are JSON, one object per line. Paste the whole object rather than a summary; the `action`,
`status`, `run_id`, `job_id`, and `application_id` fields are what place the failure.

**Redact first:** your email, your name, cookie values, tokens, API keys, and anything in a
`payload` you would not post publicly.

```json

```

## Application event trail

If a specific application failed, `GET /api/applications/{id}/events` is the audit trail and usually
names the exact field and step. Redact and paste it here.

```json

```

## Environment

- Install method: <!-- Docker / local -->
- OS: <!-- e.g. Windows 11, macOS 15, Ubuntu 24.04 -->
- Python version: <!-- python --version — local installs only -->
- Project version or commit: <!-- from GET /api/health, or `git rev-parse --short HEAD` -->
- Database: <!-- SQLite (default) / PostgreSQL -->
- `dry_run` at the time: <!-- true / false -->
- AI configured: <!-- from GET /api/ai/status -->

## Anything else
