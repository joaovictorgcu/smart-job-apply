# Safety, risk, and ethics

Read this before you run the tool, not after. It is the honest version.

## The core conflict

LinkedIn's User Agreement prohibits accessing the service with automated means — scrapers, bots, and
browser automation are all named. This project automates the LinkedIn web interface. There is no reading
of the Agreement under which that is permitted.

LinkedIn does not offer a public API for searching jobs or submitting applications. There is no compliant
path to the same outcome. That is *why* this project drives a browser, and it is not a justification —
it is the reason the risk exists and cannot be engineered away.

**What that means for you concretely:** LinkedIn may restrict your account, require identity
verification, or ban it permanently, at their discretion, with no appeal you are entitled to. Your
professional network, your message history, your job-application history, and your profile are all in that
account. Weigh that against the time this tool saves you. For some people that trade is clearly not worth
it, and the right answer is to close this repository and apply by hand.

## What the guard rails do

| Guard rail | What it actually protects against |
|---|---|
| Randomized action delays (2.5–7 s) | Uniform, machine-timed click intervals — a trivially detectable pattern |
| Randomized apply delays (45–120 s) | Bursts of applications inside a few seconds |
| Daily cap (15, hard max 50) | Volume that no human job search produces |
| Working-hours window (08:00–20:00) | Activity at 4 a.m. every day |
| One browser session | Parallel sessions from one account |
| Per-run result cap (`max_results`, ≤ 100) | Long scraping sweeps across dozens of result pages |
| Visible (non-headless) browser | Silent failure — you can see what is happening and take over |
| Human approval before every submission | Sending applications you did not read |

Together these make the traffic pattern look like a person using LinkedIn attentively rather than a script
hammering it. That is a meaningful reduction in risk.

## What the guard rails do not do

They do not make you undetectable, and it would be dishonest to imply otherwise.

- **Browser fingerprinting still applies.** Playwright-driven Chromium is distinguishable from a
  hand-driven browser through automation flags, rendering and timing characteristics, and behavioral
  telemetry. This project makes no attempt to defeat fingerprinting.
- **Behavior in aggregate is still unusual.** Even at a human pace, a session that visits job pages and
  opens Easy Apply modals in a consistent sequence, day after day, has a shape.
- **Server-side signals are invisible to us.** LinkedIn's anti-automation systems are not documented and
  change without notice. Nothing here can be tuned against them.
- **The risk is not proportional to volume alone.** A single unlucky session can trip a check. A cautious
  configuration lowers the odds; it does not create a safe threshold.
- **No guard rail protects you from a bad application.** Delays and caps are about detection. Whether the
  cover letter is accurate and the screening answers are true is entirely on the human review step.

**Do not loosen the guard rails to go faster.** Every knob in
[configuration.md](configuration.md#guard-rails) says what you are trading. The defaults are conservative
on purpose.

## The human-approval invariant

This is the one property the project treats as non-negotiable: **nothing submits a LinkedIn application
without an explicit, separate, user-confirmed action.**

It is enforced structurally rather than by a setting, in four independent places:

1. **The service contract.** `LinkedInService.fill_and_advance()` is specified to advance the Easy Apply
   form and halt at the review step. It has no code path to submission. `submit()` is a separate method.
2. **The API shape.** Preparing applications (`POST /api/automation/prepare`) and submitting one
   (`POST /api/applications/{id}/submit`) are different endpoints. Prepare requires `confirmed: true` and
   acts on a batch; submit requires `confirm: true` and acts on exactly one application, by id. There is
   no bulk-submit endpoint.
3. **The state machine.** A prepared application sits in `awaiting_review`. Nothing moves it out of that
   state automatically.
4. **The defaults.** `ASSISTED_MODE_ONLY=true`, `require_manual_approval=true`, `dry_run=true`.

A fully-automatic mode is not an unfinished feature. It is a deliberate refusal, and a pull request that
weakens any of the four points above will not be merged — see [CONTRIBUTING.md](../CONTRIBUTING.md).

### Dry-run mode

`dry_run` defaults to `true`. In that state the engine does everything except the final click: it searches,
scores, opens the form, fills the fields, attaches the résumé, and stops at review. Applications created
during a dry run are marked `was_dry_run = true`, so your history distinguishes rehearsals from real
submissions.

Run in dry-run mode until you have watched the whole flow at least once and read a couple of drafted
applications end to end. Then turn it off deliberately.

## Security checkpoints

If a CAPTCHA, a "security verification" screen, an "unusual activity" notice, or any equivalent challenge
appears, the automation raises `SecurityCheckpointError` and stops.

What happens on that path:

1. The run's status becomes `BLOCKED` and `blocked_reason` is recorded.
2. An `automation.blocked` event is published to the dashboard.
3. No retry. No alternative selector. No attempt to read, guess, or route around the challenge.

**Solve it yourself, in the browser window, as yourself.** Then decide whether to continue. If checkpoints
appear repeatedly, that is LinkedIn telling you the activity looks automated — stop using the tool on that
account rather than tuning delays until the warnings go away.

There is no configuration option to bypass a checkpoint, and adding one is out of scope for this project.

## Passwords and session data

**The project never asks for, receives, or stores your LinkedIn password.** There is no field for it in
the schema, no parameter for it in the API, and no prompt for it in the UI.

The flow is: the automation opens a visible Chromium window, you log in by hand exactly as you would
normally — including two-factor authentication — and only the resulting session state is persisted.

That state is encrypted at rest with Fernet (AES-128-CBC + HMAC), using a key derived via HKDF-SHA256 from
`ENCRYPTION_KEY` (falling back to `SECRET_KEY`). `LinkedInAccountRead`, the only schema that exposes the
account over the API, carries a display name, a connected flag, and a timestamp — no cookie ever leaves
through an endpoint.

Changing `ENCRYPTION_KEY` makes stored sessions unreadable. That is recoverable: reconnect LinkedIn and log
in again.

## What is stored, and where

| Data | Location | Sensitivity |
|---|---|---|
| Your app account password | `users.hashed_password` | bcrypt hash, not reversible |
| LinkedIn session cookies | `linkedin_accounts.encrypted_storage_state` | **Live credentials.** Encrypted at rest; anyone who has both this row and your `ENCRYPTION_KEY` can act as you on LinkedIn |
| Browser profile directory | `backend/data/browser_profiles/` | May contain further session artifacts written by Chromium |
| Your CV, as uploaded | `backend/data/resumes/` | Personal data — name, address, phone, work history |
| Your CV, as text | `profiles.resume_text` | Same, in the database |
| Answer bank | `profiles.answer_bank` | Salary expectations, notice period, work authorization |
| Job descriptions and scores | `jobs` | Low |
| Drafted letters and answers | `applications` | Personal, and sent to employers once approved |
| AI call records | `ai_analyses` | Raw model output, token counts, cost |
| Audit trail | `application_events` | What was sent on your behalf, and when |
| Screenshots | `backend/data/` | May contain your filled-in form data |

Everything above lives on your own machine or server. Nothing is sent to a service the project operates —
there is no such service.

Two external parties do receive data, and you should know exactly what:

- **Anthropic** receives the job description plus the parts of your profile needed to score it and draft
  the letter, whenever AI features are used. Leave `ANTHROPIC_API_KEY` unset and no data is sent at all;
  you fill the forms yourself.
- **LinkedIn** receives your applications — which is the point.

### `backend/data/` is gitignored for a reason

That directory holds live session cookies, your CV, and your answer bank. It is in
[`.gitignore`](../.gitignore) and must stay there. Before pushing this repository anywhere public, verify:

```bash
git check-ignore -v backend/data/app.db   # should print the ignoring rule
git ls-files backend/data                 # should print nothing
```

The same applies to `.env`, which holds your API key and your encryption key.

When you back the directory up — and you should, since it is the only copy of your job-search history —
back it up somewhere you would be comfortable storing your CV and a set of live credentials.

## Ethics

The technical risk is yours to accept. These are about other people.

**Use it on your own account only.** Not a client's, not a friend's, not a shared one. The person whose
account is at risk must be the person who chose to take the risk.

**Do not spam employers.** On the other side of each application is a human who reads it. The daily cap and
the score threshold exist as much for their sake as for yours: fifteen considered applications to jobs you
plausibly fit is a job search, and two hundred scattershot ones is a denial-of-service attack on someone's
inbox. Raising the cap and lowering the threshold at the same time is exactly the wrong direction.

**Review every application before it goes out.** This is the ethical core of assisted mode, not just a
safety feature. The letter goes out under your name and the screening answers are representations about
you. An AI-drafted answer that is wrong is *your* false statement to an employer once you approve it. Read
the letter. Check every answer, and check the low-confidence ones twice —
[`ScreeningAnswer`](../backend/app/ai/schemas.py) flags them with `needs_review` precisely so the UI can
put them in front of you.

**Never overstate your experience.** If the AI drafts "8 years of Python" and you have four, fix it before
approving. The tool makes it easy to send a lot of applications quickly; that makes it easy to send a small
lie a lot of times.

**The AI will sometimes refuse.** Refusals are recorded (`AIAnalysis.was_refusal`) and the application
falls back to manual entry. That is the system working: fill the field yourself.

## If your account gets restricted

Nothing in this project can appeal a restriction for you, and neither can the author. Follow LinkedIn's own
recovery process, as yourself. Then reconsider whether to keep using browser automation on the account —
a second restriction on the same account is generally worse than the first.

## Summary

- Automating LinkedIn violates their User Agreement and can cost you your account, permanently.
- There is no official API for applying to jobs, which is why this exists and why the risk cannot be
  removed.
- The guard rails lower the odds. They do not make you safe, and loosening them raises the odds sharply.
- Submission always requires a separate human confirmation, by design and in four independent places.
- Security challenges stop everything. Solve them yourself; never bypass them.
- Your LinkedIn password is never stored. Session cookies are, encrypted.
- `backend/data/` and `.env` hold live credentials and personal data. Keep them out of git and back them up
  carefully.
- Use it on your own account, at a human volume, and read every application before you approve it.
