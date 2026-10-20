from __future__ import annotations

from pathlib import Path

import panflute as pf

from docx_builder import strip_mdcast_metadata
from helpers import export, write_template
from mdcast.filters.importing import ImportContext, run_import_filters
from mdcast.readers.docx import read_docx
from mdcast.report import Codes, Report
from mdcast.types import Format, Source

NUMBERED = """
name: tpl
headings:
  numbering: ["Ⅰ.", "1."]
layout:
  page_break:
    before: [h1]
tables:
  variants:
    plain: {header: {background: null}}
"""
NO_RULE = "name: tpl2\ntables: {variants: {plain: {header: {background: null}}}}\n"


def template(tmp_path: Path, yaml_text: str = NUMBERED) -> str:
    name = "tpl" if yaml_text == NUMBERED else "tpl2"
    write_template(tmp_path / ".mdcast" / "templates", name, yaml_text)
    return name


def read_back(tmp_path: Path, data: bytes):
    report = Report("a.docx", Format.DOCX)
    imp = read_docx(Source(data, "a.docx", Format.DOCX), report, "a_assets")
    ctx = ImportContext(
        report, dict(imp.frontmatter), imp.generator, tmp_path, tmp_path / "home", table_styles=imp.table_styles
    )
    return run_import_filters(imp.doc, ctx), ctx


def import_back(tmp_path: Path, md: str, name: str | None):
    return read_back(tmp_path, export(tmp_path, md, Format.DOCX, name))


def blocks(doc: pf.Doc, cls: type) -> list:
    found: list = []
    doc.walk(lambda e, _d: found.append(e) if isinstance(e, cls) else None)
    return found


def first(doc: pf.Doc, cls: type):
    return blocks(doc, cls)[0]


def headers(doc: pf.Doc) -> list[pf.Header]:
    return blocks(doc, pf.Header)


def raw_blocks(doc: pf.Doc) -> list[str]:
    return [b.text for b in blocks(doc, pf.RawBlock)]


def count_pagebreaks(doc: pf.Doc) -> int:
    return raw_blocks(doc).count("<!-- pagebreak -->")


def caption_text(table: pf.Table) -> str:
    return pf.stringify(table.caption).strip()


def strongs(elem: pf.Element) -> list:
    found: list = []
    elem.walk(lambda e, _d: found.append(e) if isinstance(e, pf.Strong) else None)
    return found


def test_numbers_captions_and_rule_breaks_are_removed(tmp_path):
    name = template(tmp_path)
    md = (
        "# 개요\n\n본문\n\n# 계획\n\n## 세부\n\nTable: 예산\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "<!-- pagebreak -->\n\n끝\n"
    )
    doc, ctx = import_back(tmp_path, md, name)
    assert [pf.stringify(h) for h in headers(doc)] == ["개요", "계획", "세부"]
    assert caption_text(first(doc, pf.Table)) == "예산"
    assert count_pagebreaks(doc) == 1
    assert ctx.frontmatter["template"] == name
    assert ctx.prefixes


def test_table_kind_marker_is_restored(tmp_path):
    name = template(tmp_path, NO_RULE)
    md = "| a |\n|---|\n| 1 |\n\n<!-- table: plain -->\n\n| b |\n|---|\n| 2 |\n"
    doc, _ = import_back(tmp_path, md, name)
    assert raw_blocks(doc) == ["<!-- table: plain -->"]
    content = list(doc.content)
    marker = next(b for b in content if isinstance(b, pf.RawBlock))
    assert isinstance(content[content.index(marker) + 1], pf.Table)
    assert isinstance(content[content.index(marker) - 1], pf.Table)


def test_table_kind_without_template_variant_adds_no_marker(tmp_path):
    md = "| a |\n|---|\n| 1 |\n\n<!-- table: plain -->\n\n| b |\n|---|\n| 2 |\n"
    doc, _ = import_back(tmp_path, md, None)
    assert raw_blocks(doc) == []


def test_header_cells_lose_whole_cell_strong_in_mdcast_doc(tmp_path):
    name = template(tmp_path, NO_RULE)
    doc, _ = import_back(tmp_path, "| 항목 | 값 |\n|---|---|\n| **가** | 1 |\n", name)
    table = first(doc, pf.Table)
    head = table.head.content[0].content
    assert [pf.stringify(c) for c in head] == ["항목", "값"]
    assert not any(strongs(c) for c in head)
    assert strongs(table.content[0].content[0].content[0])


def test_unknown_template_falls_back_to_default_with_warn(tmp_path):
    name = template(tmp_path)
    data = export(tmp_path, "# 개요\n\n# 계획\n\n표\n", Format.DOCX, name)
    other = tmp_path / "elsewhere"
    other.mkdir()
    doc, ctx = read_back(other, data)
    assert ctx.frontmatter["template"] == name
    assert len([e for e in ctx.report.events if e.code == Codes.TEMPLATE_NOT_FOUND]) == 1
    # the default template has no numbering, so the exported numbers are left as text
    assert [pf.stringify(h) for h in headers(doc)] == ["Ⅰ. 개요", "Ⅱ. 계획"]


def test_third_party_doc_untouched(tmp_path):
    name = template(tmp_path)
    data = strip_mdcast_metadata(export(tmp_path, "# 개요\n\n# 계획\n\nTable: 예산\n\n| a |\n|---|\n| 1 |\n", Format.DOCX, name))
    doc, ctx = read_back(tmp_path, data)
    assert [pf.stringify(h) for h in headers(doc)] == ["Ⅰ. 개요", "Ⅱ. 계획"]
    assert caption_text(first(doc, pf.Table)) == "<표 1> 예산"
    assert "template" not in ctx.frontmatter
    assert strongs(first(doc, pf.Table).head)


def test_text_that_is_not_the_replayed_number_stays(tmp_path):
    name = template(tmp_path)
    doc, _ = import_back(tmp_path, "# Ⅹ. 직접 쓴 번호\n\n# 계획\n", name)
    assert [pf.stringify(h) for h in headers(doc)] == ["Ⅹ. 직접 쓴 번호", "계획"]
