"""Easy Apply modal driver.

Hard rule of this module: it fills the form, advances through the steps, and
**stops at the review step**. It never clicks "Submit application" — that button
is only ever used by `submit()`, which the engine calls once, after the user has
explicitly approved the draft. `fill_and_advance` does not even look up the
submit selector except to recognise that the review step has been reached.
"""

from __future__ import annotations

import random
import re
from contextlib import suppress
from dataclasses import dataclass

from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    Locator,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from app.automation import selectors as sel
from app.automation.browser import BrowserSession
from app.automation.contracts import (
    ApplicationDraft,
    FormAnswer,
    FormQuestion,
    QuestionKind,
)
from app.automation.errors import (
    AlreadyAppliedError,
    EasyApplyUnavailableError,
    ElementNotFoundError,
    UnexpectedPageError,
)
from app.automation.linkedin.job import JobDetailPage
from app.automation.linkedin.search import clean_text
from app.automation.throttle import Throttle
from app.observability import get_logger

logger = get_logger(__name__)

# LinkedIn's Easy Apply flow is 2-6 steps in practice; the bound stops a loop
# caused by a step that never advances.
_MAX_STEPS = 12
_REQUIRED_HINTS = ("required", "obrigatório", "obrigatorio")
_TRUTHY = {"true", "yes", "y", "1", "sim", "on", "checked"}

# Every fillable control, in DOM order. File inputs are handled separately by
# `_attach_resume`; buttons and hidden inputs are not questions.
_CONTROL_SELECTOR = (
    'input:not([type="file"]):not([type="hidden"]):not([type="submit"]):not([type="button"])'
    ", select, textarea"
)

# Nearest ancestor that carries a question's label or legend.
_GROUP_ANCESTOR_XPATH = (
    "ancestor::*[self::fieldset or @data-test-form-element"
    " or contains(@class,'fb-dash-form-element')"
    " or contains(@class,'jobs-easy-apply-form-section__grouping')][1]"
)


@dataclass(slots=True)
class _Field:
    """A form control on the current step, paired with its question."""

    question: FormQuestion
    control: Locator
    # For radio groups, `control` is the fieldset and options are resolved by label.
    group: Locator


class EasyApplyModal:
    """Page object for the Easy Apply dialog."""

    def __init__(
        self,
        browser: BrowserSession,
        throttle: Throttle | None = None,
        *,
        resume_path: str | None = None,
    ) -> None:
        self._browser = browser
        self._throttle = throttle or Throttle()
        self._job = JobDetailPage(browser, self._throttle)
        self.resume_path = resume_path
        self._external_id: str | None = None
        self._fields: dict[str, _Field] = {}
        self._is_open = False

    # --- State ------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def job_external_id(self) -> str | None:
        return self._external_id

    async def _modal(self) -> Locator:
        try:
            return await self._browser.find_first(
                sel.EasyApply.MODAL, name="Easy Apply modal", timeout=8_000
            )
        except ElementNotFoundError:
            self._is_open = False
            raise

    # --- Opening ----------------------------------------------------------

    async def open(self, external_id: str) -> list[FormQuestion]:
        """Open the modal for one job and return the first step's fields."""
        await self._job.open(external_id)

        if await self._browser.any_visible(sel.JobDetail.APPLIED_BANNER, timeout=1_500):
            raise AlreadyAppliedError(
                f"LinkedIn reports an application already exists for job {external_id}."
            )

        button = await self._browser.find_first_or_none(
            sel.JobDetail.EASY_APPLY_BUTTON, timeout=4_000
        )
        if button is None:
            raise EasyApplyUnavailableError(f"Job {external_id} does not offer Easy Apply.")
        try:
            label = (await button.get_attribute("aria-label")) or await button.inner_text()
        except (PlaywrightError, PlaywrightTimeoutError):
            label = ""
        normalized = (label or "").lower()
        if "easy apply" not in normalized and "candidatura simplificada" not in normalized:
            raise EasyApplyUnavailableError(
                f"Job {external_id} only offers an external application flow."
            )

        await self._throttle.human_pause(self._browser.page)
        try:
            await button.click(timeout=8_000)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            raise UnexpectedPageError(
                f"Could not open the Easy Apply modal for job {external_id}: {exc}",
                url=self._browser.current_url,
            ) from exc

        await self._browser.raise_if_blocked()
        await self._modal()
        self._is_open = True
        self._external_id = external_id
        await self._throttle.wait_action()

        questions = await self.read_questions()
        logger.info(
            "Easy Apply modal opened.",
            extra={
                "action": "apply.open",
                "status": "ok",
                "external_id": external_id,
                "fields": len(questions),
            },
        )
        return questions

    # --- Reading the current step ----------------------------------------

    async def read_questions(self) -> list[FormQuestion]:
        """Enumerate the fields of the step currently on screen.

        The walk starts from the controls rather than from group wrappers: the
        wrappers differ between LinkedIn's A/B variants (and radio groups are
        fieldsets, not the usual div), while `input`/`select`/`textarea` is
        invariant. Only visible controls count — the modal keeps hidden inputs
        around, and a later step's fields must not leak into this one.
        """
        modal = await self._modal()
        self._fields = {}
        questions: list[FormQuestion] = []
        seen_radio_groups: set[str] = set()

        for index, control in enumerate(await self._controls(modal)):
            field = await self._describe_control(modal, control, index, seen_radio_groups)
            if field is None:
                continue
            # A duplicated field_id would make filling ambiguous; keep the first.
            if field.question.field_id in self._fields:
                continue
            self._fields[field.question.field_id] = field
            questions.append(field.question)

        return questions

    @staticmethod
    async def _controls(modal: Locator) -> list[Locator]:
        try:
            return await modal.locator(_CONTROL_SELECTOR).all()
        except PlaywrightError:
            return []

    async def _describe_control(
        self, modal: Locator, control: Locator, index: int, seen_radio_groups: set[str]
    ) -> _Field | None:
        try:
            tag = (await control.evaluate("node => node.tagName")).lower()
            input_type = ((await control.get_attribute("type")) or "").lower()
            element_id = (await control.get_attribute("id")) or ""
        except PlaywrightError:
            return None

        # LinkedIn pre-checks "follow this company"; that is the user's choice, not ours.
        if "follow-company" in element_id:
            return None

        group = await self._enclosing_group(control)
        scope = group or modal

        if not await self._is_on_screen(modal, control, input_type, element_id, group):
            return None

        if input_type == "radio":
            name = (await control.get_attribute("name")) or f"group:{index}"
            if name in seen_radio_groups:
                return None
            seen_radio_groups.add(name)
            return await self._describe_radio_group(modal, group, scope, name, index)

        kind: QuestionKind
        if tag == "textarea":
            kind = "textarea"
        elif tag == "select":
            kind = "select"
        elif input_type == "number":
            kind = "number"
        elif input_type == "checkbox":
            kind = "checkbox"
        else:
            kind = "text"

        label = await self._label_for(modal, scope, control, element_id)
        options = await self._select_options(control) if kind == "select" else []
        question = FormQuestion(
            field_id=element_id or (await control.get_attribute("name")) or f"field:{index}",
            label=label or f"Field {index + 1}",
            kind=kind,
            options=options,
            required=await self._is_required(group, control, label),
            current_value=await self._current_value(control, kind),
        )
        return _Field(question=question, control=control, group=scope)

    async def _describe_radio_group(
        self, modal: Locator, group: Locator | None, scope: Locator, name: str, index: int
    ) -> _Field | None:
        radios = scope.locator(sel.EasyApply.RADIO_INPUT[0])
        options: list[str] = []
        checked: str | None = None
        try:
            for radio in await radios.all():
                text = await self._radio_option_label(scope, radio)
                if text:
                    options.append(text)
                    if await radio.is_checked():
                        checked = text
        except PlaywrightError:
            return None

        legend = await self._first_text(scope, ("css=legend", "css=label"))
        if not legend.strip():
            legend = await self._first_text(modal, (f'label[for="{name}"]',))
        question = FormQuestion(
            field_id=name,
            label=_strip_required_marker(clean_text(legend)) or f"Field {index + 1}",
            kind="radio",
            options=options,
            required=await self._is_required(group, radios.first, legend),
            current_value=checked,
        )
        return _Field(question=question, control=radios, group=scope)

    async def _is_on_screen(
        self,
        modal: Locator,
        control: Locator,
        input_type: str,
        element_id: str,
        group: Locator | None,
    ) -> bool:
        """Is this control part of the step the user is looking at?

        The modal keeps other steps' inputs in the DOM, so hidden controls must be
        ignored. Radios and checkboxes are the exception: LinkedIn hides the input
        itself and shows a styled label, so their visibility is judged from the
        label or the wrapper instead.
        """
        try:
            if await control.is_visible():
                return True
            if input_type not in {"radio", "checkbox"}:
                return False
            if element_id:
                label = modal.locator(f'label[for="{element_id}"]')
                if await label.count() and await label.first.is_visible():
                    return True
            return group is not None and await group.is_visible()
        except PlaywrightError:
            return False

    @staticmethod
    async def _enclosing_group(control: Locator) -> Locator | None:
        """Nearest wrapper that carries the question's label/legend."""
        try:
            ancestor = control.locator(f"xpath={_GROUP_ANCESTOR_XPATH}")
            if await ancestor.count():
                return ancestor.first
        except PlaywrightError:
            pass
        return None

    async def _label_for(
        self, modal: Locator, group: Locator, control: Locator, element_id: str
    ) -> str:
        # `label[for=...]` is the most reliable link between a control and its text.
        if element_id:
            text = await self._first_text(modal, (f'label[for="{element_id}"]',))
            if text.strip():
                return _strip_required_marker(clean_text(text))

        text = await self._first_text(group, sel.EasyApply.GROUP_LABEL)
        if text.strip():
            return _strip_required_marker(clean_text(text))

        for attribute in ("aria-label", "placeholder", "name", "id"):
            try:
                value = await control.get_attribute(attribute)
            except PlaywrightError:
                value = None
            if value:
                return _strip_required_marker(clean_text(value))
        return ""

    async def _radio_option_label(self, group: Locator, radio: Locator) -> str:
        try:
            radio_id = await radio.get_attribute("id")
            if radio_id:
                label = group.locator(f'label[for="{radio_id}"]')
                if await label.count():
                    return clean_text(await label.first.inner_text(timeout=1_500))
            value = await radio.get_attribute("value")
            return clean_text(value or "")
        except (PlaywrightError, PlaywrightTimeoutError):
            return ""

    async def _select_options(self, control: Locator) -> list[str]:
        try:
            texts = await control.locator("option").all_inner_texts()
        except PlaywrightError:
            return []
        options = [clean_text(text) for text in texts]
        # LinkedIn's first option is a "Select an option" placeholder.
        return [option for option in options if option and not _is_placeholder(option)]

    async def _is_required(self, group: Locator | None, control: Locator, label: str) -> bool:
        for attribute in ("required", "aria-required"):
            try:
                value = await control.get_attribute(attribute)
            except PlaywrightError:
                value = None
            if value is not None and value.lower() not in {"false", "0"}:
                return True
        haystack = (label or "").lower()
        # Only a per-question wrapper may be scanned for the "*" marker; scanning
        # the whole modal would mark every field as required.
        if group is not None:
            with suppress(PlaywrightError, PlaywrightTimeoutError):
                haystack = f"{haystack} {(await group.inner_text(timeout=1_500)).lower()}"
        return "*" in haystack or any(hint in haystack for hint in _REQUIRED_HINTS)

    async def _current_value(self, control: Locator, kind: QuestionKind) -> str | None:
        try:
            if kind == "checkbox":
                return "true" if await control.is_checked() else "false"
            value = await control.input_value(timeout=1_500)
        except (PlaywrightError, PlaywrightTimeoutError):
            return None
        return value or None

    async def _first_text(self, root: Locator, selectors: tuple[str, ...]) -> str:
        for selector in selectors:
            try:
                locator = root.locator(selector).first
                if await locator.count():
                    text = await locator.inner_text(timeout=1_500)
                    if text.strip():
                        return text
            except (PlaywrightError, PlaywrightTimeoutError):
                continue
        return ""

    # --- Filling ----------------------------------------------------------

    async def fill_and_advance(
        self, answers: list[FormAnswer], *, cover_letter: str | None = None
    ) -> ApplicationDraft:
        """Fill every step we can and stop at the review step. Never submits."""
        if not self._is_open or self._external_id is None:
            raise UnexpectedPageError("The Easy Apply modal is not open.")

        draft = ApplicationDraft(job_external_id=self._external_id)
        pending = {answer.field_id: answer for answer in answers}
        by_label = {_normalize(answer.field_id): answer for answer in answers if answer.field_id}
        seen_ids: set[str] = set()
        cover_letter_pending = cover_letter

        for step in range(1, _MAX_STEPS + 1):
            await self._browser.raise_if_blocked()
            questions = await self.read_questions()
            for question in questions:
                if question.field_id not in seen_ids:
                    seen_ids.add(question.field_id)
                    draft.questions.append(question)

            if await self._attach_resume(draft):
                await self._throttle.wait_action()

            filled_elsewhere: set[str] = set()
            if cover_letter_pending:
                cover_field = await self._fill_cover_letter(cover_letter_pending, questions)
                if cover_field:
                    draft.cover_letter_attached = True
                    draft.answers.append(
                        FormAnswer(
                            field_id=cover_field, value=cover_letter_pending, kind="textarea"
                        )
                    )
                    filled_elsewhere.add(cover_field)
                    cover_letter_pending = None

            step_unanswered = await self._fill_step(
                questions, pending, by_label, draft, filled_elsewhere
            )
            draft.unanswered.extend(step_unanswered)

            current, total = await self._read_progress(step)
            draft.current_step = current
            draft.total_steps = total

            blocking = [question for question in step_unanswered if question.required]
            if blocking:
                draft.notes.append(
                    f"Stopped on step {step}: "
                    f"{len(blocking)} required field(s) need a human answer."
                )
                draft.ready_to_submit = False
                draft.screenshot_path = await self._browser.screenshot(
                    f"easyapply-{self._external_id}-needs-input"
                )
                logger.warning(
                    "Easy Apply paused: required fields could not be answered.",
                    extra={
                        "action": "apply.fill",
                        "status": "needs_input",
                        "external_id": self._external_id,
                        "step": step,
                        "fields": [question.label for question in blocking],
                    },
                )
                return draft

            advanced = await self._advance()
            if advanced == "review":
                draft.ready_to_submit = True
                draft.notes.append(
                    "Review step reached; the application is filled and waiting for approval."
                )
                draft.screenshot_path = await self._browser.screenshot(
                    f"easyapply-{self._external_id}-review"
                )
                logger.info(
                    "Easy Apply stopped at the review step.",
                    extra={
                        "action": "apply.fill",
                        "status": "awaiting_review",
                        "external_id": self._external_id,
                        "step": step,
                    },
                )
                return draft

            if advanced == "blocked":
                errors = await self._validation_errors()
                draft.notes.append(
                    "The form rejected the current step: " + ("; ".join(errors) or "unknown reason")
                )
                draft.ready_to_submit = False
                draft.screenshot_path = await self._browser.screenshot(
                    f"easyapply-{self._external_id}-validation"
                )
                return draft

            await self._throttle.wait_action()

        draft.notes.append(f"Gave up after {_MAX_STEPS} steps without reaching the review step.")
        draft.screenshot_path = await self._browser.screenshot(
            f"easyapply-{self._external_id}-stalled"
        )
        return draft

    async def _fill_step(
        self,
        questions: list[FormQuestion],
        pending: dict[str, FormAnswer],
        by_label: dict[str, FormAnswer],
        draft: ApplicationDraft,
        already_filled: set[str],
    ) -> list[FormQuestion]:
        unanswered: list[FormQuestion] = []
        for question in questions:
            if question.field_id in already_filled:
                continue
            # `field_id` doubles as the question text when the caller could not
            # know the real DOM id, so fall back to matching on the label.
            answer = pending.pop(question.field_id, None) or by_label.get(
                _normalize(question.label)
            )
            if answer is None or not answer.value.strip():
                if not (question.current_value or "").strip():
                    unanswered.append(question)
                continue

            field = self._fields.get(question.field_id)
            if field is None:
                unanswered.append(question)
                continue

            if await self._apply_value(field, answer.value):
                draft.answers.append(
                    FormAnswer(field_id=question.field_id, value=answer.value, kind=question.kind)
                )
            else:
                unanswered.append(question)
        return unanswered

    async def _apply_value(self, field: _Field, value: str) -> bool:
        kind = field.question.kind
        try:
            if kind in {"text", "number", "textarea"}:
                return await self._type_value(field.control, value, typeahead=kind == "text")
            if kind == "select":
                return await self._select_value(field.control, value, field.question.options)
            if kind == "radio":
                return await self._choose_radio(field, value)
            if kind == "checkbox":
                wanted = _normalize(value) in _TRUTHY
                await field.control.set_checked(wanted, timeout=5_000)
                return True
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            logger.warning(
                "Could not fill a form field.",
                extra={
                    "action": "apply.fill_field",
                    "status": "failed",
                    "field": field.question.label,
                    "kind": kind,
                    "error": str(exc),
                },
            )
        return False

    async def _type_value(self, control: Locator, value: str, *, typeahead: bool) -> bool:
        await control.scroll_into_view_if_needed(timeout=4_000)
        await control.click(timeout=5_000)
        await control.fill("", timeout=5_000)
        # Character-by-character entry, so the field does not receive a whole
        # paragraph in a single tick like a script would.
        await control.press_sequentially(value, delay=random.uniform(18, 55), timeout=30_000)
        if typeahead:
            await self._accept_typeahead()
        return True

    async def _accept_typeahead(self) -> None:
        """Pick the first suggestion when LinkedIn opens a typeahead dropdown."""
        container = await self._browser.find_first_or_none(
            sel.EasyApply.TYPEAHEAD_CONTAINER, timeout=1_200
        )
        if container is None:
            return
        for selector in sel.EasyApply.TYPEAHEAD_OPTION:
            try:
                option = container.locator(selector).first
                if await option.count():
                    await option.click(timeout=2_500)
                    return
            except (PlaywrightError, PlaywrightTimeoutError):
                continue

    async def _select_value(self, control: Locator, value: str, options: list[str]) -> bool:
        for attempt in ({"label": value}, {"value": value}):
            try:
                await control.select_option(timeout=5_000, **attempt)
                return True
            except (PlaywrightError, PlaywrightTimeoutError):
                continue
        match = _closest(value, options)
        if match is None:
            return False
        try:
            await control.select_option(label=match, timeout=5_000)
            return True
        except (PlaywrightError, PlaywrightTimeoutError):
            return False

    async def _choose_radio(self, field: _Field, value: str) -> bool:
        wanted = _normalize(value)
        radios = await field.control.all()
        labels = [await self._radio_option_label(field.group, radio) for radio in radios]
        index = _match_index(wanted, labels)
        if index is None:
            return False

        radio = radios[index]
        radio_id = await radio.get_attribute("id")
        # LinkedIn hides the input itself; the clickable target is its label.
        if radio_id:
            label = field.group.locator(f'label[for="{radio_id}"]')
            if await label.count():
                await label.first.click(timeout=5_000)
                return True
        await radio.check(timeout=5_000, force=True)
        return True

    async def _attach_resume(self, draft: ApplicationDraft) -> bool:
        """Upload the resume when this step asks for a file and none is attached."""
        modal = await self._modal()
        if await self._browser.any_visible(sel.EasyApply.RESUME_CARD, root=modal, timeout=1_000):
            draft.resume_attached = True
            return False

        file_input: Locator | None = None
        for selector in sel.EasyApply.FILE_INPUT:
            try:
                locator = modal.locator(selector)
                if await locator.count():
                    file_input = locator.first
                    break
            except PlaywrightError:
                continue
        if file_input is None:
            return False

        if not self.resume_path:
            draft.notes.append("This step asks for a resume file but no resume is on file.")
            return False

        try:
            await file_input.set_input_files(self.resume_path, timeout=15_000)
        except (PlaywrightError, PlaywrightTimeoutError, ValueError) as exc:
            draft.notes.append(f"Resume upload failed: {exc}")
            return False

        draft.resume_attached = True
        logger.info(
            "Resume uploaded to the Easy Apply form.",
            extra={"action": "apply.resume", "status": "ok", "external_id": self._external_id},
        )
        return True

    async def _fill_cover_letter(self, content: str, questions: list[FormQuestion]) -> str | None:
        """Paste the cover letter into the free-text box; return the field used.

        Pasted rather than typed: a letter is hundreds of characters and
        `press_sequentially` would spend minutes on a single field.
        """
        candidates = [
            question
            for question in questions
            if question.kind == "textarea"
            and any(
                marker in _normalize(question.label) for marker in sel.EasyApply.COVER_LETTER_LABELS
            )
        ]
        if not candidates:
            candidates = [question for question in questions if question.kind == "textarea"]
        if not candidates:
            return None

        field = self._fields.get(candidates[0].field_id)
        if field is None:
            return None
        try:
            await field.control.scroll_into_view_if_needed(timeout=4_000)
            await field.control.fill(content, timeout=10_000)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            logger.warning(
                "Could not paste the cover letter.",
                extra={"action": "apply.cover_letter", "status": "failed", "error": str(exc)},
            )
            return None
        return field.question.field_id

    # --- Step navigation --------------------------------------------------

    async def _advance(self) -> str:
        """Click Next/Review. Returns "next", "review" or "blocked".

        The submit button is only *detected* here to recognise the review step;
        it is never clicked.
        """
        modal = await self._modal()
        next_button = await self._browser.find_first_or_none(
            sel.EasyApply.NEXT_BUTTON, root=modal, timeout=1_500
        )
        review_button = (
            None
            if next_button is not None
            else await self._browser.find_first_or_none(
                sel.EasyApply.REVIEW_BUTTON, root=modal, timeout=1_500
            )
        )
        target = next_button or review_button

        if target is None:
            at_review = await self._browser.any_visible(
                sel.EasyApply.SUBMIT_BUTTON, root=modal, timeout=1_500
            )
            if at_review:
                return "review"
            raise UnexpectedPageError(
                "The Easy Apply modal shows neither a next step nor a review step.",
                url=self._browser.current_url,
            )

        await self._throttle.human_pause(self._browser.page)
        try:
            await target.click(timeout=8_000)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            raise UnexpectedPageError(
                f"Could not advance the Easy Apply form: {exc}", url=self._browser.current_url
            ) from exc

        await self._throttle.wait_action()
        await self._browser.raise_if_blocked()

        if await self._validation_errors():
            return "blocked"
        if await self._browser.any_visible(
            sel.EasyApply.SUBMIT_BUTTON, root=await self._modal(), timeout=1_500
        ):
            return "review"
        return "next"

    async def _validation_errors(self) -> list[str]:
        modal = await self._modal()
        messages: list[str] = []
        for selector in sel.EasyApply.VALIDATION_ERROR:
            try:
                locator = modal.locator(selector)
                if not await locator.count():
                    continue
                for text in await locator.all_inner_texts():
                    cleaned = clean_text(text)
                    if cleaned:
                        messages.append(cleaned)
            except PlaywrightError:
                continue
        return list(dict.fromkeys(messages))

    async def _read_progress(self, fallback_step: int) -> tuple[int, int | None]:
        """Read the modal's progress meter.

        LinkedIn reports a completion *percentage*, not a step count, so the total
        is an estimate derived from it and the step we are actually on.
        """
        modal = await self._modal()
        percent: float | None = None
        for selector in sel.EasyApply.PROGRESS:
            try:
                locator = modal.locator(selector).first
                if not await locator.count():
                    continue
                for attribute in ("aria-valuenow", "value"):
                    raw = await locator.get_attribute(attribute)
                    if raw:
                        percent = float(raw)
                        break
                maximum: float | None = None
                for attribute in ("aria-valuemax", "max"):
                    raw = await locator.get_attribute(attribute)
                    if raw:
                        maximum = float(raw)
                        break
                if percent is not None and maximum:
                    percent = percent / maximum * 100.0
                break
            except (PlaywrightError, PlaywrightTimeoutError, ValueError):
                continue

        if percent is None or percent <= 0:
            return fallback_step, None
        estimated_total = max(fallback_step, round(fallback_step * 100.0 / percent))
        return fallback_step, min(estimated_total, _MAX_STEPS)

    # --- Terminal actions -------------------------------------------------

    async def submit(self) -> bool:
        """Click "Submit application".

        The ONLY place in the codebase that touches this button. The engine calls
        it after checking that the user approved this specific application.
        """
        if not self._is_open:
            raise UnexpectedPageError("The Easy Apply modal is not open; nothing to submit.")

        modal = await self._modal()
        button = await self._browser.find_first_or_none(
            sel.EasyApply.SUBMIT_BUTTON, root=modal, timeout=4_000
        )
        if button is None:
            raise UnexpectedPageError(
                "The submit button is not present — the form is not on the review step.",
                url=self._browser.current_url,
            )

        await self._throttle.human_pause(self._browser.page)
        try:
            await button.click(timeout=10_000)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            raise UnexpectedPageError(
                f"Could not click the submit button: {exc}", url=self._browser.current_url
            ) from exc

        await self._throttle.wait_action()
        await self._browser.raise_if_blocked()
        confirmed = await self._browser.any_visible(
            sel.EasyApply.SUBMIT_CONFIRMATION, timeout=8_000
        )
        self._is_open = False
        self._fields = {}
        await self._dismiss()

        logger.info(
            "Application submitted.",
            extra={
                "action": "apply.submit",
                "status": "ok" if confirmed else "unconfirmed",
                "external_id": self._external_id,
            },
        )
        return confirmed

    async def discard(self) -> None:
        """Close the modal and confirm LinkedIn's "Discard" prompt."""
        try:
            await self._dismiss()
            discard = await self._browser.find_first_or_none(
                sel.EasyApply.DISCARD_BUTTON, timeout=3_000
            )
            if discard is not None:
                await discard.click(timeout=5_000)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            logger.warning(
                "Could not cleanly discard the Easy Apply draft.",
                extra={"action": "apply.discard", "status": "failed", "error": str(exc)},
            )
        finally:
            self._is_open = False
            self._fields = {}
            self._external_id = None

    async def _dismiss(self) -> None:
        close = await self._browser.find_first_or_none(sel.EasyApply.CLOSE_BUTTON, timeout=2_500)
        if close is None:
            return
        with suppress(PlaywrightError, PlaywrightTimeoutError):
            await close.click(timeout=5_000)


def _normalize(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _strip_required_marker(label: str) -> str:
    """LinkedIn appends a bare "*" to required labels; it is not part of the question."""
    return label.rstrip().removesuffix("*").rstrip()


def _is_placeholder(option: str) -> bool:
    normalized = _normalize(option)
    return normalized in {
        "select an option",
        "selecione uma opção",
        "selecione uma opcao",
        "-",
        "",
    }


def _match_index(wanted: str, labels: list[str]) -> int | None:
    """Exact, then prefix, then containment match over option labels."""
    normalized = [_normalize(label) for label in labels]
    if wanted in normalized:
        return normalized.index(wanted)
    for index, label in enumerate(normalized):
        if label and (label.startswith(wanted) or wanted.startswith(label)):
            return index
    for index, label in enumerate(normalized):
        if label and (wanted in label or label in wanted):
            return index
    return None


def _closest(value: str, options: list[str]) -> str | None:
    index = _match_index(_normalize(value), options)
    return options[index] if index is not None else None
