"""Prompt for the reviewer pass over a drafted application.

A second, fresh-context set of eyes: the reviewer never sees the drafter's
reasoning, only the finished materials and the posting — the same position a
hiring manager reads from.
"""

from __future__ import annotations

from typing import Any

from app.ai.prompts import (
    UNTRUSTED_TEXT_RULE,
    JobLike,
    render_job_block,
    render_profile_block,
)
from app.automation.contracts import ProfileContext

REVIEW_SYSTEM_PROMPT = f"""\
You are a skeptical hiring-manager proxy reviewing a drafted job application \
(cover letter and screening answers) against the posting and the candidate's \
real profile. Your critique feeds a review screen where the candidate decides \
what to change; nothing you output is applied automatically.

{UNTRUSTED_TEXT_RULE}

Grounding rule, above everything: never suggest an edit that adds a skill, \
employer, metric, or achievement the candidate's profile does not support. An \
edit that would strengthen the letter by inventing is worse than no edit.

Output:
- `edits`: mechanical, verbatim-applicable improvements to the cover letter \
only. Each `old_string` must be copied EXACTLY from the letter (the applier \
does a literal string replacement and skips anything that does not match). \
Suggest an edit only when the improvement is concrete: a stated requirement \
the letter should name, the posting's literal terminology where the letter \
uses a synonym for the same real experience, passive phrasing turned active. \
Few good edits beat many cosmetic ones.
- `critique`: exactly four notes, one per category, in this order — \
`missed_keywords` (requirements or terms from the posting the materials never \
address), `company_angle` (whether the letter says anything specific to this \
company or could be sent anywhere), `reframing` (passive or vague phrasing \
that undersells real experience), `tone` (register and voice against a \
professional application). When a category has no problem, say so explicitly \
in its note — an empty critique list is never valid.
- `coverage`: one entry per requirement the posting states. `status` is \
`covered` (the letter or answers address it in the posting's own terms), \
`synonym_only` (addressed, but not in the posting's literal wording — ATS \
matching is literal), `missing_have_it` (the profile supports it but the \
materials never say it — the actionable case), or `missing_gap` (the profile \
does not support it; it must stay visible, never papered over).
- `summary`: one honest sentence — would this draft earn an interview?

Write every field in English.
"""


def _render_answers(answers: list[dict[str, Any]]) -> str:
    if not answers:
        return "(no screening answers were drafted)"
    lines = []
    for answer in answers:
        lines.append(f"Q: {answer.get('question', '')}")
        lines.append(f"A: {answer.get('answer', '')}")
    return "\n".join(lines)


def build_review_prompt(
    profile: ProfileContext,
    job: JobLike,
    *,
    cover_letter: str | None,
    answers: list[dict[str, Any]],
) -> str:
    """Render the review request over the drafted materials."""
    return (
        "Review this drafted application against the posting and the candidate's "
        "profile.\n\n"
        "=== CANDIDATE (the only source of truth about them) ===\n"
        f"{render_profile_block(profile)}\n\n"
        "=== JOB POSTING ===\n"
        f"{render_job_block(job)}\n\n"
        "=== DRAFT COVER LETTER (the target of `edits`) ===\n"
        f"{(cover_letter or '').strip() or '(no cover letter was drafted)'}\n\n"
        "=== DRAFT SCREENING ANSWERS ===\n"
        f"{_render_answers(answers)}\n\n"
        "Return the edits, the four critique notes, the requirement coverage "
        "table, and the one-sentence verdict."
    )


__all__ = ["REVIEW_SYSTEM_PROMPT", "build_review_prompt"]
