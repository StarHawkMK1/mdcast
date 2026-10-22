from __future__ import annotations

import panflute as pf
from pdf_builder import typst_pdf

from mdcast.pipeline import convert
from mdcast.readers.pdf import read_pdf
from mdcast.readers.pdf.model import Box
from mdcast.readers.pdf.repeats import band_key, repeated
from mdcast.report import Codes, Level, Report
from mdcast.types import Format, Source

_PAGE_NUMBER = r'footer: align(center)[\- #context counter(page).display() -]'


def pdf_source(data: bytes) -> Source:
    return Source(data, "a.pdf", Format.PDF)


def pages(*bodies: str) -> str:
    return "\n#pagebreak()\n".join(bodies)


def text(data: bytes) -> str:
    """The imported body's text, a paragraph a line (paragraphs may run on from page to page)."""
    doc = read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").doc
    return "\n".join(pf.stringify(b).strip() for b in doc.content)


def skipped(result) -> list:
    return [e for e in result.report.events if e.code == Codes.IMPORT_HEADER_SKIPPED]


def test_page_numbers_removed():
    data = typst_pdf(pages("본문 하나", "본문 둘", "본문 셋", "본문 넷"), page=f'paper: "a4", {_PAGE_NUMBER}')
    body = text(data)
    assert "본문 하나" in body and "본문 넷" in body and "-" not in body
    result = convert(pdf_source(data), [Format.MD])
    assert "- 1 -" not in result.outputs[0].data.decode("utf-8")
    [event] = skipped(result)
    assert event.level is Level.INFO
    assert "4줄" in event.message and "'- 1 -'" in event.message
    assert result.report.coverage == 1.0


def test_running_header_removed():
    data = typst_pdf(pages("첫 쪽", "둘째 쪽", "셋째 쪽", "넷째 쪽"), page='paper: "a4", header: [보고서 머리말]')
    result = convert(pdf_source(data), [Format.MD])
    md = result.outputs[0].data.decode("utf-8")
    assert "보고서 머리말" not in md and "넷째 쪽" in md
    source = read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").source_text
    assert not [t for t in source if "보고서 머리말" in t]
    [event] = skipped(result)
    assert "4줄" in event.message and "'보고서 머리말'" in event.message
    assert result.report.coverage == 1.0


def test_two_page_doc_keeps_lines():
    data = typst_pdf(pages("첫 쪽", "둘째 쪽"), page=f'paper: "a4", {_PAGE_NUMBER}')
    result = convert(pdf_source(data), [Format.MD])
    body = text(data)
    assert "- 1 -" in body and "- 2 -" in body
    assert not skipped(result)


def test_body_line_in_middle_kept():
    data = typst_pdf(pages(*["#v(10cm)\n가운데 같은 글"] * 4))
    result = convert(pdf_source(data), [Format.MD])
    assert text(data).count("가운데 같은 글") == 4
    assert not skipped(result)


def test_mixed_page_sizes():
    """Review Focus 2: each page's band is measured with that page's own height."""
    portrait = pages("세로 하나", "세로 둘", "세로 셋")
    landscape = "#page(flipped: true)[가로 하나]\n#page(flipped: true)[가로 둘]"
    footer = "footer: [꼬리말 글 #context counter(page).display()]"  # at the left margin, as wide either way
    data = typst_pdf(f"{portrait}\n{landscape}", page=f'paper: "a4", {footer}')
    body = text(data)
    assert "꼬리말" not in body and "가로 둘" in body
    result = convert(pdf_source(data), [Format.MD])
    [event] = skipped(result)
    assert "5줄" in event.message
    assert result.report.coverage == 1.0


def test_band_key_needs_the_whole_box_in_a_band():
    assert band_key(Box(100, 10, 200, 20), 800, "머리말 3쪽") == ("top", "머리말 쪽", 20)
    assert band_key(Box(100, 760, 200, 790), 800, "12") == ("bottom", "", 20)
    assert band_key(Box(100, 400, 200, 410), 800, "본문") is None
    assert band_key(Box(0, 0, 600, 800), 800) is None  # a whole-page picture is in no band
    assert band_key(Box(0, 10, 600, 100), 800) is None  # reaches out of the top band


def test_repeated_needs_min_pages_and_half_the_pages():
    assert repeated([{"a"}, {"a"}, {"a", "b"}, {"b"}]) == {"a"}
    assert repeated([{"a"}, {"a"}]) == set()
    assert repeated([{"a"}] * 3 + [set()] * 4) == set()  # 3 of 7 pages is under half
    assert repeated([{"a"}] * 4 + [set()] * 4) == {"a"}
