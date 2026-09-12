"""Drawing the adapted resume, and nothing else.

The only module in the app that knows what a point size is. `app.domain.
resume_render` decides what the page says; this decides how it looks, so
swapping the renderer — or the library — never touches a product rule.

ReportLab rather than a browser engine: it is pure Python with no system
libraries behind it, which matters for a container that already carries a
Chromium. Portuguese fits inside WinAnsiEncoding, so the built-in Helvetica
draws every accent without an embedded font.

Failure is never fatal here. A resume that cannot be drawn falls back to the
PDF the user uploaded — the behaviour before this existed — because a
submission must not be blocked by a layout engine.
"""

from __future__ import annotations

import io
from collections.abc import Sequence

from app.domain.resume_render import Block
from app.observability import get_logger

logger = get_logger(__name__)

# A4 in points, and margins wide enough that a recruiter's printer does not
# clip the last column of a technologies line.
PAGE_WIDTH = 595.27
PAGE_HEIGHT = 841.89
MARGIN = 48.0

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"


class ResumeRenderError(RuntimeError):
    """The document could not be drawn. Callers fall back; they do not fail."""


def _styles() -> dict[str, object]:
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle

    base = ParagraphStyle(
        "body",
        fontName=FONT,
        fontSize=9.5,
        leading=13,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    return {
        "name": ParagraphStyle(
            "name", parent=base, fontName=FONT_BOLD, fontSize=18, leading=22, spaceAfter=2
        ),
        "headline": ParagraphStyle(
            "headline", parent=base, fontSize=11, leading=14, spaceAfter=2, textColor="#333333"
        ),
        "contact": ParagraphStyle(
            "contact", parent=base, fontSize=8.5, leading=11, spaceAfter=10, textColor="#555555"
        ),
        "heading": ParagraphStyle(
            "heading",
            parent=base,
            fontName=FONT_BOLD,
            fontSize=10.5,
            leading=13,
            spaceBefore=12,
            spaceAfter=4,
        ),
        "entry": ParagraphStyle(
            "entry", parent=base, fontName=FONT_BOLD, fontSize=10, leading=13, spaceBefore=6
        ),
        "meta": ParagraphStyle(
            "meta", parent=base, fontName=FONT_ITALIC, fontSize=8.5, leading=11, textColor="#555555"
        ),
        "body": base,
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=12, bulletIndent=2),
        "terms": ParagraphStyle(
            "terms", parent=base, fontSize=8.5, leading=11, textColor="#444444", spaceAfter=2
        ),
    }


def _escape(text: str) -> str:
    """ReportLab's paragraphs are mini-markup, so the candidate's own `&` is not a tag."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_pdf(blocks: Sequence[Block]) -> bytes:
    """Draw the document. Raises `ResumeRenderError` if it cannot be drawn."""
    if not blocks:
        raise ResumeRenderError("There is nothing to draw.")

    try:
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:  # pragma: no cover - the dependency is declared
        raise ResumeRenderError("ReportLab is not installed.") from exc

    styles = _styles()
    story: list[object] = []
    for block in blocks:
        if block.kind == "name":
            story.append(Paragraph(_escape(block.text), styles["name"]))
        elif block.kind == "headline":
            story.append(Paragraph(_escape(block.text), styles["headline"]))
        elif block.kind == "contact":
            story.append(Paragraph(_escape(" · ".join(block.items)), styles["contact"]))
        elif block.kind == "heading":
            story.append(Paragraph(_escape(block.text.upper()), styles["heading"]))
        elif block.kind == "entry":
            story.append(Paragraph(_escape(block.text), styles["entry"]))
            meta = " · ".join(item for item in block.items if item)
            if meta:
                story.append(Paragraph(_escape(meta), styles["meta"]))
        elif block.kind == "bullet":
            story.append(Paragraph(_escape(block.text), styles["bullet"], bulletText="•"))
        elif block.kind == "terms":
            if block.items:
                story.append(Paragraph(_escape(", ".join(block.items)), styles["terms"]))
        else:
            story.append(Paragraph(_escape(block.text), styles["body"]))

    if not story:
        raise ResumeRenderError("Every block was empty.")
    story.append(Spacer(1, 1))

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="Currículo",
        # No author metadata: the file goes to an employer, and the candidate's
        # name is already on the page where they chose to put it.
        author="",
    )
    try:
        document.build(story)
    except Exception as exc:
        logger.warning(
            "The adapted resume could not be drawn.",
            extra={"action": "resume.pdf", "status": "failed", "error_type": type(exc).__name__},
        )
        raise ResumeRenderError(str(exc)) from exc

    return buffer.getvalue()


__all__ = ["MARGIN", "PAGE_HEIGHT", "PAGE_WIDTH", "ResumeRenderError", "to_pdf"]
