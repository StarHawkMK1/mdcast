import panflute as pf

from mdcast.ast import md_to_doc
from mdcast.filters import numbering
from mdcast.filters.context import FilterContext
from mdcast.report import Report
from mdcast.templates.schema import deep_merge, load_builtin_default
from mdcast.types import Format


def run(md, overrides=None):
    config = deep_merge(load_builtin_default(), overrides or {})
    ctx = FilterContext(Format.DOCX, config, {}, Report("a.md", Format.MD))
    return numbering.apply(md_to_doc(md), ctx)


def headers(doc):
    found = []
    doc.walk(lambda e, d: found.append(pf.stringify(e)) if isinstance(e, pf.Header) else None)
    return found


def captions(doc):
    found = []

    def grab(e, d):
        if isinstance(e, (pf.Table, pf.Figure)) and e.caption is not None:
            found.append(pf.stringify(e.caption))

    doc.walk(grab)
    return found


def test_heading_numbers_reset_deeper_levels():
    doc = run("# 개요\n\n## 배경\n\n## 목적\n\n# 계획\n\n## 일정\n", {"headings": {"numbering": ["Ⅰ.", "1."]}})
    assert headers(doc) == ["Ⅰ. 개요", "1. 배경", "2. 목적", "Ⅱ. 계획", "1. 일정"]


def test_levels_beyond_patterns_and_unnumbered_are_skipped():
    doc = run("# A\n\n### deep\n\n# 부록 {.unnumbered}\n\n# B\n", {"headings": {"numbering": ["Ⅰ."]}})
    assert headers(doc) == ["Ⅰ. A", "deep", "부록", "Ⅱ. B"]


def test_no_patterns_means_no_change():
    assert headers(run("# A\n\n## B\n")) == ["A", "B"]


def test_table_and_figure_captions_numbered_independently():
    md = (
        "Table: 요약\n\n| a |\n|---|\n| 1 |\n\n"
        "![구성도](x.png)\n\n"
        "Table: 둘째\n\n| b |\n|---|\n| 2 |\n"
    )
    assert captions(run(md)) == ["<표 1> 요약", "[그림 1] 구성도", "<표 2> 둘째"]


def test_uncaptioned_table_is_not_numbered():
    # Controller ruling B1: pandoc attaches a "Table:" line to the table next to it,
    # so the uncaptioned table goes last to keep the captioned table's caption unambiguous.
    md = "Table: 캡션\n\n| a |\n|---|\n| 1 |\n\n| b |\n|---|\n| 2 |\n"
    assert captions(run(md)) == ["<표 1> 캡션", ""]
