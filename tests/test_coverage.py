from __future__ import annotations

import re

import pytest

from mdcast.coverage import measure_coverage
from mdcast.report import Codes, Report
from mdcast.types import Format


def make_report() -> Report:
    return Report("a.docx", Format.DOCX)


def missing_events(report: Report):
    return [e for e in report.events if e.code == Codes.IMPORT_TEXT_MISSING]


def test_full_coverage_ignores_whitespace_markers_and_escapes():
    r = make_report()
    src = ["□ 첫 항목", "2) 둘째", "1. 개요", "칸 글"]
    md = "- 첫 항목\n\n2. 둘째\n\n# 1. 개요\n\n| 칸 글 |\n|---|\n"
    assert measure_coverage(src, md, r) == 1.0
    assert not missing_events(r)
    assert r.coverage == 1.0


def test_missing_paragraph_is_warned_with_snippet():
    r = make_report()
    value = measure_coverage(["있는 글", "사라진 문단입니다"], "있는 글\n", r)
    assert value == pytest.approx(3 / 11, abs=0.01)
    ev = missing_events(r)[0]
    assert "사라진 문단" in ev.message and "(1문단)" in ev.message and r.coverage == value


def test_numbered_heading_kept_and_list_marker_dropped():
    r = make_report()
    src = ["1. 개요", "가. 항목", "본문"]
    md = "# 1. 개요\n\n- 항목\n\n본문\n"
    assert measure_coverage(src, md, r) == 1.0
    assert not missing_events(r)


def test_prefix_patterns_strip_only_at_start():
    r = make_report()
    prefix = re.compile(r"^그림\s*\d+\.\s*")
    assert measure_coverage(["그림 1. 설명글"], "설명글\n", r, [prefix]) == 1.0
    r2 = make_report()
    assert measure_coverage(["설명글 그림 1."], "설명글\n", r2, [prefix]) < 1.0


def test_footnote_text_counts():
    r = make_report()
    md = "본문[^1]\n\n[^1]: 각주 내용입니다\n"
    assert measure_coverage(["본문", "각주 내용입니다"], md, r) == 1.0
    assert not missing_events(r)


def test_footnote_mark_inside_a_sentence_does_not_split_it():
    # the source paragraph has no text at the mark (w:footnoteReference), the note text is its own paragraph
    r = make_report()
    md = "앞 글에 각주[^1]가 있는 문장.\n\n[^1]: 각주 내용입니다\n"
    assert measure_coverage(["앞 글에 각주가 있는 문장.", "각주 내용입니다"], md, r) == 1.0
    assert not missing_events(r)


def test_empty_source_is_full():
    r = make_report()
    assert measure_coverage([], "무엇이든\n", r) == 1.0
    assert r.coverage == 1.0 and not missing_events(r)


def test_snippets_are_capped_at_three_and_truncated():
    r = make_report()
    src = ["가" * 30, "나나나", "다다다", "라라라"]
    measure_coverage(src, "\n", r)
    msg = missing_events(r)[0].message
    assert "(4문단)" in msg and "'" + "가" * 20 + "…'" in msg and "라라라" not in msg
