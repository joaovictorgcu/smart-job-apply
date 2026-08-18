"""Turning AI answers and the stored profile into form answers.

Pure functions over the contracts: no database, no browser, no engine state.
They decide what value goes into each field, where it came from, and whether a
human still has to look at it.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.schemas import ScreeningAnswer
from app.automation.contracts import ApplicationDraft, FormAnswer, FormQuestion, ProfileContext
from app.models import AnswerConfidence

_EMAIL_HINTS = ("email", "e-mail")
_PHONE_HINTS = ("phone", "telefone", "celular", "mobile")
_FIRST_NAME_HINTS = ("first name", "given name", "nome")
_LAST_NAME_HINTS = ("last name", "surname", "family name", "sobrenome")
_LOCATION_HINTS = ("city", "location", "cidade", "localidade", "where are you")
_EXPERIENCE_HINTS = ("years of experience", "anos de experiência", "anos de experiencia")
_FULL_NAME_HINTS = ("full name", "nome completo")


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


def _merge_draft_answers(
    records: list[dict[str, Any]], draft: ApplicationDraft
) -> list[dict[str, Any]]:
    """Reflect what actually landed in the form back into the stored answers."""
    filled = {answer.field_id for answer in draft.answers}
    unanswered = {question.field_id for question in draft.unanswered}
    known = {record["field_id"] for record in records}

    for record in records:
        record["filled"] = record["field_id"] in filled
        if record["field_id"] in unanswered:
            record["needs_review"] = True

    for question in draft.questions:
        if question.field_id in known:
            continue
        records.append(
            {
                "field_id": question.field_id,
                "question": question.label,
                "answer": question.current_value or "",
                "type": question.kind,
                "options": list(question.options),
                "required": question.required,
                "confidence": AnswerConfidence.LOW.value,
                "needs_review": True,
                "source": "form",
                "filled": question.field_id in filled,
            }
        )
    return records


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
