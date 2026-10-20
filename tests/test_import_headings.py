from __future__ import annotations

from pathlib import Path

import panflute as pf

from mdcast.filters.importing import ImportContext, run_import_filters
from mdcast.filters.importing.markers import heading_shape, list_marker, strip_leading_marker
from mdcast.report import Codes, Level, Report
from mdcast.types import Format


def inlines(text: str) -> list[pf.Inline]:
    out: list[pf.Inline] = []
    for i, word in enumerate(text.split(" ")):
        if i:
            out.append(pf.Space())
        out.append(pf.Str(word))
    return out


def strong(text: str) -> pf.Strong:
    return pf.Strong(*inlines(text))


def para(text: str) -> pf.Para:
    return pf.Para(*inlines(text))


def para_b(text: str) -> pf.Para:
    return pf.Para(strong(text))


def header(level: int, content) -> pf.Header:
    items = inlines(content) if isinstance(content, str) else [content]
    return pf.Header(*items, level=level)


def table() -> pf.Table:
    cell = pf.TableCell(pf.Plain(pf.Str("칸")))
    body = pf.TableBody(pf.TableRow(cell))
    return pf.Table(body, head=pf.TableHead(), colspec=[("AlignDefault", "ColWidthDefault")])


class Run:
    def __init__(self, *blocks, frontmatter=None):
        self.report = Report("a.docx", Format.DOCX)
        self.ctx = ImportContext(self.report, dict(frontmatter or {}), {}, Path("."), Path("."))
        self.doc = run_import_filters(pf.Doc(*blocks), self.ctx)

    @property
    def levels(self):
        return [(pf.stringify(b).strip(), b.level) for b in self.doc.content if isinstance(b, pf.Header)]

    def events(self, level: Level):
        return [e for e in self.report.events if e.code == Codes.IMPORT_HEADING_INFERRED and e.level is level]


def test_bold_numbered_paragraphs_become_headings_by_first_appearance():
    r = Run(para_b("1. 개요"), para("본문"), para_b("가. 배경"), para("본문"), para_b("2. 계획"))
    assert r.levels == [("1. 개요", 1), ("가. 배경", 2), ("2. 계획", 1)]


def test_dotted_decimal_without_bold_is_one_below_its_parent():
    r = Run(header(1, "1. 일반사항"), para("본문"), para("1.1 시험대상 제품"), para("본문"))
    assert r.levels == [("1. 일반사항", 1), ("1.1 시험대상 제품", 2)]


def test_dotted_decimal_without_bold_only_under_its_own_number():
    r = Run(header(1, "1. 일반사항"), para("2.1 시험대상 제품"), header(1, "2. 시험"), para("2.1 시험 방법"))
    assert r.levels == [("1. 일반사항", 1), ("2. 시험", 1), ("2.1 시험 방법", 2)]
    assert isinstance(r.doc.content[1], pf.Para)


def test_dotted_decimal_without_bold_needs_a_numbered_section():
    r = Run(header(1, "개요"), para("0.5 이하로 유지한다"), para("3.5 기준 적용"), para("1.1 항목"))
    assert r.levels == [("개요", 1)]
    r = Run(header(1, "1. 개요"), para("3.5 기준 적용"), header(1, "부록"), para("1.1 항목"))
    assert r.levels == [("1. 개요", 1), ("부록", 1)]


def test_leading_zero_and_dates_are_never_headings():
    r = Run(
        header(1, "1. 개요"),
        para_b("0.5 이하"),
        para_b("2026. 10. 21."),
        para("2026. 10. 21."),
        para_b("2026.10.21 기준"),
        para("1.0 판"),
    )
    assert r.levels == [("1. 개요", 1), ("1.0 판", 2)]


def test_any_existing_header_seeds_the_depth():
    r = Run(header(1, "개요"), para("본문"), para_b("1. 목적"), para("1.1 범위"))
    assert r.levels == [("개요", 1), ("1. 목적", 2), ("1.1 범위", 3)]


def test_dotted_decimal_before_base_is_known_sets_base():
    r = Run(para_b("Ⅰ. 서론"), para_b("1.1 배경"), para("본문"), para_b("2. 계획"))
    assert r.levels == [("Ⅰ. 서론", 1), ("1.1 배경", 2), ("2. 계획", 1)]


def test_outline_headers_seed_shape_levels():
    r = Run(header(1, "1. 개요"), para_b("2. 계획"), para_b("(1) 세부"))
    assert r.levels == [("1. 개요", 1), ("2. 계획", 1), ("(1) 세부", 2)]


def test_whole_strong_is_unwrapped_in_headings():
    r = Run(header(1, strong("1. 개요")))
    assert r.doc.content[0].content == pf.Header(pf.Str("1."), pf.Space(), pf.Str("개요")).content


def test_whole_strong_is_unwrapped_in_inferred_headings():
    r = Run(para_b("1. 개요"))
    assert [type(i).__name__ for i in r.doc.content[0].content] == ["Str", "Space", "Str"]


def test_document_title_before_first_heading():
    r = Run(table(), para_b("시 험 합 의 서"), para_b("1. 개요"), para("본문"))
    assert r.levels == [("시 험 합 의 서", 1), ("1. 개요", 2)]
    assert r.ctx.frontmatter["title"] == "시 험 합 의 서"
    assert all(not isinstance(i, pf.Strong) for i in r.doc.content[1].content)


def test_document_title_shifts_existing_headers_and_caps_at_six():
    r = Run(para_b("제목"), header(1, "1. 가"), header(6, "깊음"))
    assert r.levels == [("제목", 1), ("1. 가", 2), ("깊음", 6)]


def test_core_title_wins_for_frontmatter():
    r = Run(para_b("문서 제목"), para_b("1. 개요"), frontmatter={"title": "코어 제목"})
    assert r.ctx.frontmatter["title"] == "코어 제목"
    assert r.levels[0] == ("문서 제목", 1)


def test_info_counts_promoted_paragraphs():
    r = Run(para_b("제목"), para_b("1. 개요"), para_b("2. 계획"))
    infos = r.events(Level.INFO)
    assert len(infos) == 1
    assert "3" in infos[0].message


def test_not_headings():
    r = Run(para_b("1.5배 증가했다"), para("1. 굵지 않은 문장"), para_b("가" * 61), para_b("※ 참고"))
    assert r.levels == []


def test_numbered_inside_quote_or_list_is_not_inspected():
    r = Run(pf.BlockQuote(para_b("1. 인용 안")), pf.BulletList(pf.ListItem(para_b("2. 목록 안"))))
    assert r.levels == []


def test_no_headings_warns_once():
    r = Run(para("편지 본문"), para("끝"))
    assert [e.level for e in r.report.events if e.code == "IMPORT_HEADING_INFERRED"] == [Level.WARN]


def test_plain_letter_with_bold_first_line_gets_no_title():
    r = Run(para_b("안내문"), para("본문"))
    assert r.levels == []
    assert "title" not in r.ctx.frontmatter
    assert len(r.events(Level.WARN)) == 1


def test_no_inference_means_no_info():
    r = Run(header(1, "개요"), para("본문"))
    assert r.events(Level.INFO) == []
    assert r.events(Level.WARN) == []


def test_heading_shape():
    assert heading_shape("1. 개요") == ("decimal", 1)
    assert heading_shape("1.1 개요") == ("decimal", 2)
    assert heading_shape("1.1. 개요") == ("decimal", 2)
    assert heading_shape("1.1.1 개요") == ("decimal", 3)
    assert heading_shape("1 개요") is None
    assert heading_shape("1.5배") is None
    assert heading_shape("Ⅱ. 계획") == ("roman", 1)
    assert heading_shape("가. 배경") == ("hangul", 1)
    assert heading_shape("(1) 세부") == ("paren_decimal", 1)
    assert heading_shape("(나) 세부") == ("paren_hangul", 1)
    assert heading_shape("힣. 아님") is None
    assert heading_shape("※ 참고") is None


def test_list_marker():
    assert list_marker("□ 가") == ("□", "bullet", None)
    assert list_marker("3) 셋") == ("decimal_paren", "ordered", 3)
    assert list_marker("2. 둘") == ("decimal_dot", "ordered", 2)
    assert list_marker("(4) 넷") == ("paren_decimal", "ordered", 4)
    assert list_marker("③ 셋") == ("circled", "ordered", 3)
    assert list_marker("⑳ 스물") == ("circled", "ordered", 20)
    assert list_marker("나. 둘") == ("hangul_dot", "ordered", 2)
    assert list_marker("다) 셋") == ("hangul_paren", "ordered", 3)
    assert list_marker("(하) 열넷") == ("paren_hangul", "ordered", 14)
    assert list_marker("※ 주석") is None
    assert list_marker("-혼자") is None
    assert list_marker("- 대시") == ("-", "bullet", None)
    assert list_marker("본문") is None


def test_strip_leading_marker():
    assert strip_leading_marker("○ 나") == "나"
    assert strip_leading_marker("3) 셋") == "셋"
    assert strip_leading_marker("1.1 개요") == "개요"
    assert strip_leading_marker("본문") == "본문"
