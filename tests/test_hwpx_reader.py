from __future__ import annotations

import io
import zipfile

import panflute as pf
import pytest
from hwpx_builder import cell, hwpx_bytes, p, run, tbl
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
    assert pkg.styles.chars["1"].bold and pkg.styles.paras["3"] == ParaStyle("NUMBER", 0, "1")
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
        "0": ParaStyle(),
        "1": ParaStyle("OUTLINE", 0),
        "2": ParaStyle("OUTLINE", 1),
        "3": ParaStyle("NUMBER", 0, "1"),
        "4": ParaStyle("NUMBER", 1, "1"),
        "5": ParaStyle("BULLET", 0, "1"),
        "6": ParaStyle("NUMBER", 0, "2"),
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
