"""Turning AI answers and the stored profile into form answers.

Pure functions over the contracts: no database, no browser, no engine state.
They decide what value goes into each field, where it came from, and whether a
human still has to look at it.

The second half of the module serves the submit path, which re-opens the form
the user reviewed and has to prove it is still the same one: `_form_fingerprint`
hashes a form's shape, `_approved_answers` rebuilds the values to type from the
records the user approved, and `_describe_form_change` turns a hash mismatch
into something a human can act on.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from typing import Any

from app.ai.schemas import ScreeningAnswer
from app.automation.contracts import FormAnswer, FormQuestion, ProfileContext
from app.automation.selectors import EasyApply
from app.models import AnswerConfidence

_EMAIL_HINTS = ("email", "e-mail")
_PHONE_HINTS = ("phone", "telefone", "celular", "mobile")
_FIRST_NAME_HINTS = ("first name", "given name", "nome")
_LAST_NAME_HINTS = ("last name", "surname", "family name", "sobrenome")
_LOCATION_HINTS = ("city", "location", "cidade", "localidade", "where are you")
_EXPERIENCE_HINTS = ("years of experience", "anos de experiência", "anos de experiencia")
_FULL_NAME_HINTS = ("full name", "nome completo")


def is_cover_letter_field(question: FormQuestion) -> bool:
    """Whether this field is the form's cover-letter box.

    It has to be told apart from a screening question because two different
    parts of the system want it, and only one of them should get it. The
    cover-letter generator writes it and `EasyApplyModal._fill_cover_letter`
    types it in; the screening model has no sensible answer to "Cover letter"
    phrased as a question and correctly flags it for review.

    Left in the screening set, that flag sets `needs_human_input` and disables
    approval on *every* posting whose form has such a box — which is most of
    them. The gate then fires for a field that was already filled, which
    teaches the operator to ignore it.

    Matched on a free-text field whose label names a cover letter, using the
    same label list the modal matches on, so the two stay in agreement.
    """
    if question.kind not in {"textarea", "text"}:
        return False
    label = _normalize(question.label)
    return any(marker in label for marker in EasyApply.COVER_LETTER_LABELS)


def _build_answers(
    questions: list[FormQuestion],
    screening: list[ScreeningAnswer],
    profile: ProfileContext,
) -> tuple[list[FormAnswer], list[dict[str, Any]]]:
    """Match AI answers to the real fields, filling the rest from the profile."""
    by_field = {answer.field_id: answer for answer in screening if answer.field_id}
    by_text = {_normalize(answer.question): answer for answer in screening}

    form_answers: list[FormAnswer] = []
    records: list[dict[str, Any]] = []

    for question in questions:
        answer = by_field.get(question.field_id) or by_text.get(_normalize(question.label))
        value = answer.answer.strip() if answer and answer.answer else ""
        confidence = answer.confidence if answer else AnswerConfidence.LOW
        needs_review = answer.needs_review if answer else True
        source = "ai" if value else "none"

        if not value:
            fallback = _answer_from_profile(question, profile)
            if fallback:
                value = fallback
                confidence = AnswerConfidence.MEDIUM
                needs_review = False
                source = "profile"

        if value:
            # `field_id` doubles as the label when the AI could not echo a real id;
            # `EasyApplyModal` falls back to label matching in that case.
            form_answers.append(
                FormAnswer(field_id=question.field_id, value=value, kind=question.kind)
            )
        else:
            needs_review = True

        records.append(
            {
                "field_id": question.field_id,
                "question": question.label,
                "answer": value,
                "type": question.kind,
                "options": list(question.options),
                "required": question.required,
                "confidence": AnswerConfidence(confidence).value,
                "needs_review": bool(needs_review or (question.required and not value)),
                "source": source,
            }
        )

    return form_answers, records


def _form_fingerprint(questions: Sequence[FormQuestion]) -> str:
    """Hash the *shape* of a form: which questions it asks, not how we answered.

    Only what a reviewer would have read counts — the label, the options offered
    and whether an answer is required — so re-rendering the same form in a
    different order is not a change, while a new required question is. The payload
    is JSON rather than `repr`, because this hash is compared against one computed
    in another process, possibly days later.

    `field_id` is deliberately excluded. It is the control's DOM id, and LinkedIn's
    Easy Apply ids embed a per-form-instance URN, so re-opening the same posting
    can hand back different ids for the same questions. Hashing them would refuse
    every real submission while protecting nothing: the reviewer never saw a DOM
    id, and `_approved_answers` already falls back to matching on the label when an
    id has moved.
    """
    shape = sorted(
        [question.label, sorted(question.options), bool(question.required)]
        for question in questions
    )
    payload = json.dumps(shape, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _approved_answers(
    questions: Sequence[FormQuestion], records: Sequence[dict[str, Any]]
) -> list[FormAnswer]:
    """Rebuild what to type from the answer records the user approved.

    Every value comes from storage: nothing is re-drafted, re-inferred or asked
    of the model at submit time, so what the human read is what gets typed. Only
    the field kind is taken from the freshly opened form, which reconciliation
    has already proved identical to the reviewed one.
    """
    by_field: dict[str, str] = {}
    by_text: dict[str, str] = {}
    for record in records:
        value = str(record.get("answer") or "").strip()
        if not value:
            continue
        field_id = str(record.get("field_id") or "")
        if field_id:
            by_field.setdefault(field_id, value)
        label = _normalize(str(record.get("question") or ""))
        if label:
            by_text.setdefault(label, value)

    answers: list[FormAnswer] = []
    for question in questions:
        # Same fallback as `_build_answers`: a record may only know the label.
        approved = by_field.get(question.field_id) or by_text.get(_normalize(question.label))
        if approved:
            answers.append(
                FormAnswer(field_id=question.field_id, value=approved, kind=question.kind)
            )
    return answers


def _describe_form_change(
    questions: Sequence[FormQuestion], records: Sequence[dict[str, Any]]
) -> str:
    """Name how a re-opened form differs from the one the records were written for.

    Best effort, and deliberately powerless: the refusal is decided by the
    server-side fingerprint. This only turns that hash mismatch into a sentence,
    and it reads `screening_answers`, which the review UI overwrites — so it may
    describe the difference imprecisely, and must never be allowed to hide one.
    """
    reviewed = {_normalize(str(record.get("question") or "")) for record in records}
    current = {_normalize(question.label) for question in questions}
    added = sorted(
        question.label for question in questions if _normalize(question.label) not in reviewed
    )
    removed = sorted(
        str(record.get("question") or "")
        for record in records
        if _normalize(str(record.get("question") or "")) not in current
    )

    parts: list[str] = []
    if added:
        parts.append(f"new question(s): {', '.join(added)}")
    if removed:
        parts.append(f"question(s) gone: {', '.join(removed)}")
    if not parts:
        parts.append("the same questions now have different options or requirements")
    return "; ".join(parts)


def _answer_from_profile(question: FormQuestion, profile: ProfileContext) -> str | None:
    """Deterministic answers for the fields we can fill without the AI."""
    label = _normalize(question.label)

    if any(hint in label for hint in _EMAIL_HINTS) and profile.email:
        return profile.email
    if any(hint in label for hint in _PHONE_HINTS) and profile.phone:
        return profile.phone
    if any(hint in label for hint in _FULL_NAME_HINTS) and profile.full_name:
        return profile.full_name
    if any(hint in label for hint in _FIRST_NAME_HINTS) and profile.full_name:
        return profile.full_name.split()[0]
    if any(hint in label for hint in _LAST_NAME_HINTS) and profile.full_name:
        parts = profile.full_name.split()
        return parts[-1] if len(parts) > 1 else None
    if any(hint in label for hint in _LOCATION_HINTS) and profile.location:
        return profile.location
    if any(hint in label for hint in _EXPERIENCE_HINTS) and profile.years_of_experience is not None:
        return str(profile.years_of_experience)

    # Saved answers for recurring screening questions.
    for key, value in profile.answer_bank.items():
        normalized_key = _normalize(str(key).replace("_", " "))
        if not normalized_key or not isinstance(value, (str, int, float)):
            continue
        if normalized_key in label or label in normalized_key:
            return str(value)
    return None


def _normalize(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())
