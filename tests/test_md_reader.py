import panflute as pf
import pytest

import mdcast.readers.md as md_module
from mdcast.readers.md import read_md
from mdcast.report import Codes, Level, Report
from mdcast.types import Format, Source


def read(data: bytes):
    report = Report("a.md", Format.MD)
    return read_md(Source(data, "a.md", Format.MD), report), report


def test_frontmatter_and_body():
    md, r = read("---\ntitle: 사업계획\nn: 3\nl: [a, b]\npage_break: {before: [h2]}\n---\n\n# 개요\n".encode())
    assert md.frontmatter == {"title": "사업계획", "n": "3", "l": ["a", "b"], "page_break": {"before": ["h2"]}}
    assert isinstance(md.doc.content[0], pf.Header)
    assert r.events == []


def test_bom_is_ignored():
    md, r = read(("\ufeff# 제목\n").encode())
    assert pf.stringify(md.doc.content[0]) == "제목"
    assert r.events == []


def test_cp949_input_is_read_with_info():
    md, r = read("# 제목\n\n본문입니다\n".encode("cp949"))
    assert pf.stringify(md.doc.content[0]) == "제목"
    assert [(e.level, e.code) for e in r.events] == [(Level.INFO, Codes.INPUT_ENCODING_FALLBACK)]


def test_pagebreak_marker_survives_as_raw_html():
    md, _ = read(b"a\n\n<!-- pagebreak -->\n\nb\n")
    raw = md.doc.content[1]
    assert isinstance(raw, pf.RawBlock) and raw.format == "html"


def test_html_table_becomes_table_with_spans():
    html = (
        "<table><thead><tr><th rowspan=\"2\">구분</th><th colspan=\"2\">값</th></tr>"
        "<tr><th>a</th><th>b</th></tr></thead>"
        "<tbody><tr><td>X</td><td>1</td><td>2</td></tr></tbody></table>\n"
    )
    md, _ = read(html.encode())
    table = md.doc.content[0]
    assert isinstance(table, pf.Table)
    first_head_row = table.head.content[0].content
    assert (first_head_row[0].rowspan, first_head_row[1].colspan) == (2, 2)


def test_empty_input():
    md, _ = read(b"")
    assert list(md.doc.content) == [] and md.frontmatter == {}


def test_undecodable_input_is_read_with_replacement_and_warn():
    md, r = read(b"# \xff\xfe\n")
    assert isinstance(md.doc.content[0], pf.Header)
    assert [(e.level, e.code) for e in r.events] == [(Level.WARN, Codes.INPUT_ENCODING_FALLBACK)]


def test_malformed_frontmatter_is_dropped_with_warn():
    md, r = read("---\ntitle: [a\nx: : y\n---\n\n본문\n".encode())
    assert md.frontmatter == {}
    assert pf.stringify(md.doc).strip() == "본문"
    assert [(e.level, e.code) for e in r.events] == [(Level.WARN, Codes.FRONTMATTER_INVALID)]


def test_pandoc_failure_without_frontmatter_still_raises(monkeypatch):
    def fail(_text):
        raise RuntimeError("Pandoc died with exitcode 64")

    monkeypatch.setattr(md_module, "md_to_doc", fail)
    with pytest.raises(RuntimeError):
        read(b"# a\n")


def test_footnote_inside_html_table_cell_becomes_note():
    md = ("본문[^a].\n\n"
          '<table><tr><td rowspan="2">칸[^t1] 끝</td><td>b</td></tr><tr><td>c</td></tr></table>\n\n'
          "[^t1]: 칸 각주.\n\n    둘째 문단.\n[^a]: 본문 각주.\n")
    doc = read_md(Source(md.encode(), "t.md", Format.MD), Report("t.md", Format.MD)).doc
    notes = []
    doc.walk(lambda e, d: notes.append(pf.stringify(e).strip()) if isinstance(e, pf.Note) else None)
    assert "본문 각주." in notes
    assert any(n.startswith("칸 각주.") and "둘째 문단." in n for n in notes)
    table = next(b for b in doc.content if isinstance(b, pf.Table))
    assert "[^t1]" not in pf.stringify(table)
    assert "칸" in pf.stringify(table) and "끝" in pf.stringify(table)


def test_unknown_label_in_cell_stays_text():
    md = "<table><tr><td>x[^nope]</td></tr></table>\n"
    doc = read_md(Source(md.encode(), "t.md", Format.MD), Report("t.md", Format.MD)).doc
    assert "[^nope]" in pf.stringify(doc)
