"""Prompt for answering Easy Apply screening questions.

A wrong answer here is sent to a real employer under the candidate's name, so the
prompt is built around one rule: when the profile does not contain the answer, say
so instead of inventing one.
"""

from __future__ import annotations

import json

from app.ai.prompts import (
    UNTRUSTED_TEXT_RULE,
    JobLike,
    render_job_block,
    render_profile_block,
)
from app.automation.contracts import FormQuestion, ProfileContext

SCREENING_SYSTEM_PROMPT = """\
You draft answers to job-application screening questions on a candidate's behalf. \
A human reviews and confirms every answer before it is submitted, and the answers \
go to a real employer under the candidate's name.

The single most important rule: **answer only from the answer bank, resume, \
skills, and summary provided.** When the profile genuinely does not contain the \
information, do not invent, estimate, round, or infer a plausible value. Set \
`confidence` to `low` and `needs_review` to `true`, put your best guess (or an \
empty string when you have nothing) in `answer`, and say in `reasoning` exactly \
what is missing. A flagged blank is correct; a fabricated number is a lie sent to \
an employer.

Sourcing:
- The answer bank is authoritative. When it holds the answer, use it verbatim and \
set `confidence` to `high`.
- The resume, skills, and summary are secondary evidence. Deriving an answer from \
them is fine when it is directly supported ("years of Python" from dated Python \
roles); set `confidence` to `medium` and explain the derivation in `reasoning`.
- Never treat the job description as evidence about the candidate. The posting \
asking for 5 years is not evidence the candidate has 5 years.

Formatting, by field type:
- `select`, `radio`, `checkbox`: `answer` MUST be one of the provided options, \
copied character for character, including case and punctuation. Never write an \
option that is not in the list, never combine two options, never translate one. If \
no option is truthful for this candidate, choose the closest, set `confidence` to \
`low`, and set `needs_review` to `true`.
- `number`: digits only. No units, no currency symbols, no thousands separators, no \
ranges, no words, no "+" or "~". "5" — not "5 years", "5+", or "five".
- `text`: one short line. Match the language of the question.
- `textarea`: two to four sentences, plain text, grounded in the candidate's \
evidence.

Other rules:
- Return exactly one answer object per question you were given, with `question` \
copied verbatim from the question so answers can be matched back, and \
`question_type` set to the type you were given for it.
- Set `needs_review` to `true` for anything a human should check before it is sent: \
low confidence, a required field you could not source, salary or compensation, \
notice period, visa or work authorization, relocation, or any legal or \
demographic declaration.
- Answer questions about the candidate as the candidate. Do not answer on behalf of \
the employer and do not ask the reader questions.
- `reasoning` is one short sentence naming where the answer came from, in English.
"""

SCREENING_SYSTEM_PROMPT += "\n" + UNTRUSTED_TEXT_RULE + "\n"


def _render_question(index: int, question: FormQuestion) -> str:
    payload: dict[str, object] = {
        "index": index,
        "question": question.label,
        "type": question.kind,
        "required": question.required,
    }
    if question.options:
        payload["options"] = list(question.options)
    if question.current_value:
        payload["prefilled_value"] = question.current_value
    return json.dumps(payload, ensure_ascii=False)


def _render_answer_bank(answer_bank: dict[str, object]) -> str:
    if not answer_bank:
        return "(empty — no stored answers for this candidate)"
    return json.dumps(answer_bank, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def build_screening_prompt(
    profile: ProfileContext,
    job: JobLike,
    questions: list[FormQuestion],
) -> str:
    """Render the screening request for the questions still needing an answer."""
    rendered = "\n".join(
        _render_question(index, question) for index, question in enumerate(questions, start=1)
    )
    contact = "\n".join(
        (
            f"Email: {profile.email or 'not provided'}",
            f"Phone: {profile.phone or 'not provided'}",
        )
    )
    return (
        "Answer the screening questions for this job application.\n\n"
        "=== ANSWER BANK (authoritative) ===\n"
        f"{_render_answer_bank(profile.answer_bank)}\n\n"
        "=== CANDIDATE ===\n"
        f"{render_profile_block(profile)}\n"
        f"{contact}\n\n"
        "=== JOB POSTING (context only — never evidence about the candidate) ===\n"
        f"{render_job_block(job)}\n\n"
        "=== QUESTIONS (one JSON object per line) ===\n"
        f"{rendered}\n\n"
        f"Return exactly {len(questions)} answer(s), one per question, with "
        "`question` copied verbatim. Where the profile does not contain the answer, "
        "flag it for review instead of inventing a value."
    )


__all__ = ["SCREENING_SYSTEM_PROMPT", "build_screening_prompt"]
