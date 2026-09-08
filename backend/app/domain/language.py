"""Which language a job posting is written in, and the text folding it needs.

A deliberately small heuristic with no model call behind it: several layers ask
this question (the scoring pipeline, the "mirror the posting" cover-letter mode)
and they must all get the same answer, so the rule lives here rather than in any
one caller.
"""

from __future__ import annotations

import re
import unicodedata

_PORTUGUESE_MARKERS = frozenset(
    {
        "de", "da", "do", "das", "dos", "para", "com", "que", "nao", "voce", "como",
        "uma", "um", "os", "as", "em", "por", "mais", "sua", "seu", "sera", "ser",
        "tambem", "experiencia", "conhecimento", "desejavel", "requisitos",
        "atividades", "empresa", "vaga", "area", "nossa", "nosso", "sobre",
        "trabalho", "equipe", "anos", "salario", "beneficios", "ingles",
    }
)

_ENGLISH_MARKERS = frozenset(
    {
        "the", "and", "of", "to", "in", "for", "with", "you", "your", "a", "an",
        "are", "is", "will", "be", "or", "as", "on", "we", "our", "this", "that",
        "have", "has", "experience", "requirements", "skills", "team", "work",
        "role", "about", "strong", "ability", "years", "benefits", "salary",
    }
)

_WORD = re.compile(r"[a-z]+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def fold(text: str) -> str:
    """Lowercase and strip accents, so `experiência` matches `experiencia`."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def squash(text: str) -> str:
    """Fold, then reduce punctuation and runs of whitespace to single spaces."""
    return _NON_ALNUM.sub(" ", fold(text)).strip()


def detect_language(text: str | None) -> str:
    """Guess the language of a job description.

    A deliberately small heuristic — stopword frequency, Portuguese versus
    English — because the only consumers are `Job.detected_language` and the
    "mirror the posting" cover-letter mode. Defaults to `"en"` with no signal.
    """
    if not text or not text.strip():
        return "en"
    words = _WORD.findall(fold(text))
    if not words:
        return "en"
    portuguese = sum(1 for word in words if word in _PORTUGUESE_MARKERS)
    english = sum(1 for word in words if word in _ENGLISH_MARKERS)
    return "pt-BR" if portuguese > english else "en"


__all__ = ["detect_language", "fold", "squash"]
