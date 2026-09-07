"""A fake job portal, shaped like the markup `selectors.py` targets.

Two jobs, one implementation:

* **Demo mode.** With `DEMO_PORTAL=true`, `BrowserSession` serves this instead
  of the live site, so the whole product — search, score, draft, review gate,
  submit — can be driven from the dashboard with nothing configured and no real
  application sent anywhere. That is the supported way to try the app out.
* **Browser tests.** `backend/tests/e2e` drives the production page objects
  against it, which is the only coverage the Playwright layer has: every other
  test replaces the browser wholesale with `FakeLinkedInService`.

**It is not LinkedIn and must never be pointed at LinkedIn.** Driving the real
site in a demo or a test loop would breach its terms and risk the account; the
markup here mirrors the shapes `selectors.py` looks for so the same code paths
run against something we are allowed to automate.

There is no socket. `install()` registers a Playwright route on the browser
context and every request to `https://www.linkedin.com/**` is fulfilled from
`FakePortal.handle()`. The page's own URL stays a linkedin.com URL, so the URL
handling in `browser.py` — including checkpoint detection by URL fragment — is
exercised exactly as it is against the real site.

The portal is scriptable: postings, per-step form definitions, whether a job is
already applied, and whether navigation lands on a security challenge. It records
what the browser did, and `submitted` is the assertion that guards assisted mode.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from html import escape
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

FieldKind = Literal["text", "number", "textarea", "select", "radio", "checkbox", "file"]

# Job ids have to be digit-only: `JobSearchPage._card_external_id` rejects
# anything else, because LinkedIn's ids are numeric.
_FIRST_JOB_ID = 4010000001

# Path the modal's submit handler calls so the click is recorded on the Python
# side. It is a linkedin.com URL, so the same route interception catches it.
RECORD_SUBMIT_PATH = "/__portal/record-submit"

CHECKPOINT_PATH = "/checkpoint/challenge/AgH9xTest"


@dataclass
class PortalField:
    """One question the fake Easy Apply form asks."""

    field_id: str
    label: str
    kind: FieldKind = "text"
    options: tuple[str, ...] = ()
    required: bool = False
    value: str = ""


@dataclass
class PortalStep:
    """One step of the fake Easy Apply form."""

    fields: tuple[PortalField, ...] = ()
    #: Rendered as the review step: submit only, no next/review button.
    review: bool = False


@dataclass
class PortalJob:
    """One posting, as both a result card and a detail page."""

    external_id: str
    title: str
    company: str
    location: str = "Remote"
    description: str = (
        "We are looking for a backend engineer. Python and FastAPI are required; "
        "PostgreSQL and Docker are a plus. Fluent English is required."
    )
    workplace_text: str = "Remote"
    easy_apply: bool = True
    already_applied: bool = False
    posted: str = "2 days ago"


def _form_fields() -> tuple[PortalField, ...]:
    """Every control kind `apply.py` knows how to fill, once each.

    A regression in any one of them — file upload, text, number, radio group,
    select, textarea — shows up in the browser tests through this tuple.
    """
    return (
        PortalField("resume-upload", "Resume", "file"),
        PortalField(
            "single-line-text-form-component-city", "City", "text", value="São Paulo, Brazil"
        ),
        PortalField(
            "numeric-form-component-years",
            "Years of Python experience?",
            "number",
            required=True,
        ),
        PortalField(
            "radio-form-component-auth",
            "Are you authorized to work in this country?",
            "radio",
            options=("Yes", "No"),
            required=True,
        ),
        PortalField(
            "select-form-component-english",
            "Level of English",
            "select",
            options=("Select an option", "Basic", "Intermediate", "Advanced"),
            required=True,
        ),
        PortalField("textarea-form-component-letter", "Cover letter", "textarea"),
    )


# Labels the demo form deliberately leaves out, and why:
#
# * A cover-letter textarea is asked as a screening question by the engine
#   *and* filled by the dedicated cover-letter path. The screening model has no
#   sensible answer to "Cover letter" as a question, so it flags it, which sets
#   `needs_human_input` and blocks approval on every form that has one. Correct
#   behaviour on a real posting — a human should write that box — but it means a
#   demo of the happy path cannot include the field.
_EXCLUDED_FROM_DEMO_FORM = frozenset({"textarea-form-component-letter"})


def default_steps() -> tuple[PortalStep, ...]:
    """One question page, then review — the common Easy Apply shape.

    Single-page on purpose. `EasyApplyModal.open` reports only the step that is
    on screen, so the AI is asked about the first step's questions and nothing
    else; on a multi-step form the later steps' required fields therefore come
    back unanswered and the draft correctly stops for a human. That is real
    product behaviour, not a portal artefact — see `multi_step_steps` for the
    fixture that exercises it — but it means a multi-step form can never
    complete unattended, so it is the wrong default for a demo of the happy
    path.
    """
    fields = tuple(
        item for item in _form_fields() if item.field_id not in _EXCLUDED_FROM_DEMO_FORM
    )
    return (PortalStep(fields=fields), PortalStep(review=True))


def multi_step_steps() -> tuple[PortalStep, ...]:
    """A four-page form: contact, screening, letter, review.

    Used by the browser tests to prove the step navigation works and that a
    question the automation never saw is reported rather than skipped.
    """
    fields = {item.field_id: item for item in _form_fields()}
    return (
        PortalStep(
            fields=(fields["resume-upload"], fields["single-line-text-form-component-city"])
        ),
        PortalStep(
            fields=(
                fields["numeric-form-component-years"],
                fields["radio-form-component-auth"],
                fields["select-form-component-english"],
            )
        ),
        PortalStep(fields=(fields["textarea-form-component-letter"],)),
        PortalStep(review=True),
    )


def make_jobs(count: int = 3, *, easy_apply: bool = True) -> list[PortalJob]:
    return [
        PortalJob(
            external_id=str(_FIRST_JOB_ID + index),
            title=f"Backend Engineer {index + 1}",
            company=f"Company {index + 1}",
            easy_apply=easy_apply,
        )
        for index in range(count)
    ]


@dataclass
class FakePortal:
    """Serves the fake site and records what the browser did to it."""

    jobs: list[PortalJob] = field(default_factory=lambda: make_jobs(3))
    steps: tuple[PortalStep, ...] = field(default_factory=default_steps)
    logged_in: bool = True
    display_name: str = "Test Candidate"
    #: Any path containing one of these substrings serves the challenge page.
    checkpoint_paths: tuple[str, ...] = ()
    #: Serve the challenge page for every request after this many navigations.
    checkpoint_after: int | None = None

    requests: list[str] = field(default_factory=list)
    submitted: list[str] = field(default_factory=list)
    submitted_payloads: list[dict[str, Any]] = field(default_factory=list)

    # --- lookup -------------------------------------------------------------

    def job(self, external_id: str) -> PortalJob | None:
        return next((job for job in self.jobs if job.external_id == external_id), None)

    @property
    def easy_apply_jobs(self) -> list[PortalJob]:
        return [job for job in self.jobs if job.easy_apply]

    # --- routing ------------------------------------------------------------

    def handle(self, url: str) -> tuple[int, str, str]:
        """`(status, content_type, body)` for one request. Never raises."""
        parsed = urlparse(url)
        path = parsed.path or "/"
        query = parse_qs(parsed.query)
        self.requests.append(f"{path}?{parsed.query}" if parsed.query else path)

        if path.startswith(RECORD_SUBMIT_PATH):
            return self._record_submit(query)

        if self._is_checkpoint(path):
            return 200, "text/html", _checkpoint_page()

        if not self.logged_in and path not in ("/login", "/uas/login"):
            # A logged-out portal redirects everything to the login wall, which
            # is how `browser.is_logged_in` decides the session is dead.
            return 200, "text/html", _login_page()

        if path in ("/", "/feed", "/feed/"):
            return 200, "text/html", _feed_page(self.display_name)
        if path in ("/login", "/uas/login"):
            return 200, "text/html", _login_page()
        if path.startswith("/jobs/search"):
            return 200, "text/html", self._search_page(query)
        if path.startswith("/jobs/view/"):
            return self._job_page(path)

        return 404, "text/html", "<html><body><h1>Not found</h1></body></html>"

    def _is_checkpoint(self, path: str) -> bool:
        if any(fragment in path for fragment in self.checkpoint_paths):
            return True
        if self.checkpoint_after is None:
            return False
        # `requests` already includes this one, hence the strict comparison.
        return len(self.requests) > self.checkpoint_after

    def _record_submit(self, query: dict[str, list[str]]) -> tuple[int, str, str]:
        external_id = (query.get("id") or [""])[0]
        raw = (query.get("answers") or ["{}"])[0]
        self.submitted.append(external_id)
        try:
            self.submitted_payloads.append(json.loads(raw))
        except ValueError:
            self.submitted_payloads.append({})
        return 200, "application/json", '{"ok":true}'

    def _search_page(self, query: dict[str, list[str]]) -> str:
        start = int((query.get("start") or ["0"])[0] or 0)
        easy_only = (query.get("f_AL") or [""])[0] == "true"
        pool = self.easy_apply_jobs if easy_only else self.jobs
        # One page is enough for the suite; a second page must come back empty so
        # `JobSearchPage.collect` terminates instead of paging forever.
        page = pool if start == 0 else []
        return _search_page(page)

    def _job_page(self, path: str) -> tuple[int, str, str]:
        external_id = path.rstrip("/").rsplit("/", 1)[-1]
        job = self.job(external_id)
        if job is None:
            return 404, "text/html", "<html><body><h1>No such job</h1></body></html>"
        return 200, "text/html", _job_page(job, self.steps)


async def install(context: Any, portal: FakePortal) -> None:
    """Serve `portal` for every linkedin.com request on this browser context.

    Fulfilling rather than redirecting is deliberate: the page keeps its
    linkedin.com URL, so `Urls`, `LOGGED_OUT_FRAGMENTS` and the checkpoint URL
    fragments are all exercised on the strings production actually sees.
    """

    async def route_handler(route: Any) -> None:
        status, content_type, body = portal.handle(route.request.url)
        await route.fulfill(status=status, content_type=content_type, body=body)

    async def block_everything_else(route: Any) -> None:
        # Registered last, so Playwright runs it first: anything that is not the
        # fake portal is aborted, and portal requests fall through to the
        # handler above. A test that reaches the network is a test that fails
        # offline, which is not a failure anyone can debug.
        if "www.linkedin.com" in route.request.url:
            await route.fallback()
        else:
            await route.abort()

    await context.route("https://www.linkedin.com/**", route_handler)
    await context.route("**/*", block_everything_else)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def _document(title: str, body: str, *, head: str = "") -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{escape(title)}</title>{head}</head><body>{body}</body></html>"
    )


def _feed_page(display_name: str) -> str:
    # `.global-nav__me` is the logged-in marker; the photo's alt is where
    # `read_display_name` gets the name from.
    return _document(
        "Feed | LinkedIn",
        f"""
        <nav aria-label="Primary Navigation">
          <div class="global-nav__me">
            <img class="global-nav__me-photo" alt="{escape(display_name)}"
                 src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==">
          </div>
        </nav>
        <main class="feed-identity-module"><p>Your feed</p></main>
        """,
    )


def _login_page() -> str:
    return _document(
        "Sign in | LinkedIn",
        """
        <form class="login__form">
          <input id="username" name="session_key" type="text">
          <input id="password" name="session_password" type="password">
          <button type="submit">Sign in</button>
        </form>
        """,
    )


def _checkpoint_page() -> str:
    """The page the automation must refuse to work around."""
    return _document(
        "Security Verification | LinkedIn",
        """
        <div class="challenge-dialog" data-test-id="challenge">
          <h1>Security verification</h1>
          <p>Let's do a quick security check to confirm it is you.</p>
        </div>
        """,
    )


def _search_page(jobs: list[PortalJob]) -> str:
    if not jobs:
        return _document(
            "Jobs | LinkedIn",
            '<div class="jobs-search-no-results-banner">No matching jobs found</div>',
        )

    cards = "".join(_result_card(job) for job in jobs)
    return _document(
        "Jobs | LinkedIn",
        f"""
        <div class="jobs-search-results-list" style="height:400px;overflow-y:auto">
          <ul class="jobs-search__results-list">{cards}</ul>
        </div>
        """,
    )


def _result_card(job: PortalJob) -> str:
    applied = (
        '<li class="job-card-container__footer-job-state">Applied</li>'
        if job.already_applied
        else ""
    )
    apply_method = (
        '<li class="job-card-container__apply-method">Easy Apply</li>'
        if job.easy_apply
        else '<li class="job-card-container__apply-method">Apply on company website</li>'
    )
    return f"""
    <li data-occludable-job-id="{escape(job.external_id)}"
        class="jobs-search-results__list-item">
      <div class="job-card-container" data-job-id="{escape(job.external_id)}">
        <a class="job-card-list__title" href="/jobs/view/{escape(job.external_id)}/">
          <strong>{escape(job.title)}</strong>
        </a>
        <div class="job-card-container__primary-description">{escape(job.company)}</div>
        <ul>
          <li class="job-card-container__metadata-item">{escape(job.location)}</li>
          <li class="job-card-container__metadata-item">{escape(job.workplace_text)}</li>
          {apply_method}
          {applied}
        </ul>
        <time datetime="2026-09-05">{escape(job.posted)}</time>
      </div>
    </li>
    """


def _job_page(job: PortalJob, steps: tuple[PortalStep, ...]) -> str:
    applied_banner = (
        '<div class="jobs-s-apply__application-submitted">Application submitted</div>'
        if job.already_applied
        else ""
    )
    apply_button = (
        '<div class="jobs-apply-button--top-card">'
        '<button class="jobs-apply-button" aria-label="Easy Apply" '
        'onclick="openModal()">Easy Apply</button></div>'
        if job.easy_apply
        else '<button class="jobs-apply-button" aria-label="Apply on company website">'
        "Apply</button>"
    )

    return _document(
        f"{job.title} | LinkedIn",
        f"""
        <div class="job-details-jobs-unified-top-card__job-title">
          <h1>{escape(job.title)}</h1>
        </div>
        <div class="job-details-jobs-unified-top-card__company-name">
          {escape(job.company)}
        </div>
        <div class="job-details-jobs-unified-top-card__primary-description-container">
          {escape(job.location)} · <time datetime="2026-09-05">{escape(job.posted)}</time>
        </div>
        <ul>
          <li class="job-details-jobs-unified-top-card__job-insight">
            {escape(job.workplace_text)}
          </li>
          <li class="job-details-jobs-unified-top-card__job-insight">Full-time</li>
        </ul>
        {applied_banner}
        {apply_button}
        <div id="job-details"><p>{escape(job.description)}</p></div>
        {_modal(job, steps)}
        """,
        head=f"<style>{_MODAL_CSS}</style><script>{_modal_script(job, steps)}</script>",
    )


def _modal(job: PortalJob, steps: tuple[PortalStep, ...]) -> str:
    # The step before the review step is the one that offers "Review your
    # application"; every earlier step offers "Continue to next step".
    last_input_index = max(
        (index for index, step in enumerate(steps) if not step.review), default=-1
    )
    rendered = "".join(
        _step(index, step, is_last_input_step=index == last_input_index)
        for index, step in enumerate(steps)
    )
    return f"""
    <div data-test-modal-id="easy-apply-modal" class="jobs-easy-apply-modal artdeco-modal"
         role="dialog" aria-label="Apply to {escape(job.company)}" hidden>
      <header class="artdeco-modal__header">
        <h2 id="jobs-apply-header">Apply to {escape(job.company)}</h2>
        <button class="artdeco-modal__dismiss" aria-label="Dismiss"
                onclick="dismissModal()">Dismiss</button>
      </header>
      <progress class="artdeco-completeness-meter-linear__progress-element"
                aria-label="application progress" value="25" max="100"></progress>
      <div class="artdeco-modal__content">
        <form class="jobs-easy-apply-form" onsubmit="return false">{rendered}</form>
        <div id="portal-errors"></div>
        <div id="portal-confirmation" hidden>
          <div class="jobs-easy-apply-confirmation">
            <h2>Your application was sent to {escape(job.company)}</h2>
          </div>
        </div>
        <div id="portal-discard" hidden>
          <p>Discard this application?</p>
          <button data-control-name="discard_application_confirm_btn"
                  onclick="confirmDiscard()">Discard</button>
        </div>
      </div>
    </div>
    """


def _step(index: int, step: PortalStep, *, is_last_input_step: bool) -> str:
    hidden = "" if index == 0 else " hidden"
    if step.review:
        return f"""
        <section class="portal-step" data-step="{index}"{hidden}>
          <h3>Review your application</h3>
          <p>Nothing has been sent yet.</p>
          <button aria-label="Submit application" onclick="submitApplication()">
            Submit application
          </button>
        </section>
        """

    body = "".join(_field(item) for item in step.fields)
    label = "Review your application" if is_last_input_step else "Continue to next step"
    return f"""
    <section class="portal-step" data-step="{index}"{hidden}>
      {body}
      <button aria-label="{label}" onclick="advance({index})">{label}</button>
    </section>
    """


def _field(item: PortalField) -> str:
    required_marker = ' <span aria-hidden="true">*</span>' if item.required else ""
    required_attr = " required" if item.required else ""

    if item.kind == "file":
        return f"""
        <div data-test-form-element class="fb-dash-form-element">
          <label for="{escape(item.field_id)}">{escape(item.label)}</label>
          <input id="{escape(item.field_id)}" type="file" class="js-jobs-document-upload__input"
                 onchange="onResumePicked()">
          <div class="jobs-document-upload-redesign-card__container"
               data-test-jobs-document-upload-redesign-card hidden>
            <span>resume.pdf</span>
          </div>
        </div>
        """

    if item.kind == "radio":
        options = "".join(
            f'<div><input id="{escape(item.field_id)}-{position}" type="radio" '
            f'name="{escape(item.field_id)}" value="{escape(option)}"{required_attr}>'
            f'<label for="{escape(item.field_id)}-{position}">{escape(option)}</label></div>'
            for position, option in enumerate(item.options)
        )
        return f"""
        <fieldset data-test-form-builder-radio-button-form-component
                  class="jobs-easy-apply-form-element__fieldset">
          <legend><span aria-hidden="true">{escape(item.label)}{required_marker}</span></legend>
          {options}
        </fieldset>
        """

    if item.kind == "select":
        options = "".join(
            f'<option value="{escape(option)}">{escape(option)}</option>'
            for option in item.options
        )
        control = (
            f'<select id="{escape(item.field_id)}"{required_attr}>{options}</select>'
        )
    elif item.kind == "textarea":
        control = f'<textarea id="{escape(item.field_id)}"{required_attr}></textarea>'
    elif item.kind == "checkbox":
        control = f'<input id="{escape(item.field_id)}" type="checkbox"{required_attr}>'
    else:
        input_type = "number" if item.kind == "number" else "text"
        control = (
            f'<input id="{escape(item.field_id)}" type="{input_type}" '
            f'class="artdeco-text-input--input" value="{escape(item.value)}"{required_attr}>'
        )

    return f"""
    <div data-test-form-element class="fb-dash-form-element">
      <label for="{escape(item.field_id)}">{escape(item.label)}{required_marker}</label>
      {control}
    </div>
    """


_MODAL_CSS = """
[hidden] { display: none !important; }
body { font: 14px system-ui, sans-serif; margin: 16px; }
.jobs-easy-apply-modal { border: 1px solid #ccc; padding: 12px; margin-top: 16px; }
.artdeco-inline-feedback--error { color: #b00; }
"""


def _modal_script(job: PortalJob, steps: tuple[PortalStep, ...]) -> str:
    """The modal's behaviour: step navigation, validation, submit.

    Written as one inline script because the portal serves no assets — every
    external request is aborted by `install()`, so a test can never depend on
    the network.
    """
    total = len(steps)
    return f"""
const TOTAL_STEPS = {total};
const JOB_ID = {json.dumps(job.external_id)};
const RECORD_URL = {json.dumps(f"https://www.linkedin.com{RECORD_SUBMIT_PATH}")};

function stepEl(index) {{
  return document.querySelector('.portal-step[data-step="' + index + '"]');
}}

function openModal() {{
  document.querySelector('[data-test-modal-id="easy-apply-modal"]').hidden = false;
  showStep(0);
}}

function showStep(index) {{
  document.querySelectorAll('.portal-step').forEach((section) => {{
    section.hidden = Number(section.dataset.step) !== index;
  }});
  const progress = document.querySelector('progress');
  progress.value = Math.round(((index + 1) / TOTAL_STEPS) * 100);
  clearErrors();
}}

function clearErrors() {{
  document.getElementById('portal-errors').innerHTML = '';
}}

function showError(message) {{
  document.getElementById('portal-errors').innerHTML =
    '<div class="artdeco-inline-feedback--error">' + message + '</div>';
}}

/* A required field left empty blocks the step, exactly as the real form does —
   that is the path `apply.py` reports as "blocked". */
function missingRequired(index) {{
  const section = stepEl(index);
  const missing = [];
  section.querySelectorAll('[required]').forEach((control) => {{
    if (control.type === 'radio') {{
      const group = section.querySelectorAll('input[name="' + control.name + '"]');
      const checked = Array.from(group).some((radio) => radio.checked);
      if (!checked && !missing.includes(control.name)) missing.push(control.name);
      return;
    }}
    const value = (control.value || '').trim();
    /* The select's placeholder counts as no answer. */
    const placeholder = control.tagName === 'SELECT' && value === 'Select an option';
    if (!value || placeholder) missing.push(control.id);
  }});
  return missing;
}}

function advance(index) {{
  const missing = missingRequired(index);
  if (missing.length > 0) {{
    showError('Please enter a valid answer. (' + missing.join(', ') + ')');
    return;
  }}
  showStep(Math.min(index + 1, TOTAL_STEPS - 1));
}}

function onResumePicked() {{
  const card = document.querySelector('.jobs-document-upload-redesign-card__container');
  if (card) card.hidden = false;
}}

function collectAnswers() {{
  const answers = {{}};
  document.querySelectorAll('.jobs-easy-apply-form input, .jobs-easy-apply-form select, '
    + '.jobs-easy-apply-form textarea').forEach((control) => {{
    if (control.type === 'file') return;
    if (control.type === 'radio') {{
      if (control.checked) answers[control.name] = control.value;
      return;
    }}
    if (control.type === 'checkbox') {{
      answers[control.id] = control.checked ? 'true' : 'false';
      return;
    }}
    answers[control.id] = control.value;
  }});
  return answers;
}}

/* Reached only by clicking "Submit application". The recorded call is what the
   test asserts on, so a stray click anywhere else in the codebase shows up. */
function submitApplication() {{
  const answers = encodeURIComponent(JSON.stringify(collectAnswers()));
  window.__portalSubmitted = true;
  fetch(RECORD_URL + '?id=' + encodeURIComponent(JOB_ID) + '&answers=' + answers);
  document.querySelector('.jobs-easy-apply-form').hidden = true;
  document.getElementById('portal-confirmation').hidden = false;
}}

function dismissModal() {{
  document.querySelector('.jobs-easy-apply-form').hidden = true;
  document.getElementById('portal-discard').hidden = false;
}}

function confirmDiscard() {{
  document.getElementById('portal-discard').hidden = true;
  document.querySelector('[data-test-modal-id="easy-apply-modal"]').hidden = true;
  const form = document.querySelector('.jobs-easy-apply-form');
  form.hidden = false;
  form.reset();
  showStep(0);
}}
"""


def render_job_page(job: PortalJob, steps: tuple[PortalStep, ...] | None = None) -> str:
    """Exposed for tests that want to assert on the markup itself."""
    return _job_page(job, steps or default_steps())


__all__ = [
    "CHECKPOINT_PATH",
    "RECORD_SUBMIT_PATH",
    "FakePortal",
    "PortalField",
    "PortalJob",
    "PortalStep",
    "default_steps",
    "install",
    "make_jobs",
    "multi_step_steps",
    "render_job_page",
]
