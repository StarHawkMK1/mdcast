from __future__ import annotations

import io

import panflute as pf
import pdfplumber
import pytest
from pdf_builder import typst_pdf
from PIL import Image

from mdcast.pipeline import convert
from mdcast.readers.md import read_md
from mdcast.readers.pdf.lines import page_lines
from mdcast.readers.pdf.model import Box, Line, Run
from mdcast.readers.pdf.paragraphs import group_paragraphs, join_text, measure_layout, to_inlines
from mdcast.report import Level, Report
from mdcast.types import Format, Source

RIGHT = 500.0


def line(page: int, top: float, x0: float, x1: float, text: str, size: float = 11, bold: bool = False) -> Line:
    return Line(page, Box(x0, top, x1, top + size), size, [Run(text, bold)])


def texts(lines: list[Line]) -> list[list[str]]:
    return [[ln.text for ln in p] for p in group_paragraphs(lines, measure_layout(lines))]


def body(*tops: float, page: int = 0) -> list[Line]:
    """Lines of ordinary text running to the right edge, at ``tops``."""
    return [line(page, top, 70, RIGHT, f"줄{i}") for i, top in enumerate(tops)]


def test_close_lines_join_into_one_paragraph():
    assert texts(body(100, 114, 128)) == [["줄0", "줄1", "줄2"]]


def test_wide_gap_starts_paragraph():
    assert texts(body(100, 114, 128, 158)) == [["줄0", "줄1", "줄2"], ["줄3"]]


def test_marker_line_starts_paragraph():
    lines = [line(0, 100, 70, RIGHT, "□ 첫 항목"), line(0, 114, 70, RIGHT, "이어지는 줄"),
             line(0, 128, 70, RIGHT, "○ 둘째")]
    assert texts(lines) == [["□ 첫 항목", "이어지는 줄"], ["○ 둘째"]]


def test_note_mark_starts_paragraph():
    lines = [*body(100, 114), line(0, 128, 70, RIGHT, "※ 참고 글")]
    assert texts(lines) == [["줄0", "줄1"], ["※ 참고 글"]]


def test_short_last_line_ends_paragraph():
    lines = [line(0, 100, 70, RIGHT - 40, "끝줄"), *body(114, 128)]
    assert texts(lines) == [["끝줄"], ["줄0", "줄1"]]
    # a line a little short of the edge (ragged right) still continues
    lines = [line(0, 100, 70, RIGHT - 15, "끝줄"), *body(114, 128)]
    assert texts(lines) == [["끝줄", "줄0", "줄1"]]


def test_size_change_starts_paragraph():
    lines = [line(0, 80, 70, RIGHT, "큰 글", size=16), *body(100, 114)]
    assert texts(lines) == [["큰 글"], ["줄0", "줄1"]]


def test_bold_change_starts_paragraph():
    lines = [line(0, 100, 70, RIGHT, "Bold", bold=True), *body(114, 128)]
    assert texts(lines) == [["Bold"], ["줄0", "줄1"]]


def test_paragraph_continues_across_pages():
    # page 1 starts high up: the gap from page 0's last line does not count
    lines = [*body(700, 714, 728), *body(50, page=1)]
    assert texts(lines) == [["줄0", "줄1", "줄2", "줄0"]]
    # the other rules still hold across the page boundary
    lines = [*body(700, 714, 728), line(1, 50, 70, RIGHT, "□ 항목")]
    assert texts(lines) == [["줄0", "줄1", "줄2"], ["□ 항목"]]


def test_join_text_spacing():
    assert join_text("가나", "다라") == "가나 다라"
    assert join_text("well-", "known") == "well-known"
    assert join_text("A -", "B") == "A - B"
    assert join_text("가-", "나") == "가- 나"
    assert join_text("opine\u00ad", "mur") == "opine\u00admur"  # hyphenated at the line end: soft hyphen kept


def test_bold_runs_become_strong():
    only = Line(0, Box(0, 0, 100, 11), 11, [Run("Bold", True), Run(" plain", False)])
    assert to_inlines([only]) == [pf.Strong(pf.Str("Bold")), pf.Space(), pf.Str("plain")]


def test_inlines_join_lines_and_keep_spaces_outside_strong():
    first = Line(0, Box(0, 0, 100, 11), 11, [Run("a well-", False)])
    second = Line(0, Box(0, 14, 100, 25), 11, [Run("known", False), Run(" b c", True)])
    third = Line(0, Box(0, 28, 100, 39), 11, [Run("d", True), Run(" e", False)])
    assert to_inlines([first, second, third]) == [
        pf.Str("a"), pf.Space(), pf.Str("well-known"), pf.Space(),
        pf.Strong(pf.Str("b"), pf.Space(), pf.Str("c"), pf.Space(), pf.Str("d")),
        pf.Space(), pf.Str("e"),
    ]


def test_no_lines_layout_defaults():
    layout = measure_layout([])
    assert layout.body_size == 11.0
    assert layout.line_gap == pytest.approx(13.2)
    assert layout.right == 0
    assert group_paragraphs([], layout) == []
    assert to_inlines([]) == []


def test_layout_measures_body_lines():
    lines = [line(0, 80, 70, 300, "큰 제목 글줄", size=16), *body(100, 114, 128), line(0, 142, 70, 400, "끝")]
    layout = measure_layout(lines)
    assert layout.body_size == 11
    assert layout.line_gap == pytest.approx(14)
    assert layout.right == pytest.approx(RIGHT)


LONG = (
    "The quick brown fox jumps over the lazy dog while the patient reader keeps going, "
    "line after line, until the paragraph has wrapped well past three lines of ordinary text "
    "set in the default serif face and size of this small test document. Every sentence adds "
    "a little more width, so the lines keep breaking at the right margin of the page, and the "
    "reader should see one paragraph rather than a stack of separate lines. "
)


def test_typst_paragraphs_and_bold():
    data = typst_pdf(LONG + "*Bold* rest of it.\n\nSecond paragraph here.")
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        assert len(page_lines(0, pdf.pages[0].chars)) > 4  # the first paragraph does wrap past three lines
    result = convert(Source(data, "a.pdf", Format.PDF), [Format.MD])
    assert not [e for e in result.report.events if e.level is Level.ERROR]
    assert result.report.coverage == 1.0
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc
    assert [type(b).__name__ for b in back.content] == ["Para", "Para"]
    first = back.content[0]
    assert pf.stringify(first).strip() == LONG + "Bold rest of it."  # one space at each line join
    assert not any(isinstance(e, (pf.SoftBreak, pf.LineBreak)) for e in first.content)
    strong = [e for e in first.content if isinstance(e, pf.Strong)]
    assert [pf.stringify(e) for e in strong] == ["Bold"]
    assert pf.stringify(back.content[1]).strip() == "Second paragraph here."


HYPHENATED = (
    "Extraordinarily comprehensive internationalization considerations notwithstanding, "
    "implementations characteristically demonstrate unquestionable interoperability. "
) * 6


def test_typst_hyphenated_words_join_up():
    """typst hyphenates justified text with a soft hyphen in the text layer: the word joins up, no space."""
    data = typst_pdf(
        '#set par(justify: true)\n#set text(lang: "en", hyphenate: true)\n' + HYPHENATED,
        page="width: 8cm, height: auto, margin: 1cm",
    )
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        assert "\u00ad" in "".join(c["text"] for c in pdf.pages[0].chars)  # typst did hyphenate
    result = convert(Source(data, "a.pdf", Format.PDF), [Format.MD])
    assert result.report.coverage == 1.0
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc
    assert pf.stringify(back).strip().replace("\u00ad", "") == HYPHENATED.strip()


def test_image_only_pdf_does_not_fail():
    png = io.BytesIO()
    Image.new("RGB", (40, 30), (30, 120, 200)).save(png, format="PNG")
    data = typst_pdf('#image("a.png", width: 4cm)', files={"a.png": png.getvalue()})
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        assert pdf.pages[0].chars == [] and len(pdf.pages[0].images) == 1
    result = convert(Source(data, "a.pdf", Format.PDF), [Format.MD])
    assert not [e for e in result.report.events if e.level is Level.ERROR]
    assert result.outputs[0].data is not None
