from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape, quoteattr

import panflute as pf
import pytest
from helpers import tiny_bmp, tiny_png
from hwpx_builder import cell, hwpx_bytes, p, pic, run, tbl, textbox
from lxml import etree

from mdcast.ast import grid_cells
from mdcast.pipeline import convert
from mdcast.readers.docx_package import PAGEBREAK_SENTINEL
from mdcast.readers.hwpx import read_hwpx
from mdcast.readers.hwpx.body import BodyReader
from mdcast.readers.hwpx.package import HP, CharStyle, HwpxError, ParaStyle, open_hwpx
from mdcast.readers.md import read_md
from mdcast.report import Report
from mdcast.types import Format, Source


def _replace(data: bytes, name: str, blob: bytes) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            target.writestr(info, blob if info.filename == name else source.read(info.filename))
    return out.getvalue()


def test_open_reads_spine_order_styles_and_meta():
    data = hwpx_bytes(
        p(run("첫")),
        p(run("둘")),
        title="제목",
        meta={"mdcast.generator": "mdcast 0.1", "creator": "홍"},
    )
    pkg = open_hwpx(data)
    assert len(pkg.sections) == 2 and pkg.title == "제목" and pkg.creator == "홍"
    assert pkg.generator == {"mdcast.generator": "mdcast 0.1"}
    assert pkg.styles.chars["1"].bold and pkg.styles.paras["3"] == ParaStyle("NUMBER", 0, "1", "JUSTIFY")
    assert pkg.styles.numbering_start["2"] == 3


def test_sections_follow_spine_order_not_manifest_order():
    data = hwpx_bytes(p(run("첫")), p(run("둘")))
    content = zipfile.ZipFile(io.BytesIO(data)).read("Contents/content.hpf").decode()
    forward = '<opf:itemref idref="section0"/><opf:itemref idref="section1"/>'
    assert forward in content
    swapped = content.replace(
        forward, '<opf:itemref idref="section1"/><opf:itemref idref="section0"/>'
    )
    pkg = open_hwpx(_replace(data, "Contents/content.hpf", swapped.encode()))
    assert ["".join(section.itertext()) for section in pkg.sections] == ["둘", "첫"]


def test_fixed_header_ids_map_to_styles():
    styles = open_hwpx(hwpx_bytes(p(run("a")))).styles
    assert styles.chars == {
        "0": CharStyle(),
        "1": CharStyle(bold=True),
        "2": CharStyle(italic=True),
        "3": CharStyle(superscript=True),
        "4": CharStyle(subscript=True),
        "5": CharStyle(strike=True),
    }
    assert styles.paras == {
        "0": ParaStyle(align="JUSTIFY"),
        "1": ParaStyle("OUTLINE", 0, align="JUSTIFY"),
        "2": ParaStyle("OUTLINE", 1, align="JUSTIFY"),
        "3": ParaStyle("NUMBER", 0, "1", "JUSTIFY"),
        "4": ParaStyle("NUMBER", 1, "1", "JUSTIFY"),
        "5": ParaStyle("BULLET", 0, "1", "JUSTIFY"),
        "6": ParaStyle("NUMBER", 0, "2", "JUSTIFY"),
    }
    assert styles.numbering_start == {"1": 1, "2": 3}


def test_empty_meta_values_are_absent():
    pkg = open_hwpx(hwpx_bytes(p(run("a")), meta={"mdcast.generator": "", "mdcast.template": "t"}))
    assert pkg.title is None and pkg.creator is None
    assert pkg.generator == {"mdcast.template": "t"}


def test_bin_data_keyed_by_manifest_id():
    pkg = open_hwpx(hwpx_bytes(p(run("a")), bin_data={"image1.png": b"PNGDATA"}))
    assert pkg.bin_data == {"image1": ("image1.png", b"PNGDATA")}


def test_not_a_zip_is_hwpx_error():
    with pytest.raises(HwpxError):
        open_hwpx(b"x")


def test_missing_content_hpf_is_hwpx_error():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        target.writestr("mimetype", "application/hwp+zip")
    with pytest.raises(HwpxError):
        open_hwpx(out.getvalue())


def test_encrypted_package_is_hwpx_error_naming_security():
    with pytest.raises(HwpxError, match="암호|보안"):
        open_hwpx(hwpx_bytes(p(run("a")), encrypted=True))


def test_unreadable_section_is_hwpx_error_naming_security():
    data = _replace(hwpx_bytes(p(run("a"))), "Contents/section0.xml", b"\x93\x11\xfe garbled")
    with pytest.raises(HwpxError, match="암호|보안"):
        open_hwpx(data)


@pytest.mark.parametrize("part", ["Contents/content.hpf", "Contents/header.xml"])
def test_unreadable_content_or_header_is_hwpx_error_naming_security(part):
    data = _replace(hwpx_bytes(p(run("a"))), part, b"\x93\x11\xfe garbled")
    with pytest.raises(HwpxError, match="암호|보안") as caught:
        open_hwpx(data)
    assert part in str(caught.value)


def _read(*sections: str, **kw):
    report = Report("a.hwpx", Format.HWPX)
    return read_hwpx(Source(hwpx_bytes(*sections, **kw), "a.hwpx", Format.HWPX), report, "a_assets"), report


def read(*sections: str, **kw) -> tuple[pf.Doc, Report]:
    imported, report = _read(*sections, **kw)
    return imported.doc, report


def text(elem: pf.Element) -> str:
    return pf.stringify(elem, newlines=False)


def kinds(elems) -> list[str]:
    return [type(e).__name__ for e in elems]


def test_runs_keep_bold_italic_sup_sub_strike_and_breaks():
    doc, _ = read(p(run("굵", "1"), run("기", "2"), run("x"), run("2", "3")))
    para = doc.content[0]
    assert [type(i).__name__ for i in para.content] == ["Strong", "Emph", "Str", "Superscript"]

    doc, _ = read(p(run("H"), run("2", "4"), run("O "), run("지움", "5")))
    para = doc.content[0]
    assert kinds(para.content) == ["Str", "Subscript", "Str", "Space", "Strikeout"]
    assert text(para) == "H2O 지움"


def test_tab_and_line_break_inside_text():
    t = '<hp:run charPrIDRef="0"><hp:t>가<hp:tab width="0" leader="0" type="1"/>나<hp:lineBreak/>다</hp:t></hp:run>'
    doc, _ = read(p(t))
    assert kinds(doc.content[0].content) == ["Str", "Space", "Str", "LineBreak", "Str"]
    assert text(doc.content[0]) == "가 나 다"


def test_same_style_runs_merge_and_edge_spaces_leave_the_wrapper():
    doc, _ = read(p(run("본"), run("문 "), run("굵 ", "1"), run("게", "1"), run(" 끝 ")))
    para = doc.content[0]
    assert kinds(para.content) == ["Str", "Space", "Strong", "Space", "Str"]
    assert text(para.content[0]) == "본문"
    assert kinds(para.content[2].content) == ["Str", "Space", "Str"]
    assert text(para) == "본문 굵 게 끝"


def test_paragraphs_without_text_are_dropped():
    doc, _ = read(p(run("하나")), p(), p(run("   ")), p(run("둘")))
    assert [text(b) for b in doc.content] == ["하나", "둘"]


def test_unknown_run_children_keep_the_text_around_them():
    body = (
        '<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="0"><hp:secPr id=""/><hp:ctrl><hp:colPr id="" type="NEWSPAPER"/></hp:ctrl>'
        "<hp:t>앞<hp:markpenBegin/>표시<hp:markpenEnd/>뒤</hp:t></hp:run></hp:p>"
    )
    doc, _ = read(body)
    assert [text(b) for b in doc.content] == ["앞표시뒤"]


def test_unknown_style_ids_read_as_plain():
    doc, _ = read(p(run("글", "99"), para="99"))
    assert kinds(doc.content) == ["Para"] and kinds(doc.content[0].content) == ["Str"]


def test_outline_paragraphs_are_headers_and_page_break_leaves_sentinel():
    doc, _ = read(p(run("개요"), para="1"), p(run("세부"), para="2"), p(run("본문")), p(run("다음"), page_break=True))
    assert kinds(doc.content) == ["Header", "Header", "Para", "Para", "Para"]
    assert [b.level for b in doc.content[:2]] == [1, 2]
    assert text(doc.content[0]) == "개요"
    assert text(doc.content[3]) == PAGEBREAK_SENTINEL
    assert text(doc.content[4]) == "다음"


def test_page_break_on_an_empty_paragraph_still_leaves_sentinel():
    doc, _ = read(p(run("앞")), p(page_break=True), p(run("뒤")))
    assert [text(b) for b in doc.content] == ["앞", PAGEBREAK_SENTINEL, "뒤"]


def _with_para_pr(data: bytes, pid: str, kind: str, ref: str, level: str) -> bytes:
    """``data`` with one more paraPr in its header (ids from "7" on are free)."""
    para_pr = (
        f'<hh:paraPr id="{pid}" tabPrIDRef="0" condense="0"><hh:align horizontal="JUSTIFY" vertical="BASELINE"/>'
        f'<hh:heading type="{kind}" idRef="{ref}" level="{level}"/></hh:paraPr>'
    )
    header = zipfile.ZipFile(io.BytesIO(data)).read("Contents/header.xml").decode()
    header = header.replace("</hh:paraProperties>", para_pr + "</hh:paraProperties>")
    return _replace(data, "Contents/header.xml", header.encode())


@pytest.mark.parametrize(("level", "expected"), [("5", 6), ("7", 6), ("9", None)])
def test_deep_outline_levels_cap_at_six_and_nine_is_body(level, expected):
    data = _with_para_pr(hwpx_bytes(p(run("깊은"), para="7")), "7", "OUTLINE", "0", level)
    report = Report("a.hwpx", Format.HWPX)
    block = read_hwpx(Source(data, "a.hwpx", Format.HWPX), report, "a_assets").doc.content[0]
    if expected is None:
        assert isinstance(block, pf.Para)
    else:
        assert isinstance(block, pf.Header) and block.level == expected


def test_paragraph_in_cell_is_plain_without_sentinel():
    pkg = open_hwpx(hwpx_bytes(p(run("a"))))
    reader = BodyReader(pkg, Report("a.hwpx", Format.HWPX), None)
    xml = (
        f'<hp:p xmlns:hp="{HP}" id="0" paraPrIDRef="1" styleIDRef="0" pageBreak="1" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="1"><hp:t>칸 글</hp:t></hp:run></hp:p>'
    )
    blocks = reader.paragraph(etree.fromstring(xml), in_cell=True)
    assert kinds(blocks) == ["Plain"] and kinds(blocks[0].content) == ["Strong"]


def test_sections_are_read_in_spine_order():
    doc, _ = read(p(run("하나")), p(run("둘")))
    assert [text(b) for b in doc.content] == ["하나", "둘"]


def test_sections_keep_every_paragraph():
    imported, _ = _read(p(run("가")) + p(run("나")), p(run("다")) + p(run("라")), p(run("마")))
    assert [text(b) for b in imported.doc.content] == ["가", "나", "다", "라", "마"]
    assert imported.source_text == ["가", "나", "다", "라", "마"]


def test_source_text_has_one_entry_per_paragraph():
    table = tbl([[cell(p(run("칸 하나")), col=0, row=0), cell(p(run("칸 둘")), col=1, row=0)]], cols=2)
    imported, _ = _read(p(run("앞 "), run("굵게", "1"), table, run("뒤")), p(), p(run("끝")))
    # a paragraph's own text split where its table sits, then each paragraph of its tables on its
    # own line; empty ones are left out
    assert imported.source_text == ["앞 굵게", "뒤", "칸 하나", "칸 둘", "끝"]


def test_source_text_reads_tab_and_line_break_marks_as_whitespace():
    # a hand-typed list marker and its text are split by a tab: without the space the coverage
    # check could not take the marker off the source (``□하나``) the way the list filter did
    marked = (
        '<hp:run charPrIDRef="0"><hp:t>□<hp:tab width="0" leader="0" type="1"/>하나'
        "<hp:lineBreak/>둘</hp:t></hp:run>"
    )
    imported, _ = _read(p(marked))
    assert imported.source_text == ["□ 하나\n둘"]


def test_frontmatter_media_and_generator():
    imported, _ = _read(p(run("a")), title="제목", meta={"creator": "", "mdcast.template": "t"})
    assert imported.frontmatter == {"title": "제목"}
    assert imported.media == {} and imported.table_styles == []
    assert imported.generator == {"mdcast.template": "t"}
    imported, _ = _read(p(run("a")), meta={"creator": "홍"})
    assert imported.frontmatter == {"author": "홍"}


def test_read_hwpx_lets_hwpx_error_through():
    with pytest.raises(HwpxError, match="암호|보안"):
        _read(p(run("a")), encrypted=True)


def grid(table: pf.Table) -> list[list[tuple[str, int, int, int]]]:
    """Every row as (text, grid column, rowspan, colspan) per cell, head rows first."""
    rows = list(table.head.content) + [row for body in table.content for row in body.content]
    starts = {id(c): col for c, col in grid_cells(rows)}
    return [[(text(c), starts[id(c)], c.rowspan, c.colspan) for c in row.content] for row in rows]


def only_table(*runs: str) -> pf.Table:
    doc, _ = read(p(*runs))
    assert kinds(doc.content) == ["Table"]
    return doc.content[0]


def _row(texts: list[str], row: int, header: bool = False) -> list[str]:
    return [cell(p(run(t)), col=c, row=row, header=header) for c, t in enumerate(texts)]


def test_merged_cells_keep_spans_and_nested_table():
    inner = tbl([_row(["안1", "안2"], 0), _row(["안3", "안4"], 1)], cols=2)
    table = only_table(
        tbl(
            [
                [cell(p(run("가")), col=0, row=0, rowspan=2), cell(p(run("나")), col=1, row=0, colspan=2)],
                [cell(p(run("다")), col=1, row=1), cell(p(run("앞"), inner, run("뒤")), col=2, row=1)],
                _row(["라", "마", "바"], 2),
            ],
            cols=3,
        )
    )
    assert table.colspec == [("AlignDefault", "ColWidthDefault")] * 3
    assert grid(table) == [
        [("가", 0, 2, 1), ("나", 1, 1, 2)],
        [("다", 1, 1, 1), ("앞안1안2안3안4뒤", 2, 1, 1)],
        [("라", 0, 1, 1), ("마", 1, 1, 1), ("바", 2, 1, 1)],
    ]
    rows = list(table.head.content) + list(table.content[0].content)
    nested_cell = rows[1].content[1]
    assert kinds(nested_cell.content) == ["Para", "Table", "Para"]
    nested = nested_cell.content[1]
    assert grid(nested) == [[("안1", 0, 1, 1), ("안2", 1, 1, 1)], [("안3", 0, 1, 1), ("안4", 1, 1, 1)]]
    assert len(nested.head.content) == 1 and len(nested.content[0].content) == 1


def test_header_marks_make_head_rows():
    def head_rows(marks: list[bool]) -> tuple[int, int]:
        rows = [_row([f"{r}a", f"{r}b"], r, mark) for r, mark in enumerate(marks)]
        table = only_table(tbl(rows, cols=2))
        assert [c[0] for row in grid(table) for c in row] == [f"{r}{c}" for r in range(len(marks)) for c in "ab"]
        return len(table.head.content), sum(len(body.content) for body in table.content)

    assert head_rows([True, True, False]) == (2, 1)  # marked rows from the top
    assert head_rows([False, False, False]) == (1, 2)  # no mark at all: the first row
    assert head_rows([False, True, False]) == (0, 3)  # marks not from the top: no head
    assert head_rows([True, False, True]) == (1, 2)
    rows = [[cell(p(run("a")), col=0, row=0, header=True), cell(p(run("b")), col=1, row=0)], _row(["c", "d"], 1)]
    assert len(only_table(tbl(rows, cols=2)).head.content) == 0  # a partly marked first row is no head


def test_table_head_grows_over_its_row_spans():
    # pandoc cuts a head cell's rowspan at the end of the head, which would move the cells below
    rows = [
        [cell(p(run("구분")), col=0, row=0, rowspan=2), cell(p(run("값")), col=1, row=0, colspan=2)],
        [cell(p(run("상")), col=1, row=1), cell(p(run("하")), col=2, row=1)],
        _row(["x", "y", "z"], 2),
    ]
    table = only_table(tbl(rows, cols=3))
    assert len(table.head.content) == 2
    assert grid(table)[2] == [("x", 0, 1, 1), ("y", 1, 1, 1), ("z", 2, 1, 1)]

    # a head that would take every row is no head
    rows = [[cell(p(run("세로")), col=0, row=0, rowspan=2), cell(p(run("a")), col=1, row=0)], [cell(p(run("b")), col=1, row=1)]]
    table = only_table(tbl(rows, cols=2))
    assert len(table.head.content) == 0
    assert grid(table) == [[("세로", 0, 2, 1), ("a", 1, 1, 1)], [("b", 1, 1, 1)]]


def _no_addr(xml: str) -> str:
    start = xml.index("<hp:cellAddr")
    return xml[:start] + xml[xml.index("/>", start) + 2 :]


@pytest.mark.parametrize("variant", ["missing", "same address", "spans overlap", "out of range", "not a number"])
def test_missing_cell_addresses_fall_back_to_document_order_keeping_text(variant):
    # 다's address (if any) disagrees with the document order, so trusting it would read differently
    second = {
        "missing": _no_addr(cell(p(run("다")), col=0, row=1)),
        "same address": cell(p(run("다")), col=0, row=0),
        "spans overlap": cell(p(run("다")), col=0, row=1),  # 가's rowspan covers (0, 1)
        "out of range": cell(p(run("다")), col=7, row=1),
        "not a number": cell(p(run("다")), col=0, row=1).replace('colAddr="0"', 'colAddr="x"'),
    }[variant]
    rows = [
        [cell(p(run("가")), col=0, row=0, rowspan=2), cell(p(run("나")), col=1, row=0)],
        [second, cell(p(run("라")), col=1, row=1)],
    ]
    table = only_table(tbl(rows, cols=2))
    # document order: the second row's cells go after the rowspan from above, in hp:tc order
    assert grid(table) == [
        [("가", 0, 2, 1), ("나", 1, 1, 1), ("", 2, 1, 1)],
        [("다", 1, 1, 1), ("라", 2, 1, 1)],
    ]


def test_table_fallback_pads_short_rows():
    rows = [
        [_no_addr(cell(p(run("가")), col=0, row=0)), cell(p(run("나")), col=1, row=0), cell(p(run("다")), col=2, row=0)],
        [cell(p(run("라")), col=0, row=1)],
    ]
    table = only_table(tbl(rows, cols=3))
    assert grid(table) == [
        [("가", 0, 1, 1), ("나", 1, 1, 1), ("다", 2, 1, 1)],
        [("라", 0, 1, 1), ("", 1, 1, 1), ("", 2, 1, 1)],
    ]


def test_cell_address_holes_are_padded_and_covered_rows_dropped():
    # (2, 0) has no cell
    rows = [
        [cell(p(run("가")), col=0, row=0), cell(p(run("나")), col=1, row=0, rowspan=2)],
        [cell(p(run("다")), col=0, row=1), cell(p(run("라")), col=2, row=1)],
    ]
    table = only_table(tbl(rows, cols=3))
    assert grid(table) == [
        [("가", 0, 1, 1), ("나", 1, 2, 1), ("", 2, 1, 1)],
        [("다", 0, 1, 1), ("라", 2, 1, 1)],
    ]
    # nothing starts in row 1, the rowspans from row 0 cover it: an empty <tr> would not read back
    rows = [
        [cell(p(run("가")), col=0, row=0, rowspan=3), cell(p(run("나")), col=1, row=0, rowspan=2)],
        [cell(p(run("다")), col=1, row=2)],
    ]
    table = only_table(tbl(rows, cols=2).replace('rowCnt="2"', 'rowCnt="3"'))
    assert grid(table) == [[("가", 0, 2, 1), ("나", 1, 1, 1)], [("다", 1, 1, 1)]]


def _with_caption(table: str, *paras: str) -> str:
    caption = (
        '<hp:caption side="BOTTOM" fullSz="0" width="8504" gap="850" lastWidth="8000">'
        f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP">{"".join(paras)}</hp:subList>'
        "</hp:caption>"
    )
    return table.replace('<hp:pos treatAsChar="1"/>', '<hp:pos treatAsChar="1"/>' + caption)


def test_cell_paragraphs_are_plain_and_caption_is_read():
    first = cell(p(run("개요 글"), para="1", page_break=True), p(run("둘째", "1")), col=0, row=0)
    table = tbl([[first, cell(p(run("칸 둘")), col=1, row=0)]], cols=2)
    imported, _ = _read(p(run("앞"), _with_caption(table, p(run("표 제목"), para="1")), run("뒤")))
    blocks = imported.doc.content
    assert kinds(blocks) == ["Para", "Table", "Para"]
    assert [text(blocks[0]), text(blocks[2])] == ["앞", "뒤"]
    # no heading or page-break sentinel in a cell; one paragraph is Plain, several a Para each (R3)
    content = blocks[1].head.content[0].content[0].content
    assert kinds(content) == ["Para", "Para"] and [text(b) for b in content] == ["개요 글", "둘째"]
    assert kinds(content[1].content) == ["Strong"]
    assert kinds(blocks[1].head.content[0].content[1].content) == ["Plain"]
    assert kinds(blocks[1].caption.content) == ["Plain"] and text(blocks[1].caption) == "표 제목"
    assert not blocks[1].foot.content
    # each paragraph's text once: the outer paragraph around its table, then caption and cells in XML order
    assert imported.source_text == ["앞", "뒤", "표 제목", "개요 글", "둘째", "칸 둘"]


def _with_aligned_para_prs(data: bytes) -> bytes:
    """``data`` with paraPr "7" RIGHT, "8" CENTER, "9" LEFT."""
    header = zipfile.ZipFile(io.BytesIO(data)).read("Contents/header.xml").decode()
    extra = "".join(
        f'<hh:paraPr id="{pid}" tabPrIDRef="0" condense="0"><hh:align horizontal="{align}" vertical="BASELINE"/>'
        '<hh:heading type="NONE" idRef="0" level="0"/></hh:paraPr>'
        for pid, align in (("7", "RIGHT"), ("8", "CENTER"), ("9", "LEFT"))
    )
    header = header.replace("</hh:paraProperties>", extra + "</hh:paraProperties>")
    return _replace(data, "Contents/header.xml", header.encode())


def test_column_alignment_comes_from_body_cells():
    def row(r: int, *paras: tuple[str, str]) -> list[str]:
        return [cell(p(run(t), para=para) if t else p(para=para), col=c, row=r) for c, (t, para) in enumerate(paras)]

    head = row(0, ("가", "8"), ("나", "8"), ("다", "8"), ("라", "8"), ("마", "8"))
    rows = [
        head,
        row(1, ("a", "9"), ("1", "7"), ("x", "7"), ("p", "0"), ("q", "8")),
        row(2, ("b", "9"), ("", "8"), ("y", "8"), ("r", "0"), ("s", "8")),
    ]
    data = _with_aligned_para_prs(hwpx_bytes(p(tbl(rows, cols=5))))
    table = read_hwpx(Source(data, "a.hwpx", Format.HWPX), Report("a.hwpx", Format.HWPX), "a_assets").doc.content[0]
    # head cells do not count, an empty cell does not either; mixed or justified columns stay default
    assert [spec[0] for spec in table.colspec] == ["AlignLeft", "AlignRight", "AlignDefault", "AlignDefault", "AlignCenter"]


_GOOD = tbl([[cell(p(run("가")), col=0, row=0), cell(p(run("나")), col=1, row=0)], _row(["다", "라"], 1)], cols=2)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('rowCnt="2"', 'rowCnt="1"'),
        ('colCnt="2"', 'colCnt="9"'),
        ('colCnt="2"', 'colCnt="x"'),
        ('colSpan="1"', 'colSpan="9999"'),
        ('rowSpan="1"', 'rowSpan="9999"'),
        ('rowSpan="1"', 'rowSpan="-3"'),
        ('colAddr="1"', 'colAddr="-1"'),
        ("</hp:tr><hp:tr>", "</hp:tr><hp:tr></hp:tr><hp:tr>"),
    ],
)
def test_malformed_tables_convert_without_losing_text(old, new):
    broken = _GOOD.replace(old, new)
    assert broken != _GOOD
    result = convert(Source(hwpx_bytes(p(run("앞")), p(broken), p(run("뒤"))), "a.hwpx", Format.HWPX), [Format.MD])
    md = result.outputs[0].data.decode()
    assert all(t in md for t in ("앞", "가", "나", "다", "라", "뒤")) and result.report.coverage == 1.0


def test_text_around_a_table_counts_as_present():
    table = tbl([[cell(p(run("칸")), col=0, row=0)]], cols=1)
    data = hwpx_bytes(p(run("앞 글"), _with_caption(table, p(run("표 제목"))), run("뒤 글")))
    result = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0


def test_table_without_cells_leaves_only_its_caption():
    empty = '<hp:run charPrIDRef="0"><hp:tbl id="1" rowCnt="0" colCnt="0"><hp:pos treatAsChar="1"/></hp:tbl></hp:run>'
    result = convert(Source(hwpx_bytes(p(run("앞")), p(empty), p(run("뒤"))), "a.hwpx", Format.HWPX), [Format.MD])
    assert result.outputs[0].data.decode() == "앞\n\n뒤\n" and result.report.coverage == 1.0
    doc, _ = read(p(run("앞"), _with_caption(empty, p(run("제목"))), run("뒤")))
    assert kinds(doc.content) == ["Para", "Plain", "Para"] and [text(b) for b in doc.content] == ["앞", "제목", "뒤"]


_LISTS = (pf.OrderedList, pf.BulletList)


def items(lst: pf.Block) -> list[str]:
    """Each item's text, leaving out its nested lists."""
    return [" ".join(text(b) for b in item.content if not isinstance(b, _LISTS)) for item in lst.content]


def test_number_paragraphs_become_ordered_list_with_nested_level():
    doc, _ = read(p(run("가"), para="3"), p(run("나"), para="4"), p(run("다"), para="3"))
    ol = doc.content[0]
    assert isinstance(ol, pf.OrderedList) and len(ol.content) == 2
    assert isinstance(ol.content[0].content[-1], pf.OrderedList)
    assert kinds(doc.content) == ["OrderedList"] and items(ol) == ["가", "다"]
    sub = ol.content[0].content[-1]
    assert items(sub) == ["나"] and (ol.start, sub.start) == (1, 1)
    assert (ol.style, ol.delimiter) == ("Decimal", "Period")
    # one paragraph per item: a tight list, which MD reads back as Plain items
    assert kinds(ol.content[0].content) == ["Plain", "OrderedList"] and kinds(ol.content[1].content) == ["Plain"]


def test_list_start_number_comes_from_numbering():
    doc, _ = read(p(run("셋"), para="6"), p(run("넷"), para="6"))
    assert kinds(doc.content) == ["OrderedList"] and doc.content[0].start == 3
    assert items(doc.content[0]) == ["셋", "넷"]


def test_bullet_paragraphs_in_cell_are_bullet_list_of_plain():
    first = cell(p(run("가"), para="5"), p(run("나"), para="5"), col=0, row=0)
    table = only_table(tbl([[first, cell(p(run("칸")), col=1, row=0)]], cols=2))
    content = table.head.content[0].content[0].content
    # the cell holds one list and no paragraph: R3 leaves its items alone
    assert kinds(content) == ["BulletList"] and items(content[0]) == ["가", "나"]
    assert [kinds(item.content) for item in content[0].content] == [["Plain"], ["Plain"]]


def test_bullet_list_in_body_and_cell_text_around_a_list_follows_r3():
    doc, _ = read(p(run("가"), para="5"), p(run("나"), para="5"))
    assert kinds(doc.content) == ["BulletList"] and items(doc.content[0]) == ["가", "나"]
    first = cell(p(run("앞")), p(run("가"), para="5"), p(run("뒤")), col=0, row=0)
    second = cell(p(run("나"), para="3"), p(run("끝")), col=1, row=0)
    row = only_table(tbl([[first, second]], cols=2)).head.content[0]
    # two paragraphs around the list are a Para each; a list and one paragraph keep the Plain
    assert kinds(row.content[0].content) == ["Para", "BulletList", "Para"]
    assert kinds(row.content[1].content) == ["OrderedList", "Plain"]
    assert kinds(row.content[0].content[1].content[0].content) == ["Plain"]


def test_list_breaks_on_kind_id_and_text_but_not_on_empty_paragraph():
    doc, _ = read(
        p(run("가"), para="3"),
        p(),
        p(run("나"), para="3"),
        p(run("다"), para="6"),
        p(run("라"), para="5"),
        p(run("본문")),
        p(run("마"), para="5"),
    )
    assert kinds(doc.content) == ["OrderedList", "OrderedList", "BulletList", "Para", "BulletList"]
    assert [items(b) if isinstance(b, _LISTS) else text(b) for b in doc.content] == [
        ["가", "나"],
        ["다"],
        ["라"],
        "본문",
        ["마"],
    ]
    assert [doc.content[0].start, doc.content[1].start] == [1, 3]


def test_list_level_jumps_keep_every_paragraph_in_order():
    def lst(*paras: str) -> pf.Block:
        data = _with_para_pr(hwpx_bytes(*paras), "7", "NUMBER", "1", "2")
        doc = read_hwpx(Source(data, "a.hwpx", Format.HWPX), Report("a.hwpx", Format.HWPX), "a").doc
        assert kinds(doc.content) == ["OrderedList"]
        return doc.content[0]

    # a list that starts one level down is a list of its own; a shallower item later is its sibling
    ol = lst(p(run("가"), para="4"), p(run("나"), para="4"), p(run("다"), para="3"))
    assert items(ol) == ["가", "나", "다"] and ol.start == 1
    # 0 → 2 nests one level only; the following level 1 item goes in the same nested list
    ol = lst(p(run("가"), para="3"), p(run("나"), para="7"), p(run("다"), para="4"), p(run("라"), para="3"))
    assert items(ol) == ["가", "라"]
    assert kinds(ol.content[0].content) == ["Plain", "OrderedList"]
    assert items(ol.content[0].content[1]) == ["나", "다"]
    # 1 → 2 → 0: the deeper list closes, the outer one goes on
    ol = lst(p(run("가"), para="4"), p(run("나"), para="7"), p(run("다"), para="3"))
    assert items(ol) == ["가", "다"] and items(ol.content[0].content[1]) == ["나"]


def test_list_paragraph_with_page_break_or_table_makes_loose_list():
    table = tbl([[cell(p(run("칸")), col=0, row=0)]], cols=1)
    doc, _ = read(p(run("가"), para="3"), p(run("나"), table, para="3"), p(run("다"), para="3"))
    assert kinds(doc.content) == ["OrderedList"] and len(doc.content[0].content) == 3
    # a tight list item cannot hold a table in MD: the whole list is loose, its text in Paras
    assert [kinds(item.content) for item in doc.content[0].content] == [["Para"], ["Para", "Table"], ["Para"]]
    doc, _ = read(p(run("가"), para="5"), p(run("나"), para="5", page_break=True))
    assert [kinds(item.content) for item in doc.content[0].content] == [["Para"], ["Para", "Para"]]
    assert text(doc.content[0].content[1].content[0]) == PAGEBREAK_SENTINEL


def test_hand_typed_number_after_native_list_still_merges_via_import_filters():
    data = hwpx_bytes(p(run("하나"), para="3"), p(run("둘"), para="3"), p(run("3. 셋")))
    result = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc
    assert kinds(back.content) == ["OrderedList"] and items(back.content[0]) == ["하나", "둘", "셋"]


def test_list_in_table_caption_converts():
    table = tbl([[cell(p(run("칸")), col=0, row=0)]], cols=1)
    data = hwpx_bytes(p(_with_caption(table, p(run("가"), para="5"), p(run("나"), para="3"))))
    assert kinds(only_table(_with_caption(table, p(run("가"), para="5"))).caption.content) == ["BulletList"]
    result = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc
    assert kinds(back.content[0].caption.content) == ["BulletList", "OrderedList"]


def _shape(blocks) -> list:
    """Block kinds, list starts and text, nested lists and table cells included."""
    out = []
    for b in blocks:
        if isinstance(b, pf.OrderedList):
            out.append(("OrderedList", b.start, [_shape(item.content) for item in b.content]))
        elif isinstance(b, pf.BulletList):
            out.append(("BulletList", [_shape(item.content) for item in b.content]))
        elif isinstance(b, pf.Table):
            rows = list(b.head.content) + [row for body in b.content for row in body.content]
            out.append(("Table", [[_shape(c.content) for c in row.content] for row in rows]))
        elif text(b) == PAGEBREAK_SENTINEL or (isinstance(b, pf.RawBlock) and "pagebreak" in b.text):
            out.append(("pagebreak",))  # the import filters turn the reader's mark into a raw block
        else:
            out.append((type(b).__name__, text(b)))
    return out


def test_native_lists_survive_md_round_trip():
    in_cell = cell(p(run("칸 가"), para="3"), p(run("칸 나"), para="4"), p(run("칸 글")), col=0, row=0)
    table = tbl([[in_cell, cell(p(run("칸 다"), para="5"), col=1, row=0)]], cols=2)
    loose = tbl([[cell(p(run("안")), col=0, row=0)]], cols=1)
    data = hwpx_bytes(
        p(run("하나"), para="3"),
        p(run("하위"), para="4"),
        p(run("둘"), para="3"),
        p(run("본문")),
        p(run("셋"), para="6"),
        p(run("글머리"), para="5"),
        p(run("본문 둘")),
        p(run("느슨"), para="5"),
        p(run("표 앞"), loose, para="5"),
        p(table),
    )
    report = Report("a.hwpx", Format.HWPX)
    source = read_hwpx(Source(data, "a.hwpx", Format.HWPX), report, "a_assets").doc
    result = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc
    assert _shape(back.content) == _shape(source.content)
    shape = [k for k, *_ in _shape(source.content)]
    assert shape == ["OrderedList", "Para", "OrderedList", "BulletList", "Para", "BulletList", "Table"]


def test_list_item_of_only_a_table_or_page_break_survives_md_round_trip():
    table = tbl([[cell(p(run("칸")), col=0, row=0)]], cols=1)
    data = hwpx_bytes(
        p(run("쪽 앞"), para="5", page_break=True),
        p(run("둘"), para="5"),
        p(run("본문")),
        p(run("가"), para="3"),
        p(table, para="3"),
        p(run("다"), para="3"),
        p(run("본문 둘")),
        p(run("라"), para="5"),
        p(para="5", page_break=True),
        p(run("마"), para="5"),
    )
    report = Report("a.hwpx", Format.HWPX)
    source = read_hwpx(Source(data, "a.hwpx", Format.HWPX), report, "a_assets").doc
    blocks = source.content
    assert kinds(blocks) == ["Para", "BulletList", "Para", "OrderedList", "Para", "BulletList"]
    # a page break on a list's first paragraph goes before the list; the list stays tight
    assert text(blocks[0]) == PAGEBREAK_SENTINEL and items(blocks[1]) == ["쪽 앞", "둘"]
    assert [kinds(i.content) for i in blocks[1].content] == [["Plain"], ["Plain"]]
    # an item that starts with anything but text makes pandoc write the list loose (R6a)
    assert [kinds(i.content) for i in blocks[3].content] == [["Para"], ["Table"], ["Para"]]
    assert [kinds(i.content) for i in blocks[5].content] == [["Para"], ["Para"], ["Para"]]
    result = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc
    assert _shape(back.content) == _shape(source.content)


# notes, equations, headers, memos, fields and tracked changes (Task 5) --------------------------

_SKIPPED = "머리말·꼬리말·메모는 가져오지 않습니다"  # the docx reader's IMPORT_HEADER_SKIPPED message
_SUB_OPEN = '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP">'


def _ctrl(inner: str) -> str:
    return f'<hp:run charPrIDRef="0"><hp:ctrl>{inner}</hp:ctrl></hp:run>'


def note(*paras: str, kind: str = "footNote") -> str:
    return _ctrl(
        f'<hp:{kind} number="1" suffixChar="41" instId="1">{_SUB_OPEN}{"".join(paras)}</hp:subList></hp:{kind}>'
    )


def equation(script: str, char: str = "0") -> str:
    return (
        f'<hp:run charPrIDRef="{char}"><hp:equation id="1" zOrder="0" numberingType="EQUATION" '
        'textWrap="TOP_AND_BOTTOM" version="Equation Version 60" baseLine="85" textColor="#000000" '
        'baseUnit="1000" lineMode="CHAR" font="HYhwpEQ"><hp:sz width="1000" widthRelTo="ABSOLUTE" height="1000" '
        'heightRelTo="ABSOLUTE" protect="0"/><hp:pos treatAsChar="1"/><hp:shapeComment>수식입니다.</hp:shapeComment>'
        f"<hp:script>{escape(script)}</hp:script></hp:equation></hp:run>"
    )


def page_part(kind: str, *paras: str) -> str:
    return _ctrl(f'<hp:{kind} id="1" applyPageType="BOTH">{_SUB_OPEN}{"".join(paras)}</hp:subList></hp:{kind}>')


def field_begin(fid: str, kind: str, params: dict[str, str] | None = None, inner: str = "") -> str:
    params = params or {}
    items = "".join(
        f"<hp:stringParam name={quoteattr(name)}>{escape(value)}</hp:stringParam>" for name, value in params.items()
    )
    return _ctrl(
        f'<hp:fieldBegin id="{fid}" type="{kind}" name="" editable="1" dirty="0" zorder="-1" fieldid="1">'
        f'<hp:parameters cnt="{len(params) + 1}" name=""><hp:integerParam name="Prop">0</hp:integerParam>{items}'
        f"</hp:parameters>{inner}</hp:fieldBegin>"
    )


def field_end(fid: str) -> str:
    return _ctrl(f'<hp:fieldEnd beginIDRef="{fid}" fieldid="1"/>')


def t(xml: str, char: str = "0") -> str:
    """A run whose ``hp:t`` holds ``xml`` as is (marks between the text)."""
    return f'<hp:run charPrIDRef="{char}"><hp:t>{xml}</hp:t></hp:run>'


def skipped(report: Report) -> list[str]:
    return [e.message for e in report.events if e.code == "IMPORT_HEADER_SKIPPED"]


def test_footnote_and_endnote_become_notes_in_body_and_cell():
    body = p(
        run("본문"),
        note(p(run("각주 하나"), para="1", page_break=True), p(run("각주 둘"))),
        run(" 뒤"),
    )
    table = tbl([[cell(p(run("칸"), note(p(run("칸 각주")))), col=0, row=0)]], cols=1)
    end = p(run("미주 앞"), note(p(run("미주 글")), kind="endNote"))
    listed = p(run("목록 주"), note(p(run("가"), para="3"), p(run("나"), para="3")))
    imported, _ = _read(body + p(table) + end + listed)
    blocks = imported.doc.content
    assert kinds(blocks) == ["Para", "Table", "Para", "Para"]
    assert kinds(blocks[0].content) == ["Str", "Note", "Space", "Str"]
    # note paragraphs are Para (R1): no heading and no page-break mark inside a note
    footnote = blocks[0].content[1]
    assert kinds(footnote.content) == ["Para", "Para"]
    assert [text(b) for b in footnote.content] == ["각주 하나", "각주 둘"]
    in_cell = blocks[1].head.content[0].content[0].content  # a one-row table is all head
    assert kinds(in_cell) == ["Plain"] and kinds(in_cell[0].content) == ["Str", "Note"]
    assert kinds(in_cell[0].content[1].content) == ["Para"] and text(in_cell[0].content[1]) == "칸 각주"
    assert kinds(blocks[2].content) == ["Str", "Space", "Str", "Note"] and text(blocks[2].content[3]) == "미주 글"
    assert kinds(blocks[3].content[-1].content) == ["OrderedList"]
    # each note paragraph once, on its own, not inside its referencing paragraph's text
    assert imported.source_text == [
        "본문 뒤", "각주 하나", "각주 둘", "칸", "칸 각주", "미주 앞", "미주 글", "목록 주", "가", "나",
    ]


def test_empty_footnote_is_dropped():
    doc, _ = read(p(run("글"), note(p())))
    assert kinds(doc.content[0].content) == ["Str"]


def test_equation_alone_is_code_block_inline_is_code_with_warn():
    imported, report = _read(
        p(equation("a over b")),
        p(run("값 "), equation("x ^{2}", char="1"), run(" 이다")),
    )
    blocks = imported.doc.content
    assert kinds(blocks) == ["CodeBlock", "Para"] and blocks[0].text == "a over b"
    assert kinds(blocks[1].content) == ["Str", "Space", "Code", "Space", "Str"]
    assert blocks[1].content[2].text == "x ^{2}"
    warns = [e for e in report.events if e.code == "HWPX_EQUATION_PRESERVED"]
    assert [(e.level.value, e.message) for e in warns] == [("warn", "한글 수식을 코드로 남깁니다")] * 2
    assert imported.source_text == ["값 ", " 이다"]


def test_equation_between_text_keeps_full_coverage():
    data = hwpx_bytes(p(run("값은 "), equation("x over y"), run(" 이다")), p(equation("z")))
    result = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0
    assert "`x over y`" in result.outputs[0].data.decode()


def test_header_footer_skipped_with_one_info_and_not_in_source_text():
    imported, report = _read(
        p(page_part("header", p(run("머리 글"))), page_part("footer", p(run("꼬리 글"))), run("본문")),
        p(page_part("header", p(run("둘째 머리"))), run("둘째")),
    )
    assert [text(b) for b in imported.doc.content] == ["본문", "둘째"]
    assert imported.source_text == ["본문", "둘째"]
    assert skipped(report) == [_SKIPPED]
    _, plain = _read(p(run("본문")))
    assert skipped(plain) == []


def test_hyperlink_field_becomes_link():
    command = {"Command": "https\\://example.com/a\\;b?x=1;1;0;0;", "Path": "https://example.com/a;b?x=1"}
    doc, _ = read(
        p(run("앞 "), field_begin("5", "HYPERLINK", command), run("링크 "), run("굵게", "1"), field_end("5"), run(" 뒤")),
        p(field_begin("6", "HYPERLINK", command), run("끝에 공백 "), field_end("6"), run("뒤")),
    )
    first = doc.content[0].content
    assert kinds(first) == ["Str", "Space", "Link", "Space", "Str"]
    assert first[2].url == "https://example.com/a;b?x=1"
    assert kinds(first[2].content) == ["Str", "Space", "Strong"] and text(first[2]) == "링크 굵게"
    second = doc.content[1].content
    assert kinds(second) == ["Link", "Space", "Str"] and text(second[0]) == "끝에 공백"


def test_unbalanced_and_unknown_fields_keep_their_text():
    link = {"Command": "https\\://example.com;1;0;0;"}
    doc, _ = read(
        p(run("가 "), field_begin("1", "HYPERLINK", link), run("열린 채")),  # no fieldEnd
        p(run("나 "), field_end("2"), run("닫기만")),  # no fieldBegin
        p(field_begin("3", "DATE"), run("날짜 글"), field_end("3")),
        p(field_begin("4", "HYPERLINK"), run("주소 없음"), field_end("4")),
        p(run("빈 "), field_begin("5", "HYPERLINK", link), field_end("5"), run("링크")),
    )
    assert [text(b) for b in doc.content] == ["가 열린 채", "나 닫기만", "날짜 글", "주소 없음", "빈 링크"]
    assert not [e for b in doc.content for e in b.content if isinstance(e, pf.Link)]


def test_empty_click_here_keeps_guide_text():
    guide = {"Direction": "이름을 쓰십시오"}
    by_command = {"Command": "Clickhere:set:66:Direction:wstring:8:날짜를 고르세요 HelpState:wstring:0: "}
    imported, _ = _read(
        p(run("이름: "), field_begin("7", "CLICK_HERE", guide), field_end("7"), run(" 끝")),
        p(field_begin("8", "CLICK_HERE", guide), run("홍길동"), field_end("8")),
        p(field_begin("9", "CLICK_HERE", by_command), field_end("9")),
    )
    assert [text(b) for b in imported.doc.content] == ["이름: 이름을 쓰십시오 끝", "홍길동", "날짜를 고르세요"]
    data = hwpx_bytes(p(run("이름:"), field_begin("7", "CLICK_HERE", guide), field_end("7"), run("끝")))
    assert convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD]).report.coverage == 1.0


def test_memo_dropped_with_info():
    memo = field_begin("9", "MEMO", {"Author": "검토자"}, inner=f"{_SUB_OPEN}{p(run('메모 글'))}</hp:subList>")
    group = (
        '<hp:memogroup><hp:memo id="1" memoShapeIDRef="0"><hp:paraList>'
        f"{p(run('메모 둘'))}</hp:paraList></hp:memo></hp:memogroup>"
    )
    imported, report = _read(p(run("앞 "), memo, run("표시 글"), field_end("9"), run(" 뒤")) + group)
    # the memo goes; the text it was attached to stays
    assert [text(b) for b in imported.doc.content] == ["앞 표시 글 뒤"]
    assert imported.source_text == ["앞 표시 글 뒤"]
    assert skipped(report) == [_SKIPPED]


def test_tracked_deletion_is_left_out_of_body_and_source_text():
    imported, report = _read(
        p(
            t('남김 <hp:deleteBegin Id="1" TcId="1" paraend="0"/>지운<hp:tab/>글'),
            t("굵게 지움", "1"),
            t('까지<hp:deleteEnd Id="1" TcId="1" paraend="0"/>끝'),
            t('<hp:insertBegin Id="2" TcId="2" paraend="0"/> 넣은 글<hp:insertEnd Id="2" TcId="2" paraend="0"/>'),
        ),
        p(t('가<hp:deleteBegin Id="3" TcId="3" paraend="1"/>나')),  # a begin with no end
        p(t('다<hp:deleteEnd Id="4" TcId="4" paraend="0"/>라')),  # an end with no begin
    )
    assert [text(b) for b in imported.doc.content] == ["남김 끝 넣은 글", "가나", "다라"]
    assert kinds(imported.doc.content[0].content) == ["Str", "Space", "Str", "Space", "Str", "Space", "Str"]
    assert imported.source_text == ["남김 끝 넣은 글", "가나", "다라"]
    assert skipped(report) == [_SKIPPED]


def test_tracked_deletion_across_paragraphs_is_left_out():
    begin, end = '<hp:deleteBegin Id="5" TcId="5" paraend="1"/>', '<hp:deleteEnd Id="5" TcId="5" paraend="0"/>'
    in_cell = cell(p(t(f"칸 앞{begin}칸 지움")), p(t(f"칸 지움{end}칸 뒤")), col=0, row=0)
    body = (
        p(t(f"첫 글 {begin}지운 끝")),
        p(run("통째로 지운 문단")),
        p(t(f"이것도 지움{end} 남은 글")),
        p(tbl([[in_cell]], cols=1)),
    )
    imported, _ = _read("".join(body))
    blocks = imported.doc.content
    # a paragraph left without text is dropped; a cell's paragraphs pair their own marks
    assert [text(b) for b in blocks[:2]] == ["첫 글", "남은 글"]
    assert [text(b) for b in blocks[2].head.content[0].content[0].content] == ["칸 앞", "칸 뒤"]
    assert imported.source_text == ["첫 글 ", " 남은 글", "칸 앞", "칸 뒤"]
    result = convert(Source(hwpx_bytes("".join(body)), "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0


# pictures, text boxes and shapes (Task 6) -------------------------------------------------------

_AUTO = "그림입니다.\n원본 그림의 이름: x.png\n원본 그림의 크기: 가로 10pixel, 세로 10pixel"
_IMAGE_TEXT = "표 칸 안의 작은 그림은 글자였는지 알 수 없어 그림으로 가져옵니다"  # the docx reader's message


def to_md(*sections: str, name: str = "a.hwpx", **kw):
    result = convert(Source(hwpx_bytes(*sections, **kw), name, Format.HWPX), [Format.MD])
    return result.outputs[0].data.decode(), result


def bare(run_xml: str) -> str:
    """The object a builder run holds, without its run."""
    return run_xml.removeprefix('<hp:run charPrIDRef="0">').removesuffix("</hp:run>")


def container(*objects: str) -> str:
    return (
        '<hp:run charPrIDRef="0"><hp:container id="1" zOrder="0" numberingType="PICTURE">'
        f"{''.join(objects)}</hp:container></hp:run>"
    )


def events(report: Report, code: str) -> list:
    return [e for e in report.events if e.code == code]


def test_picture_goes_to_assets_with_auto_comment_replaced():
    md, out = to_md(p(pic("image1", comment=_AUTO)), bin_data={"image1.png": tiny_png()})
    assert "![그림](a_assets/image1.png)" in md and "x.png" not in md
    assert out.outputs[0].assets == {"a_assets/image1.png": tiny_png()}
    # Hancom also writes the drawing program's name on a line of its own, with a space before ':'
    program = _AUTO + "\n프로그램 이름 : 그리기 도구"
    md, _ = to_md(p(pic("image1", comment=program)), bin_data={"image1.png": tiny_png()})
    assert "![그림](a_assets/image1.png)" in md and "그리기" not in md


def test_human_comment_is_alt_text():
    imported, _ = _read(
        p(pic("image1", comment="회사\n로고")),
        p(pic("image1")),
        p(pic("image1", comment="그림입니다.\n사람이 쓴 설명")),
        bin_data={"image1.png": tiny_png()},
    )
    images = [b.content[0] for b in imported.doc.content]
    assert [text(i) for i in images] == ["회사 로고", "그림", "그림입니다. 사람이 쓴 설명"]
    assert {i.url for i in images} == {"a_assets/image1.png"} and imported.media == {"image1.png": tiny_png()}
    assert all(not i.attributes for i in images)


def test_small_picture_in_cell_without_comment_warns_image_text():
    row = [
        cell(p(pic("image1", height=3600)), col=0, row=0),
        cell(p(pic("image1", comment="확인 표시", height=3600)), col=1, row=0),
        cell(p(pic("image1", comment=_AUTO, height=3601)), col=2, row=0),
    ]
    second = [cell(p(run("글")), col=0, row=0), cell(p(pic("image1", comment=_AUTO, height=1000)), col=1, row=0)]
    imported, report = _read(
        p(pic("image1", height=100)),  # outside a table: no warn
        p(tbl([row], cols=3)),
        p(tbl([second], cols=2)),
        bin_data={"image1.png": tiny_png()},
    )
    warns = events(report, "IMPORT_IMAGE_TEXT")
    assert [(e.level.value, e.message) for e in warns] == [("warn", _IMAGE_TEXT)] * 2
    # the docx reader's place keys: tables in document order, row and column from 1
    assert [e.where for e in warns] == [{"table": 1, "row": 1, "col": 1}, {"table": 2, "row": 1, "col": 2}]
    in_cell = imported.doc.content[1].head.content[0].content[0].content
    assert kinds(in_cell) == ["Plain"] and kinds(in_cell[0].content) == ["Image"]


def test_bmp_picture_becomes_png():
    imported, report = _read(p(pic("image1")), bin_data={"image1.bmp": tiny_bmp()})
    assert list(imported.media) == ["image1.png"] and imported.media["image1.png"].startswith(b"\x89PNG")
    assert imported.doc.content[0].content[0].url == "a_assets/image1.png"
    assert not events(report, "IMAGE_CONVERT_FAILED")


def test_unreadable_or_missing_picture_data_keeps_going():
    imported, report = _read(
        p(run("앞 "), pic("image1"), run(" 뒤")),  # bytes Pillow cannot read: kept as they are
        p(run("없는 "), pic("image9", comment="조직도")),  # no such item: the human alt text stays
        p(pic("image9", comment=_AUTO)),  # nothing to keep
        bin_data={"image1.bmp": b"not a picture"},
    )
    assert imported.media == {"image1.bmp": b"not a picture"}
    assert [e.where for e in events(report, "IMAGE_CONVERT_FAILED")] == [{"name": "image1.bmp"}]
    assert kinds(imported.doc.content) == ["Para", "Para"]
    assert kinds(imported.doc.content[0].content) == ["Str", "Space", "Image", "Space", "Str"]
    assert text(imported.doc.content[1]) == "없는 조직도"
    skips = events(report, "IMPORT_OBJECT_SKIPPED")
    assert [(e.level.value, e.message, e.where) for e in skips] == [
        ("warn", "그림 파일을 찾을 수 없어 그림을 건너뜁니다", {"name": "image9"})
    ] * 2


def test_same_picture_twice_is_one_file():
    imported, _ = _read(
        p(pic("image1"), pic("image1")),
        p(pic("image2")),
        bin_data={"image1.png": tiny_png(), "image2.png": tiny_png()},
    )
    assert imported.media == {"image1.png": tiny_png(), "image2.png": tiny_png()}
    assert [i.url for i in imported.doc.content[0].content if isinstance(i, pf.Image)] == ["a_assets/image1.png"] * 2


def test_textbox_text_is_paragraphs_in_place_and_counted():
    imported, _ = _read(p(run("앞글"), textbox(p(run("상자 안")), p(run("둘째 줄"), para="1")), run("뒷글")))
    blocks = imported.doc.content
    # a text box's paragraphs follow body rules, but never become headings (as in a note)
    assert kinds(blocks) == ["Para", "Para", "Para", "Para"]
    assert [text(b) for b in blocks] == ["앞글", "상자 안", "둘째 줄", "뒷글"]
    # each text box paragraph once, on its own
    assert imported.source_text == ["앞글", "뒷글", "상자 안", "둘째 줄"]
    md, result = to_md(p(run("앞글"), textbox(p(run("상자 안"))), run("뒷글")))
    assert md.split() == ["앞글", "상자", "안", "뒷글"] and result.report.coverage == 1.0


def test_container_objects_are_read_in_order():
    inner = container(bare(textbox(p(run("안쪽 상자")))))
    group = container(bare(pic("image1")), bare(textbox(p(run("상자 하나")))), bare(inner))
    imported, _ = _read(p(run("앞"), group, run("뒤")), bin_data={"image1.png": tiny_png()})
    blocks = imported.doc.content
    assert [text(b) for b in blocks] == ["앞", "그림", "상자 하나", "안쪽 상자", "뒤"]
    assert kinds(blocks[1].content) == ["Image"]
    assert imported.source_text == ["앞", "뒤", "상자 하나", "안쪽 상자"]


def test_every_drawing_with_text_gives_its_text():
    def shape(tag: str) -> str:
        return textbox(p(run(f"{tag} 글"))).replace("hp:rect", f"hp:{tag}")

    tags = ["ellipse", "polygon", "arc", "curve", "connectLine", "unknownShape"]
    imported, report = _read(p(*(shape(tag) for tag in tags)))
    assert [text(b) for b in imported.doc.content] == [f"{tag} 글" for tag in tags]
    assert not events(report, "IMPORT_OBJECT_SKIPPED")


def test_textbox_in_cell_and_note():
    alone = cell(p(textbox(p(run("상자만")))), col=0, row=0)
    mixed = cell(p(run("칸 앞"), textbox(p(run("칸 상자"))), run("칸 뒤")), col=1, row=0)
    imported, _ = _read(p(tbl([[alone, mixed]], cols=2)), p(run("주"), note(p(textbox(p(run("주 상자")))))))
    cells = imported.doc.content[0].head.content[0].content
    assert kinds(cells[0].content) == ["Plain"] and text(cells[0]) == "상자만"
    # with the box's paragraph the cell has three: each is a Para (R3)
    assert kinds(cells[1].content) == ["Para", "Para", "Para"]
    assert [text(b) for b in cells[1].content] == ["칸 앞", "칸 상자", "칸 뒤"]
    footnote = imported.doc.content[1].content[1]
    assert kinds(footnote.content) == ["Para"] and text(footnote) == "주 상자"


def test_textboxes_survive_md_round_trip():
    alone = cell(p(textbox(p(run("상자만")))), col=0, row=0)
    mixed = cell(p(run("칸 앞"), textbox(p(run("칸 상자"))), run("칸 뒤")), col=1, row=0)
    data = hwpx_bytes(
        p(run("앞글"), textbox(p(run("상자 가"), para="3"), p(run("상자 나"), para="3")), run("뒷글")),
        p(tbl([[alone, mixed]], cols=2)),
    )
    source = read_hwpx(Source(data, "a.hwpx", Format.HWPX), Report("a.hwpx", Format.HWPX), "a_assets").doc
    result = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc
    assert _shape(back.content) == _shape(source.content)
    assert [k for k, *_ in _shape(source.content)] == ["Para", "OrderedList", "Para", "Table"]


def test_picture_caption_is_kept_after_the_picture():
    caption = (
        f'<hp:caption side="BOTTOM" fullSz="0" width="7200" gap="850" lastWidth="7200">{_SUB_OPEN}'
        f"{p(run('그림 설명'))}</hp:subList></hp:caption>"
    )
    captioned = pic("image1").replace("<hp:outMargin", caption + "<hp:outMargin")
    imported, _ = _read(p(run("앞 "), captioned, run(" 뒤")), bin_data={"image1.png": tiny_png()})
    assert [text(b) for b in imported.doc.content] == ["앞 그림", "그림 설명", "뒤"]
    assert imported.source_text == ["앞 ", " 뒤", "그림 설명"]


def _object(tag: str, comment: str | None) -> str:
    shape_comment = "" if comment is None else f"<hp:shapeComment>{escape(comment)}</hp:shapeComment>"
    return (
        f'<hp:run charPrIDRef="0"><hp:{tag} id="1" zOrder="0"><hp:sz width="1" height="1"/>'
        f"{shape_comment}</hp:{tag}></hp:run>"
    )


def test_chart_is_skipped_with_warn():
    imported, report = _read(
        p(run("앞"), _object("chart", None), run("뒤")),
        p(_object("ole", "매출 추이")),  # a comment that is not Hancom's picture template stays
        p(_object("textart", "")),
    )
    # nothing is put where an object without a description was: the text around it closes up
    assert kinds(imported.doc.content) == ["Para", "Para"]
    assert [text(b) for b in imported.doc.content] == ["앞뒤", "매출 추이"]
    assert imported.source_text == ["앞", "뒤"]
    skips = events(report, "IMPORT_OBJECT_SKIPPED")
    assert [(e.level.value, e.message) for e in skips] == [("warn", "글로 옮길 수 없는 개체를 건너뜁니다")] * 3


def test_map_symbols_counts_mapped_and_unknown():
    from mdcast.readers.symbols import SYMBOLS, map_symbols

    assert SYMBOLS["\uf0a7"] == "\u25aa" and SYMBOLS["\uf0b7"] == "\u2022"
    assert SYMBOLS["\uf06c"] == "\u25cf" and SYMBOLS["\uf0a8"] == "\u25c6"
    assert map_symbols("\uf0a7 가 \uf0b7\ue000\uf8ff") == ("\u25aa 가 \u2022\ue000\uf8ff", 2, 2)
    assert map_symbols("보통 글 \ud7a3") == ("보통 글 \ud7a3", 0, 0)
    assert map_symbols("") == ("", 0, 0)


def test_symbol_font_text_is_mapped_in_body_notes_and_source_text():
    tab = '<hp:run charPrIDRef="0"><hp:t>\uf0b7<hp:tab/>\uf06c 나\ue000</hp:t></hp:run>'
    in_note = p(run("\uf0a8 주"))
    note = (
        '<hp:run charPrIDRef="0"><hp:ctrl><hp:footNote number="1" suffixChar="41" instId="1">'
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP">'
        f"{in_note}</hp:subList></hp:footNote></hp:ctrl></hp:run>"
    )
    imported, report = _read(p(run("\uf0a7 가")), p(tab, note))
    body = [text(b) for b in imported.doc.content]
    assert body == ["\u25aa 가", "\u2022 \u25cf 나\ue000\u25c6 주"]  # the note text comes last
    notes = []
    imported.doc.walk(lambda e, _d: notes.append(e) if isinstance(e, pf.Note) else None)
    assert [text(n) for n in notes] == ["\u25c6 주"]
    assert imported.source_text == ["\u25aa 가", "\u2022 \u25cf 나\ue000", "\u25c6 주"]  # the tab mark is a space
    infos = events(report, "IMPORT_SYMBOL_MAPPED")
    assert [(e.level.value, e.message) for e in infos] == [
        ("info", "기호 글꼴 글자 4개를 보이는 기호로 바꿨습니다 (바꾸지 못한 글자 1개는 그대로 둡니다)")
    ]


def test_symbol_report_only_when_symbol_font_text_is_there():
    _, report = read(p(run("보통 글")))
    assert events(report, "IMPORT_SYMBOL_MAPPED") == []
    _, report = read(p(run("\ue000 글")))
    assert [e.message for e in events(report, "IMPORT_SYMBOL_MAPPED")] == [
        "기호 글꼴 글자 1개는 보이는 기호로 바꾸지 못해 그대로 둡니다"
    ]


def test_symbol_font_text_in_a_text_box_is_mapped():
    imported, report = _read(p(run("앞"), textbox(p(run("\uf0d8 상자"))), run("\uf0fc 뒤")))
    assert [text(b) for b in imported.doc.content] == ["앞", "\u27a2 상자", "\u2713 뒤"]
    assert imported.source_text == ["앞", "\u2713 뒤", "\u27a2 상자"]  # nested paragraphs after
    assert [e.message for e in events(report, "IMPORT_SYMBOL_MAPPED")] == [
        "기호 글꼴 글자 2개를 보이는 기호로 바꿨습니다"
    ]
