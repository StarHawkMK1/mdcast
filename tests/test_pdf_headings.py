from __future__ import annotations

import panflute as pf
from pdf_builder import typst_pdf

from mdcast.pipeline import convert
from mdcast.readers.md import read_md
from mdcast.readers.pdf import read_pdf
from mdcast.readers.pdf.headings import heading_level, heading_sizes
from mdcast.readers.pdf.model import Box, Line, Run
from mdcast.report import Level, Report
from mdcast.types import Format, Source

BODY = 11.0


def para(size: float, *texts: str, top: float = 100, page: int = 0) -> list[Line]:
    """A paragraph of one line per text, all at ``size``."""
    return [Line(page, Box(70, top + i * size * 1.2, 300, top + i * size * 1.2 + size), size, [Run(t, False)])
            for i, t in enumerate(texts)]


def test_sizes_rank_into_levels():
    paragraphs = [para(20, "제목"), para(BODY, "본문"), para(16, "장"), para(14, "절"), para(16, "다른 장")]
    assert heading_sizes(paragraphs, BODY) == {20: 1, 16: 2, 14: 3}
    assert [heading_level(p, heading_sizes(paragraphs, BODY), BODY) for p in paragraphs] == [1, None, 2, 3, 2]


def test_close_sizes_share_level():
    paragraphs = [para(20, "제목"), para(16.0, "장"), para(16.3, "다른 장"), para(14, "절")]
    sizes = heading_sizes(paragraphs, BODY)
    assert sizes == {20: 1, 16.3: 2, 16.0: 2, 14: 3}


def test_first_page_title_stays_level_one():
    # a divider on page 2 set larger than the page-1 title is level 1 beside it, not above it
    paragraphs = [
        para(BODY, "표지 앞 본문", page=0),  # no candidate on page 0: page 1 holds the title
        para(18, "문서 제목", page=1), para(BODY, "본문", page=1), para(14, "1장", page=1),
        para(24, "제2부", page=2), para(17.7, "부제", page=2), para(16, "2장", page=2), para(12.8, "절", page=2),
    ]
    sizes = heading_sizes(paragraphs, BODY)
    assert sizes == {24: 1, 18: 1, 17.7: 1, 16: 2, 14: 3, 12.8: 4}


def test_levels_stop_at_six():
    paragraphs = [para(size, f"{size}pt") for size in (30, 28, 26, 24, 22, 20, 18, 16)]
    assert heading_sizes(paragraphs, BODY) == {30: 1, 28: 2, 26: 3, 24: 4, 22: 5, 20: 6, 18: 6, 16: 6}


def test_long_or_sentence_not_heading():
    three = para(20, "첫 줄", "둘째 줄", "셋째 줄")
    sentence = para(20, "크게 쓴 글이 문장으로", "끝.")
    sizes = heading_sizes([three, sentence], BODY)
    assert sizes == {}
    # sizes are keyed by size alone: a long paragraph at a heading's size is still not a heading
    heading = para(20, "제목")
    sizes = heading_sizes([heading, three, sentence], BODY)
    assert sizes == {20: 1}
    assert heading_level(heading, sizes, BODY) == 1
    assert heading_level(three, sizes, BODY) is None
    assert heading_level(sentence, sizes, BODY) is None


def test_slightly_larger_not_heading():
    # 12pt over an 11pt body (1.09×) with no number in front: too close to tell from body text
    paragraph = para(12, "소제목")
    sizes = heading_sizes([paragraph], BODY)
    assert sizes == {}
    assert heading_level(paragraph, sizes, BODY) is None


def test_numbered_slightly_larger_is_heading():
    # a heading number or a □ in front lets a size just above the body be a heading (D14)
    numbered = [para(12, "가. 소제목"), para(12, "1. 개요"), para(12, "Ⅱ. 추진 방향"), para(12, "□ 목 적")]
    paragraphs = [para(20, "제목"), *numbered, para(12, "소제목")]
    sizes = heading_sizes(paragraphs, BODY)
    assert sizes == {20: 1, 12: 2}
    assert [heading_level(p, sizes, BODY) for p in paragraphs] == [1, 2, 2, 2, 2, None]


def test_numbered_at_body_size_or_long_not_heading():
    near_body = para(11.4, "1. 개요")  # within 0.5pt of the body: the body size
    long = para(12, "1. " + "가" * 60)
    sentence = para(12, "1. 개요를 적습니다.")
    bullet = para(12, "○ 세부 항목")  # only □·■ open a heading
    sizes = heading_sizes([near_body, long, sentence, bullet], BODY)
    assert sizes == {}


BODY_TEXT = "본문 글은 여러 낱말로 이어집니다. 줄이 조금 길어 집니다. 계속해서 이어지는 본문 글입니다."


def read_back(data: bytes) -> pf.Doc:
    result = convert(Source(data, "a.pdf", Format.PDF), [Format.MD])
    assert not [e for e in result.report.events if e.level is Level.ERROR]
    assert result.report.coverage == 1.0
    return read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc


def test_typst_headings_end_to_end():
    # the second title is bold Latin: left a bold Para, the document-title rule (M3a D6-1) would lift it
    for title, markup in (("문서 제목", "문서 제목"), ("Report Title", "*Report Title*")):
        data = typst_pdf(
            f"#text(size: 20pt)[{markup}]\n\n"
            "#text(size: 16pt)[1장]\n\n"
            f"{BODY_TEXT}\n\n"
            "#text(size: 14pt)[1.1 절]\n\n"
            f"{BODY_TEXT}\n"
        )
        back = read_back(data)
        headers = [b for b in back.content if isinstance(b, pf.Header)]
        assert [(h.level, pf.stringify(h)) for h in headers] == [(1, title), (2, "1장"), (3, "1.1 절")]
        assert [type(b).__name__ for b in back.content] == ["Header", "Header", "Para", "Header", "Para"]
        assert pf.stringify(back.content[2]).strip() == BODY_TEXT
        assert not any(isinstance(e, pf.Strong) for e in headers[0].content)


def test_bold_banner_does_not_push_the_title_down():
    # a short bold line above the title (an agency name) stays a paragraph: the size-ranked title
    # is the document title, so the common title rule (M3a D6-1) leaves it alone (D14)
    data = typst_pdf(
        "*Agency Name*\n\n"
        "#text(size: 20pt)[Report Title]\n\n"
        f"{BODY_TEXT}\n\n"
        "#text(size: 16pt)[Chapter]\n\n"
        f"{BODY_TEXT}\n"
    )
    result = convert(Source(data, "a.pdf", Format.PDF), [Format.MD])
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD))
    headers = [(h.level, pf.stringify(h)) for h in back.doc.content if isinstance(h, pf.Header)]
    assert headers == [(1, "Report Title"), (2, "Chapter")]
    assert back.doc.content[0] == pf.Para(pf.Strong(pf.Str("Agency"), pf.Space(), pf.Str("Name")))
    assert back.doc.get_metadata("title") == "Report Title"


def test_whole_bold_heading_drops_strong(tmp_path):
    data = typst_pdf(
        "#text(size: 20pt)[*Big Title*]\n\n"
        f"{BODY_TEXT}\n\n"
        "#text(size: 16pt)[*Partly* bold]\n\n"
        f"{BODY_TEXT}\n"
    )
    doc = read_pdf(Source(data, "a.pdf", Format.PDF), Report("a.pdf", Format.PDF), str(tmp_path)).doc
    whole, _, partly, _ = doc.content
    assert whole == pf.Header(pf.Str("Big"), pf.Space(), pf.Str("Title"), level=1)
    assert partly == pf.Header(pf.Strong(pf.Str("Partly")), pf.Space(), pf.Str("bold"), level=2)


def test_bold_numbered_body_size_left_to_common_filter(tmp_path):
    # Latin text: bold Hangul in the bundled variable Noto is not named Bold
    text = "The body text of this section runs on for a while in plain words, long enough to set the body size."
    data = typst_pdf(f"{text}\n\n*1. Overview*\n\n{text}\n")
    doc = read_pdf(Source(data, "a.pdf", Format.PDF), Report("a.pdf", Format.PDF), str(tmp_path)).doc
    assert [type(b).__name__ for b in doc.content] == ["Para", "Para", "Para"]
    assert doc.content[1] == pf.Para(pf.Strong(pf.Str("1."), pf.Space(), pf.Str("Overview")))
    back = read_back(data)
    assert [type(b).__name__ for b in back.content] == ["Para", "Header", "Para"]
    assert pf.stringify(back.content[1]) == "1. Overview"
