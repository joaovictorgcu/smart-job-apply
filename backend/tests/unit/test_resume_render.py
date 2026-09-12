"""The adapted resume as a page, and as bytes.

Two layers, tested separately on purpose. What the document *says* — which
sections, in which order — is a product decision and is asserted against a
tuple of blocks. How it *looks* is one adapter, and all that is asserted there
is that it produces a PDF and never takes a submission down with it.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.resume_diff import Snapshot, SnapshotExperience
from app.domain.resume_render import (
    MAX_BULLETS_PER_ENTRY,
    Block,
    period_text,
    plain_text,
    render_blocks,
)
from app.services.resume_pdf import ResumeRenderError, to_pdf


def experience(**overrides: object) -> SnapshotExperience:
    payload: dict[str, object] = {
        "experience_id": 1,
        "company": "Acme",
        "role": "Desenvolvedor Full Stack",
        "summary": "APIs e painéis.",
        "responsibilities": ("Construí APIs em .NET 8.",),
        "results": ("p95 de 420 ms para 120 ms",),
        "technologies": (".NET", "React"),
        "period": "jan 2023 — atual",
        "location": "Recife, PE",
    }
    payload.update(overrides)
    return SnapshotExperience(**payload)  # type: ignore[arg-type]


def snapshot(**overrides: object) -> Snapshot:
    payload: dict[str, object] = {
        "summary": "Full stack com foco em .NET.",
        "skills": ("C#", ".NET", "React"),
        "experiences": (experience(),),
    }
    payload.update(overrides)
    return Snapshot(**payload)  # type: ignore[arg-type]


def kinds(blocks: tuple[Block, ...]) -> list[str]:
    return [block.kind for block in blocks]


class TestThePeriod:
    def test_a_current_position_says_atual_rather_than_trailing_off(self) -> None:
        assert period_text(date(2023, 1, 1), None, True) == "jan 2023 — atual"

    def test_a_finished_one_prints_both_ends(self) -> None:
        assert period_text(date(2021, 2, 1), date(2022, 12, 31), False) == "fev 2021 — dez 2022"

    def test_a_half_known_period_prints_the_half_it_knows(self) -> None:
        assert period_text(date(2021, 2, 1), None, False) == "fev 2021"
        assert period_text(None, None, False) == ""


class TestWhatThePageSays:
    def test_the_header_leads_and_the_sections_follow_in_order(self) -> None:
        blocks = render_blocks(
            snapshot(),
            full_name="João Victor Uchôa",
            headline="Desenvolvedor Full Stack",
            contact=("Recife, PE", "+55 81 99999-1234"),
        )

        assert kinds(blocks)[:3] == ["name", "headline", "contact"]
        headings = [block.text for block in blocks if block.kind == "heading"]
        assert headings == ["Resumo", "Tecnologias", "Experiência"]

    def test_a_section_with_no_content_gets_no_heading(self) -> None:
        blocks = render_blocks(snapshot(summary="", skills=(), experiences=()))

        assert [block for block in blocks if block.kind == "heading"] == []

    def test_a_measured_result_is_printed_before_a_responsibility(self) -> None:
        blocks = render_blocks(snapshot())

        bullets = [block.text for block in blocks if block.kind == "bullet"]
        assert bullets[0].startswith("p95")

    def test_a_long_position_is_capped_rather_than_running_off_the_page(self) -> None:
        many = tuple(f"Item {index}" for index in range(20))
        blocks = render_blocks(snapshot(experiences=(experience(responsibilities=many),)))

        assert len([block for block in blocks if block.kind == "bullet"]) == MAX_BULLETS_PER_ENTRY

    def test_a_position_with_no_role_and_no_company_is_left_out(self) -> None:
        # It cannot be drawn honestly, and a blank entry on a resume is worse
        # than a missing one.
        blocks = render_blocks(snapshot(experiences=(experience(role="", company=""),)))

        assert [block for block in blocks if block.kind == "entry"] == []

    def test_every_word_on_the_page_came_from_the_snapshot(self) -> None:
        source = snapshot()
        text = plain_text(render_blocks(source, full_name="João Victor Uchôa"))

        for line in (*source.skills, *source.experiences[0].responsibilities):
            assert line in text
        # The renderer joins and orders. It does not write new facts.
        assert "Kubernetes" not in text


class TestWhatItLooksLike:
    def test_it_produces_a_pdf(self) -> None:
        content = to_pdf(render_blocks(snapshot(), full_name="João Victor Uchôa"))

        assert content.startswith(b"%PDF")
        assert len(content) > 500

    def test_portuguese_accents_need_no_embedded_font(self) -> None:
        blocks = render_blocks(
            snapshot(summary="Experiência em manutenção, integração e migração."),
            full_name="João Victor Uchôa",
        )

        assert to_pdf(blocks).startswith(b"%PDF")

    def test_markup_in_the_candidate_s_own_words_is_escaped_not_parsed(self) -> None:
        # ReportLab paragraphs are mini-markup. A resume saying "C++ & <T>" must
        # render, not raise.
        blocks = render_blocks(snapshot(summary="Trabalhei com C++ & genéricos <T>."))

        assert to_pdf(blocks).startswith(b"%PDF")

    def test_an_empty_document_is_refused_rather_than_drawn_blank(self) -> None:
        with pytest.raises(ResumeRenderError):
            to_pdf(())
