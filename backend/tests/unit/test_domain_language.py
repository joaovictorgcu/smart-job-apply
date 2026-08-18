"""The posting-language heuristic.

Pure tests over `app.domain.language`. The stakes are modest but concrete: the
detected language picks the language a cover letter is written in, so a posting
in Portuguese answered in English is a wasted application.
"""

from __future__ import annotations

from app.domain.language import detect_language, fold, squash

PORTUGUESE = (
    "Estamos com uma vaga para pessoa desenvolvedora backend. "
    "Requisitos: conhecimento em Python e experiencia com APIs REST. "
    "Sobre a empresa: nossa equipe trabalha de forma remota."
)

ENGLISH = (
    "We are looking for a backend engineer to join our team. "
    "Requirements: strong experience with Python and REST APIs. "
    "About the role: you will work with a distributed team."
)


class TestDetectLanguage:
    def test_no_text_defaults_to_english(self) -> None:
        assert detect_language(None) == "en"
        assert detect_language("") == "en"
        assert detect_language("   \n\t ") == "en"

    def test_text_without_words_defaults_to_english(self) -> None:
        assert detect_language("--- 2024 // 100% ---") == "en"

    def test_a_portuguese_posting_is_detected(self) -> None:
        assert detect_language(PORTUGUESE) == "pt-BR"

    def test_an_english_posting_is_detected(self) -> None:
        assert detect_language(ENGLISH) == "en"

    def test_accents_are_folded_before_the_markers_are_counted(self) -> None:
        # Written the way a real posting is: without folding, `experiência`
        # tokenizes into fragments and the posting reads as English.
        assert detect_language("Experiência, colaboração e inglês.") == "pt-BR"

    def test_a_tie_defaults_to_english(self) -> None:
        # Portuguese has to win outright; mixed postings are common and English
        # is the safer default for a cover letter.
        assert detect_language("de the") == "en"


class TestFolding:
    def test_fold_lowercases_and_strips_accents(self) -> None:
        assert fold("Experiência PÓS-graduação") == "experiencia pos-graduacao"

    def test_squash_also_collapses_punctuation_and_whitespace(self) -> None:
        assert squash("  Anos de experiência?  (Sênior)  ") == "anos de experiencia senior"
