from __future__ import annotations

from pathlib import Path

import panflute as pf
import pytest
from docx_builder import strip_mdcast_metadata
from helpers import builtin_hwpx, export, tiny_png, write_template

from mdcast.filters.importing import ImportContext, run_import_filters
from mdcast.readers.docx import read_docx
from mdcast.readers.hwpx import read_hwpx
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


def hwpx_back(tmp_path: Path, md: str, name: str | None):
    report = Report("a.hwpx", Format.HWPX)
    imp = read_hwpx(Source(export(tmp_path, md, Format.HWPX, name), "a.hwpx", Format.HWPX), report, "a_assets")
    ctx = ImportContext(report, dict(imp.frontmatter), imp.generator, tmp_path, tmp_path / "home")
    return run_import_filters(imp.doc, ctx), ctx


def wide_png() -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (1200, 300), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.parametrize("picture", [tiny_png, wide_png], ids=["caption-paragraph", "hp-caption"])
def test_hwpx_bold_headings_and_captions_are_undone(tmp_path, picture):
    # hwpx puts the template's bold on the runs (Strong around the whole heading or caption), and
    # sets a figure caption as a paragraph of its own (or the picture's hp:caption) after the picture
    name = template(tmp_path)
    (tmp_path / "a.png").write_bytes(picture())
    md = (
        "# 개요\n\n## 세부\n\nTable: 예산\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "![샘플 그림](a.png)\n\n![](a.png)\n\n다음 글\n"
    )
    doc, ctx = hwpx_back(tmp_path, md, name)
    assert [pf.stringify(h) for h in headers(doc)] == ["개요", "세부"]
    table = first(doc, pf.Table)
    assert caption_text(table) == "예산" and not strongs(table.caption)
    figures = blocks(doc, pf.Figure)
    assert len(figures) == 1 and pf.stringify(figures[0].caption).strip() == "샘플 그림"
    assert not strongs(figures[0].caption)
    assert len(blocks(doc, pf.Image)) == 2  # the uncaptioned picture stays a paragraph of its own
    assert pf.stringify(doc.content[-1]).strip() == "다음 글"
    assert ctx.frontmatter["template"] == name


def test_hwpx_figure_caption_not_in_template_format_stays_a_paragraph(tmp_path):
    (tmp_path / "a.png").write_bytes(tiny_png())
    doc, _ = hwpx_back(tmp_path, "![](a.png)\n\n그림 설명이 아닌 글\n", None)
    assert not blocks(doc, pf.Figure)
    assert pf.stringify(doc.content[-1]).strip() == "그림 설명이 아닌 글"


MARKED = (
    "# 제목\n\n본문 `인라인 코드`와 **`굵은 코드`** 그리고 $E = mc^2$.\n\n"
    "```python\ndef hello():\n    print(\"안녕\")\n```\n\n```\nA-->B\n```\n\n"
    "> 인용 하나\n>\n> 인용 둘\n\n---\n\n$$\\int_0^1 x^2 dx$$\n\n| `칸 코드` |\n|---|\n| 값 |\n\n끝[^1]\n\n[^1]: 각주 `코드`\n"
)


def _strip_hwpx_metadata(data: bytes) -> bytes:
    """The same hwpx without its ``mdcast.*`` metadata: someone else's document."""
    import io
    import re
    import zipfile

    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            blob = source.read(info.filename)
            if info.filename == "Contents/content.hpf":
                blob = re.sub(rb'<opf:meta name="mdcast\.[^"]*"[^>]*>[^<]*</opf:meta>', b"", blob)
            target.writestr(info, blob)
    return out.getvalue()


def _spans(doc: pf.Doc) -> list:
    return blocks(doc, pf.Span)


def test_hwpx_code_quote_and_rule_marks_are_recovered(tmp_path):
    doc, _ = hwpx_back(tmp_path, MARKED, None)
    assert not _spans(doc)  # every hint is taken out again
    codes = [c.text for c in blocks(doc, pf.Code)]
    assert codes == ["인라인 코드", "굵은 코드", "E = mc^2", "\\int_0^1 x^2 dx", "칸 코드", "코드"]
    assert isinstance(first(doc, pf.Code).parent, pf.Para)
    assert isinstance(blocks(doc, pf.Code)[1].parent, pf.Strong)  # bold code stays bold code
    # code blocks side by side join (as docx, M3a §5.4 b); indentation and breaks kept
    assert [b.text for b in blocks(doc, pf.CodeBlock)] == ['def hello():\n    print("안녕")\nA-->B']
    quote = first(doc, pf.BlockQuote)
    assert [pf.stringify(b).strip() for b in quote.content] == ["인용 하나", "인용 둘"]
    assert len(blocks(doc, pf.HorizontalRule)) == 1
    # math is code text, never Math (M3b §5.3); a display equation is a paragraph of code
    assert not blocks(doc, pf.Math)


def test_hwpx_marks_follow_the_template_code_font(tmp_path):
    write_template(tmp_path / ".mdcast" / "templates", "mono", "name: mono\nfonts:\n  code: {family: D2Coding}\n")
    doc, _ = hwpx_back(tmp_path, "글 `코드`\n\n```\n블록\n```\n", "mono")
    assert [c.text for c in blocks(doc, pf.Code)] == ["코드"]
    assert [b.text for b in blocks(doc, pf.CodeBlock)] == ["블록"]


def test_hwpx_marks_are_not_read_without_mdcast_metadata(tmp_path):
    data = _strip_hwpx_metadata(export(tmp_path, MARKED, Format.HWPX, None))
    report = Report("a.hwpx", Format.HWPX)
    imp = read_hwpx(Source(data, "a.hwpx", Format.HWPX), report, "a_assets")
    assert imp.generator == {}
    ctx = ImportContext(report, dict(imp.frontmatter), imp.generator, tmp_path, tmp_path / "home")
    doc = run_import_filters(imp.doc, ctx)
    # spec §4.2 for someone else's hwpx: fonts, colours and borders are dropped
    for cls in (pf.Span, pf.Code, pf.CodeBlock, pf.BlockQuote, pf.HorizontalRule):
        assert not blocks(doc, cls), cls.__name__
    assert "인라인 코드" in pf.stringify(doc) and "A-->B" in pf.stringify(doc)


@pytest.mark.parametrize(("background", "color"), [("f6f8fa", "'#555'"), ("'#abc'", "336699")])
def test_hwpx_marks_match_colours_written_short_or_without_hash(tmp_path, background, color):
    # the writer normalises template colours (#RGB, no #) to #RRGGBB; matching must do the same
    yaml_text = f"name: colours\nelements:\n  code: {{background: {background}}}\n  quote: {{color: {color}}}\n"
    write_template(tmp_path / ".mdcast" / "templates", "colours", yaml_text)
    doc, _ = hwpx_back(tmp_path, "```\n줄 하나\n줄 둘\n```\n\n> 인용\n", "colours")
    assert [type(b).__name__ for b in doc.content] == ["CodeBlock", "BlockQuote"]
    assert doc.content[0].text == "줄 하나\n줄 둘"


def test_hwpx_marks_in_a_custom_container_follow_only_what_the_template_wrote(tmp_path):
    # a custom reference.hwpx takes only the template's own values: an explicit code font but no
    # explicit code background writes the code block with no fill, which must still read back
    yaml_text = "name: own\nfonts:\n  code: {family: D2Coding}\n"
    write_template(tmp_path / ".mdcast" / "templates", "own", yaml_text, {"reference.hwpx": builtin_hwpx()})
    doc, _ = hwpx_back(tmp_path, "글 `코드`\n\n```\n줄 하나\n줄 둘\n```\n", "own")
    assert [c.text for c in blocks(doc, pf.Code)] == ["코드"]
    assert [b.text for b in blocks(doc, pf.CodeBlock)] == ["줄 하나\n줄 둘"]
    assert not blocks(doc, pf.Span)
