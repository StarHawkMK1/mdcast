import pytest
from helpers import HWPX_NS as NS
from helpers import hwpx_render, hwpx_settings, hwpx_texts

from mdcast.ast import md_to_doc
from mdcast.hwpx.look import Border, TableLook
from mdcast.hwpx.table import build_grid, column_widths, slot_fill, slot_sides, slot_valign
from mdcast.hwpx.units import hwpunit

MERGED = (
    "+------+------------+--------------------------+\n"
    "| 구분 | 항목       | 성능 기준                |\n"
    "|      |            +--------+--------+--------+\n"
    "|      |            | 최소   | 권장   | 비고   |\n"
    "+======+============+========+========+========+\n"
    "| 1    | 응답 시간  | 3초    | 1초    | 평균   |\n"
    "+------+------------+--------+--------+--------+\n"
)


def table(md):
    return md_to_doc(md).content[0]


def test_merged_header_grid_skips_covered_places():
    grid = build_grid(table(MERGED))
    assert grid.cols == 5
    assert [[(s.row, s.col, s.rowspan, s.colspan, s.part) for s in row] for row in grid.rows] == [
        [(0, 0, 2, 1, "head"), (0, 1, 2, 1, "head"), (0, 2, 1, 3, "head")],
        [(1, 2, 1, 1, "head"), (1, 3, 1, 1, "head"), (1, 4, 1, 1, "head")],
        [(2, 0, 1, 1, "body"), (2, 1, 1, 1, "body"), (2, 2, 1, 1, "body"), (2, 3, 1, 1, "body"), (2, 4, 1, 1, "body")],
    ]


def test_short_rows_get_fillers_and_spans_are_clipped():
    t = table("| a | b | c |\n|---|---|---|\n| 1 | 2 | 3 |\n")
    row = t.content[0].content[0]
    row.content = list(row.content)[:1]
    row.content[0].colspan = 9
    grid = build_grid(t)
    assert [(s.col, s.colspan, s.cell is None) for s in grid.rows[1]] == [(0, 3, False)]
    t2 = table("| a | b |\n|---|---|\n| 1 | 2 |\n")
    row2 = t2.content[0].content[0]
    row2.content = list(row2.content)[:1]
    assert [(s.col, s.cell is None) for s in build_grid(t2).rows[1]] == [(0, False), (1, True)]


def test_full_widths_stretch_grid_table_fractions_to_the_available_width():
    t = table(MERGED)
    widths = column_widths(t, build_grid(t), TableLook(), 170.0, 10.0)
    assert sum(widths) == pytest.approx(170.0)
    assert widths[1] / widths[0] == pytest.approx(0.18055555 / 0.09722222, rel=1e-3)


def test_auto_widths_follow_text_and_minimum():
    t = table("| 짧 | 조금 더 긴 칸 글자 |\n|---|---|\n| 1 | 2 |\n")
    widths = column_widths(t, build_grid(t), TableLook(width="auto"), 170.0, 10.0)
    assert widths[0] == pytest.approx(10.0)
    assert 20.0 < widths[1] < 60.0


def test_auto_widths_never_exceed_available_even_with_minimums():
    head = "|" + "|".join(f" c{i} " for i in range(12)) + "|\n|" + "---|" * 12 + "\n"
    t = table(head + "|" + " 1 |" * 12 + "\n")
    assert sum(column_widths(t, build_grid(t), TableLook(width="auto"), 100.0, 10.0)) == pytest.approx(100.0)


def test_outer_sides_and_fill_priority():
    look = TableLook(header_background="#H", first_column_background="#F", zebra="#Z")
    grid = build_grid(table("| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"))
    (h0, h1), (b0, b1), (c0, c1) = grid.rows
    assert slot_sides(h0, grid, look) == (look.border_outer, look.border, look.border_outer, look.border)
    assert slot_sides(c1, grid, look) == (look.border, look.border_outer, look.border, look.border_outer)
    assert [slot_fill(s, look) for s in (h0, h1, b0, b1, c0, c1)] == ["#H", "#H", "#F", None, "#F", "#Z"]
    assert slot_valign(h0, TableLook(header_valign="bottom")) == "BOTTOM"


def tbl(paragraphs):
    return next(t for p in paragraphs for t in p.iter(f"{{{NS['hp']}}}tbl"))


def test_table_xml_matches_the_sample_shape():
    _, _, paragraphs, notices = hwpx_render(MERGED)
    t = tbl(paragraphs)
    assert (t.get("rowCnt"), t.get("colCnt"), t.get("repeatHeader"), t.get("pageBreak")) == ("3", "5", "1", "CELL")
    assert [c.tag.split("}")[1] for c in t][:4] == ["sz", "pos", "outMargin", "inMargin"]
    pos = t.find("hp:pos", NS)
    assert (pos.get("treatAsChar"), pos.get("horzRelTo")) == ("0", "PARA")  # Hangul splits only floating tables
    assert t.find("hp:outMargin", NS).attrib == {"left": "0", "right": "0", "top": "283", "bottom": "283"}
    assert int(t.find("hp:sz", NS).get("width")) == hwpunit(170.0)
    cells = t.findall("hp:tr/hp:tc", NS)
    assert len(cells) == 11  # 15 places in the 3x5 grid, 4 covered by the two spans
    assert [c.get("header") for c in cells[:6]] == ["1"] * 6
    first = cells[0]
    assert first.find("hp:cellSpan", NS).attrib == {"colSpan": "1", "rowSpan": "2"}
    assert first.find("hp:subList", NS).get("vertAlign") == "CENTER"
    assert first.find("hp:cellMargin", NS).get("left") == str(hwpunit(1.5))
    body = cells[6:]  # the five body cells, one per column
    assert sum(int(c.find("hp:cellSz", NS).get("width")) for c in body) == int(t.find("hp:sz", NS).get("width"))
    assert notices.items == []


def test_table_paragraph_ends_with_an_empty_text():
    _, _, paragraphs, _ = hwpx_render("| a |\n|---|\n| 1 |\n")
    run = tbl(paragraphs).getparent()
    assert [c.tag.split("}")[1] for c in run] == ["tbl", "t"]


def test_header_cells_get_the_header_background():
    header, _, paragraphs, _ = hwpx_render("| a | b |\n|---|---|\n| 1 | 2 |\n",
                                           hwpx_settings(tables={None: TableLook(header_background="#F2F2F2")}))
    cells = tbl(paragraphs).findall("hp:tr/hp:tc", NS)
    faces = [header.item("borderFills", c.get("borderFillIDRef")).find(".//hc:winBrush", NS) for c in cells]
    assert [f is not None and f.get("faceColor") for f in faces] == ["#F2F2F2", "#F2F2F2", False, False]


def test_variant_attribute_picks_the_variant_look():
    doc = md_to_doc("| a |\n|---|\n| 1 |\n")
    doc.content[0].attributes["mdcast-variant"] = "얇게"
    looks = {None: TableLook(), "얇게": TableLook(border=Border(0.34), border_outer=Border(0.34))}
    header, _, paragraphs, _ = hwpx_render("", hwpx_settings(tables=looks), doc=doc)
    fill = header.item("borderFills", tbl(paragraphs).find("hp:tr/hp:tc", NS).get("borderFillIDRef"))
    assert {e.get("width") for e in fill if e.tag.endswith("Border")} == {"0.12 mm"}


def test_caption_is_a_hangul_caption_without_autonum():
    _, shapes, paragraphs, _ = hwpx_render("Table: <표 1> 요약\n\n| a |\n|---|\n| 1 |\n")
    caption = tbl(paragraphs).find("hp:caption", NS)
    assert caption.get("side") == "TOP"
    p = caption.find("hp:subList/hp:p", NS)
    assert p.get("styleIDRef") == shapes["caption"].style
    assert p.find(".//hp:autoNum", NS) is None and "요약" in "".join(p.itertext())


@pytest.mark.parametrize("above", [True, False])
def test_caption_wider_than_a_narrow_table_is_a_paragraph_of_its_own(above):
    # Hangul draws a table's caption only as wide as the table (appendix B-8)
    md = "Table: <표 1> 좁은 표에 붙은 긴 캡션\n\n| a |\n|---|\n| 1 |\n"
    settings = hwpx_settings(tables={None: TableLook(width="auto")}, table_caption_above=above)
    _, shapes, paragraphs, _ = hwpx_render(md, settings)
    assert tbl(paragraphs).find("hp:caption", NS) is None
    caption = hwpx_texts(paragraphs).index("<표 1> 좁은 표에 붙은 긴 캡션")
    anchor = next(i for i, p in enumerate(paragraphs) if p.find(".//hp:tbl", NS) is not None)
    assert caption == (anchor - 1 if above else anchor + 1)
    assert paragraphs[caption].get("styleIDRef") == shapes["caption"].style


def test_cell_paragraphs_use_the_table_size_and_cell_alignment():
    header, _, paragraphs, _ = hwpx_render("| a |\n|--:|\n| 1 |\n", hwpx_settings(tables={None: TableLook(font_size=9.0)}))
    p = tbl(paragraphs).find("hp:tr/hp:tc/hp:subList/hp:p", NS)
    char = header.item("charProperties", p.find("hp:run", NS).get("charPrIDRef"))
    para = header.item("paraProperties", p.get("paraPrIDRef"))
    assert char.get("height") == "900"
    assert para.find(".//hh:align", NS).get("horizontal") == "RIGHT"


def test_nested_table_uses_the_cell_inner_width():
    doc = md_to_doc("| 바깥 |\n|---|\n| x |\n")
    inner = md_to_doc("| 안 |\n|---|\n| y |\n").content[0]
    doc.content[0].content[0].content[0].content[0].content = [inner]
    _, _, paragraphs, _ = hwpx_render("", doc=doc)
    nested = tbl(paragraphs).find(".//hp:tc//hp:tbl", NS)
    assert abs(int(nested.find("hp:sz", NS).get("width")) - (hwpunit(170.0) - 2 * hwpunit(1.5))) <= 1


def test_table_in_list_item_is_narrower():
    _, _, paragraphs, _ = hwpx_render("- 항목\n\n    | a |\n    |---|\n    | 1 |\n")
    assert int(tbl(paragraphs).find("hp:sz", NS).get("width")) < hwpunit(170.0)


def test_empty_table_writes_only_its_caption():
    doc = md_to_doc("Table: 빈 표\n\n| a |\n|---|\n| 1 |\n")
    t = doc.content[0]
    t.head.content = []
    t.content[0].content = []
    _, _, paragraphs, _ = hwpx_render("", doc=doc)
    assert hwpx_texts(paragraphs) == ["빈 표"]


def test_floating_table_keeps_the_next_paragraphs_space_before():
    # Hangul lays the next paragraph right under a floating table: its own gap goes to the table's margin
    _, _, paragraphs, _ = hwpx_render("| a |\n|---|\n| 1 |\n\n## 다음 제목\n\n| b |\n|---|\n| 2 |\n")
    first, second = [t for p in paragraphs for t in p.iter(f"{{{NS['hp']}}}tbl")]
    assert first.find("hp:outMargin", NS).get("bottom") == str(283 + 1200)  # heading2 space_before 12pt
    assert second.find("hp:outMargin", NS).get("bottom") == "283"  # nothing follows
