from __future__ import annotations

import io
from dataclasses import dataclass

import panflute as pf
import pdfplumber
import pytest
from pdf_builder import typst_pdf

from mdcast.pipeline import convert
from mdcast.readers.grid import Slot
from mdcast.readers.md import read_md
from mdcast.readers.pdf import read_pdf
from mdcast.readers.pdf.body import read_page
from mdcast.readers.pdf.model import Box
from mdcast.readers.pdf.tables import PageTable, build_table, open_sides
from mdcast.report import Report
from mdcast.types import Format, Source

# a paragraph wrapping over several lines, so the layout is measured on real body text
_BODY = "본문 글은 여러 줄에 걸쳐 이어지는 한 문단입니다. " * 8 + "끝."


@dataclass
class FakeTable:
    bbox: tuple[float, float, float, float]
    cells: list[tuple[float, float, float, float]]


@dataclass
class FakePage:
    chars: list[dict]
    tables: list[FakeTable]
    height: float = 842.0
    bbox: tuple[float, float, float, float] = (0, 0, 595, 842)
    images: tuple[dict, ...] = ()
    curves: tuple[dict, ...] = ()
    edges: tuple[dict, ...] = ()  # no ruling lines: no side is closed

    def find_tables(self) -> list[FakeTable]:
        return self.tables


def word(text: str, x0: float, top: float, size: float = 10.0) -> list[dict]:
    """pdfplumber-like chars, each as wide as it is tall."""
    return [{"text": c, "fontname": "Body-Regular", "size": size, "upright": True,
             "x0": x0 + i * size, "x1": x0 + (i + 1) * size, "top": top, "bottom": top + size}
            for i, c in enumerate(text)]


def pdf_source(data: bytes) -> Source:
    return Source(data, "a.pdf", Format.PDF)


def blocks(body: str) -> list[pf.Block]:
    return list(read_pdf(pdf_source(typst_pdf(body)), Report("a.pdf", Format.PDF), "a_assets").doc.content)


def tables(found: list[pf.Block]) -> list[pf.Table]:
    return [b for b in found if isinstance(b, pf.Table)]


def rows(table: pf.Table) -> list[pf.TableRow]:
    return [*table.head.content, *(r for body in table.content for r in body.content)]


def cell_texts(table: pf.Table) -> list[list[str]]:
    return [[pf.stringify(cell).strip() for cell in row.content] for row in rows(table)]


def spans(table: pf.Table) -> list[list[tuple[int, int]]]:
    return [[(cell.rowspan, cell.colspan) for cell in row.content] for row in rows(table)]


def texts(found: list[pf.Block]) -> list[str]:
    return [pf.stringify(b).strip() for b in found if not isinstance(b, pf.Table)]


def test_merged_cells_spans():
    found = blocks("#table(columns: 3, table.cell(colspan: 2)[a], [b], [c], [d], [e])")
    [table] = tables(found)
    assert cell_texts(table) == [["a", "b"], ["c", "d", "e"]]
    assert spans(table) == [[(1, 2), (1, 1)], [(1, 1), (1, 1), (1, 1)]]


def test_rowspan():
    found = blocks("#table(columns: 2, [h1], [h2], table.cell(rowspan: 2)[a], [b], [c])")
    [table] = tables(found)
    assert cell_texts(table) == [["h1", "h2"], ["a", "b"], ["c"]]
    assert spans(table) == [[(1, 1), (1, 1)], [(2, 1), (1, 1)], [(1, 1)]]


def test_first_row_is_head():
    [table] = tables(blocks("#table(columns: 2, [h1], [h2], [a], [b])"))
    assert [[pf.stringify(c).strip() for c in r.content] for r in table.head.content] == [["h1", "h2"]]
    assert len(table.content) == 1 and len(table.content[0].content) == 1
    assert pf.stringify(table.caption) == ""
    assert table.colspec == [("AlignDefault", "ColWidthDefault")] * 2


def test_table_text_not_in_body():
    found = blocks("위 문단 글입니다.\n\n#table(columns: 2, [칸가], [칸나], [칸다], [칸라])\n\n아래 문단 글입니다.")
    assert [type(b) for b in found] == [pf.Para, pf.Table, pf.Para]
    assert texts(found) == ["위 문단 글입니다.", "아래 문단 글입니다."]
    assert cell_texts(found[1]) == [["칸가", "칸나"], ["칸다", "칸라"]]


def test_cell_paragraphs():
    found = blocks(f"{_BODY}\n\n#table(columns: 2, [머리], [머리 둘], [첫 문단\n\n둘째 문단], [한 문단])")
    [table] = tables(found)
    two, one = table.content[0].content[0].content
    assert [type(b) for b in two.content] == [pf.Para, pf.Para]
    assert [pf.stringify(b).strip() for b in two.content] == ["첫 문단", "둘째 문단"]
    assert [type(b) for b in one.content] == [pf.Plain]


def test_wrapped_sentence_in_narrow_cell_is_one_paragraph():
    sentence = "이 칸의 글은 좁은 칸 안에서 여러 줄로 감겨 내려가는 한 문단입니다."
    data = typst_pdf(f"{_BODY}\n\n#table(columns: (4cm, 4cm), [머리], [둘], [{sentence}], [짧은 글])")
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page = read_page(0, pdf.pages[0])
    assert max(len(lines) for lines in page.cells.values()) > 2  # the sentence does wrap in its cell
    [table] = tables(list(read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").doc.content))
    cell = table.content[0].content[0].content[0]
    assert [type(b) for b in cell.content] == [pf.Plain]
    # Hangul may break inside a word, which joins with a space (spec §4.2, accepted loss)
    assert pf.stringify(cell).replace(" ", "").strip() == sentence.replace(" ", "")


def test_short_lines_in_wide_cell_stay_apart():
    found = blocks(f"{_BODY}\n\n#table(columns: (12cm, 2cm), [머리], [둘], [이름 \\ 주소], [값])")
    [table] = tables(found)
    cell = table.content[0].content[0].content[0]
    assert [type(b) for b in cell.content] == [pf.Para, pf.Para]
    assert [pf.stringify(b).strip() for b in cell.content] == ["이름", "주소"]


def test_char_in_table_outline_but_no_cell_stays_body_text():
    # an L-shaped table: its outline is 0..100 × 0..40 but no cell covers 50..100 × 20..40
    cells = [(0, 0, 50, 20), (50, 0, 100, 20), (0, 20, 50, 40)]
    chars = [*word("가", 10, 5), *word("나", 60, 5), *word("다", 10, 25), *word("밖", 70, 25)]
    page = read_page(0, FakePage(chars, [FakeTable((0, 0, 100, 40), cells)]))
    assert [ln.text for ln in page.lines] == ["밖"]
    assert sorted(ln.text for lines in page.cells.values() for ln in lines) == ["가", "나", "다"]


def test_cell_paragraphs_are_never_headings():
    found = blocks("#table(columns: 2, [#text(size: 20pt)[큰 글]], [b], [c], [d])\n\n" + _BODY)
    [table] = tables(found)
    assert [type(b) for b in table.head.content[0].content[0].content] == [pf.Plain]
    assert not [b for b in found if isinstance(b, pf.Header)]


def test_one_cell_box_unwraps():
    # pdfplumber does not report one-cell tables, so a ruled box's text stays body text in place
    found = blocks(f"{_BODY}\n\n#block(stroke: 1pt, inset: 6pt)[상자 안 글]")
    assert [type(b) for b in found] == [pf.Para, pf.Para]
    assert texts(found)[1] == "상자 안 글"


def test_one_cell_table_gives_its_blocks_as_paras():
    box = Box(0, 0, 100, 20)
    table = PageTable(box, [Slot(box, 0, 0)])
    out = build_table(table, lambda cell: [pf.Plain(pf.Str("상자"))])
    assert [type(b) for b in out] == [pf.Para]
    assert pf.stringify(out[0]).strip() == "상자"


def test_one_by_two_box_stays_table():
    [table] = tables(blocks("#table(columns: 2, [이름표], [긴 안내 글])"))
    assert cell_texts(table) == [["이름표", "긴 안내 글"]]


def test_borderless_table_is_text():
    data = typst_pdf("#table(stroke: none, columns: 2, [칸가], [칸나], [칸다], [칸라])")
    found = list(read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").doc.content)
    assert not tables(found)
    assert all(t in " ".join(texts(found)) for t in ["칸가", "칸나", "칸다", "칸라"])
    assert convert(pdf_source(data), [Format.MD]).report.coverage == 1.0


def test_cell_text_in_source_text():
    data = typst_pdf("위 글\n\n#table(columns: 2, [칸가], [칸나], [칸다], [칸라])\n\n아래 글")
    source = read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").source_text
    assert source == ["위 글", "칸가", "칸나", "칸다", "칸라", "아래 글"]


def test_merged_table_reads_back_from_md():
    result = convert(pdf_source(typst_pdf("#table(columns: 3, table.cell(colspan: 2)[a], [b], [c], [d], [e])")),
                     [Format.MD])
    assert result.report.coverage == 1.0
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc
    [table] = tables(list(back.content))
    assert cell_texts(table) == [["a", "b"], ["c", "d", "e"]]
    assert spans(table) == [[(1, 2), (1, 1)], [(1, 1), (1, 1), (1, 1)]]
    assert len(table.head.content) == 1


# row rules and inner column rules only: no rule down the outer left and right sides
_OPEN_SIDES = "stroke: (x, y) => (top: 0.5pt, bottom: 0.5pt, left: if x > 0 { 0.5pt } else { none }, right: none)"


def test_open_sided_table_keeps_its_outer_cells():
    data = typst_pdf(
        f"{_BODY}\n\n#table(columns: 3, {_OPEN_SIDES}, [머리 가], [머리 나], [머리 다], "
        "table.cell(rowspan: 2)[묶음], [칸 가], [칸 나], [칸 다], [칸 라])"
    )
    found = list(read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").doc.content)
    assert [type(b) for b in found] == [pf.Para, pf.Table]  # nothing of the table follows it as body text
    [table] = tables(found)
    assert cell_texts(table) == [["머리 가", "머리 나", "머리 다"], ["묶음", "칸 가", "칸 나"], ["칸 다", "칸 라"]]
    assert spans(table) == [[(1, 1)] * 3, [(2, 1), (1, 1), (1, 1)], [(1, 1), (1, 1)]]
    assert convert(pdf_source(data), [Format.MD]).report.coverage == 1.0


_FULL = "table.cell(colspan: 3)[가로 칸]"
_ROW_A, _ROW_B = "[가 하나], [가 둘], [가 셋]", "[나 하나], [나 둘], [나 셋]"


@pytest.mark.parametrize(
    ("cells", "expected"),
    [
        (f"{_ROW_A}, {_ROW_B}, {_FULL}", [["가 하나", "가 둘", "가 셋"], ["나 하나", "나 둘", "나 셋"], ["가로 칸"]]),
        (f"{_FULL}, {_ROW_A}, {_ROW_B}", [["가로 칸"], ["가 하나", "가 둘", "가 셋"], ["나 하나", "나 둘", "나 셋"]]),
        (f"{_ROW_A}, {_FULL}, {_ROW_B}", [["가 하나", "가 둘", "가 셋"], ["가로 칸"], ["나 하나", "나 둘", "나 셋"]]),
    ],
    ids=["last", "first", "middle"],
)
def test_open_sided_table_keeps_its_full_width_row(cells, expected):
    data = typst_pdf(f"{_BODY}\n\n#table(columns: 3, {_OPEN_SIDES}, {cells})")
    found = list(read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").doc.content)
    assert [type(b) for b in found] == [pf.Para, pf.Table]  # nothing after or between the table's rows
    [table] = tables(found)
    assert cell_texts(table) == expected
    row = expected.index(["가로 칸"])
    assert spans(table)[row] == [(1, 3)]
    assert convert(pdf_source(data), [Format.MD]).report.coverage == 1.0


def test_full_width_row_joins_rows_with_an_empty_outer_column():
    # below the full-width row the right-hand outer cells are empty: that side is still open above
    lower = "[나 하나], [나 둘], [], [다 하나], [다 둘], []"
    data = typst_pdf(f"{_BODY}\n\n#table(columns: 3, {_OPEN_SIDES}, {_ROW_A}, {_FULL}, {lower})")
    found = list(read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").doc.content)
    assert [type(b) for b in found] == [pf.Para, pf.Table]
    [table] = tables(found)
    assert cell_texts(table) == [["가 하나", "가 둘", "가 셋"], ["가로 칸"], ["나 하나", "나 둘", ""], ["다 하나", "다 둘", ""]]
    assert spans(table)[1] == [(1, 3)]
    assert convert(pdf_source(data), [Format.MD]).report.coverage == 1.0


def test_paragraph_between_open_sided_tables_stays_between():
    # the paragraph's rules are the tables' own and have their ends, but it sits in the room around them
    two = f"#table(columns: 3, {_OPEN_SIDES}, {_ROW_A}, {_ROW_B})"
    found = blocks(f"{_BODY}\n\n{two}\n\n사이 문단 한 줄\n\n{two}")
    assert [type(b) for b in found] == [pf.Para, pf.Table, pf.Para, pf.Table]
    assert texts(found)[1] == "사이 문단 한 줄"


@pytest.mark.parametrize("inset", [5, 14])
def test_paragraph_between_ruled_tables_stays_between(inset):
    # closed tables never join across a row with no vertical rule, however tight or loose their rows
    two = f"#table(columns: 3, inset: {inset}pt, {_ROW_A}, {_ROW_B})"
    found = blocks(f"{_BODY}\n\n{two}\n\n사이 문단 한 줄\n\n{two}")
    assert [type(b) for b in found] == [pf.Para, pf.Table, pf.Para, pf.Table]
    assert texts(found)[1] == "사이 문단 한 줄"


def test_paragraph_between_empty_grids_stays_between():
    # blank form sections: ruled grids with no text in them
    empty = "#table(columns: (3cm, 3cm, 3cm), rows: 18pt, [], [], [], [], [], [])"
    found = blocks(f"{_BODY}\n\n{empty}\n\n사이 문단 한 줄\n\n{empty}")
    assert [type(b) for b in found] == [pf.Para, pf.Table, pf.Para, pf.Table]
    assert texts(found)[1] == "사이 문단 한 줄"


def test_two_rules_around_text_are_no_table():
    found = blocks(f"#line(length: 100%)\n\n{_BODY}\n\n#line(length: 100%)")
    assert not tables(found)
    assert [type(b) for b in found] == [pf.Para]


def _rule(x0: float, x1: float, y: float) -> dict:
    return {"orientation": "h", "x0": x0, "x1": x1, "top": y, "bottom": y}


def _upright(x: float, top: float, bottom: float) -> dict:
    return {"orientation": "v", "x0": x, "x1": x, "top": top, "bottom": bottom}


def _glyph(x: float, y: float) -> Box:
    """A 6pt character centred on (x, y)."""
    return Box(x - 3, y - 3, x + 3, y + 3)


_CELL_TEXT = [_glyph(50, 110), _glyph(150, 110), _glyph(250, 130)]  # in the outer and middle columns


def test_open_sides_spans_only_the_stack():
    rules = [_rule(0, 300, y) for y in (100, 120, 140)]
    inner = [_upright(100, 100, 140), _upright(200, 100, 140)]
    unrelated = [_rule(0, 300, 400), _rule(0, 300, 420)]  # the same ends, but nothing joins them
    sides = open_sides([*rules, *inner, *unrelated], [*_CELL_TEXT, _glyph(50, 410)])
    assert sorted((s["x0"], s["top"], s["bottom"]) for s in sides) == [(0, 100, 140), (300, 100, 140)]


def test_open_sides_needs_text_outside_the_rules():
    rules = [_rule(0, 300, y) for y in (100, 120, 140)]
    inner = [_upright(100, 100, 140), _upright(200, 100, 140)]
    assert open_sides([*rules, *inner], [_glyph(150, 110)]) == []  # nothing in the outer columns to rescue


@pytest.mark.parametrize("overhang", [2, 5, 12])
def test_open_sides_leaves_ruled_tables_alone(overhang):
    # row rules that overhang the side rules (2pt in the corpus) leave nothing outside the cells
    rules = [_rule(0, 300, y) for y in (100, 120, 140)]
    sides = [_upright(overhang, 100, 140), _upright(150, 100, 140), _upright(300 - overhang, 100, 140)]
    assert open_sides([*rules, *sides], [_glyph(overhang + 20, 110), _glyph(250, 130)]) == []


def test_open_sides_never_join_closed_tables():
    # two ruled tables of 30pt rows, side rules 2pt in, one paragraph glyph in the gap between them
    rules = [_rule(0, 300, y) for y in (100, 130, 160, 190, 220, 250)]
    first = [_upright(2, 100, 160), _upright(150, 100, 160), _upright(298, 100, 160)]
    second = [_upright(2, 190, 250), _upright(150, 190, 250), _upright(298, 190, 250)]
    cells = [_glyph(50, 115), _glyph(200, 145), _glyph(50, 205), _glyph(200, 235)]
    assert open_sides([*rules, *first, *second], [*cells, _glyph(100, 175)]) == []


def test_open_sides_never_join_textless_runs():
    rules = [_rule(0, 300, y) for y in (100, 120, 140, 160, 180, 200)]
    inner = [_upright(150, 100, 140), _upright(150, 160, 200)]  # open sides, no text in the cells
    assert open_sides([*rules, *inner], [_glyph(100, 150)]) == []


def test_full_width_row_far_below_stays_out():
    rules = [_rule(0, 300, y) for y in (100, 120, 140, 200)]  # the last row is 60pt: over 2 × 20pt
    inner = [_upright(100, 100, 140), _upright(200, 100, 140)]
    sides = open_sides([*rules, *inner], [*_CELL_TEXT, _glyph(150, 170)])
    assert sorted((s["x0"], s["top"], s["bottom"]) for s in sides) == [(0, 100, 140), (300, 100, 140)]


@pytest.mark.parametrize("inset", ["", "inset: (left: 0pt, rest: 5pt), "], ids=["inset", "flush-left"])
def test_nested_table_is_text_of_the_outer_cell(inset):
    # pdfplumber reports a table drawn inside a cell as a table of its own beside the outer one
    data = typst_pdf(f"#table(columns: 2, {inset}[바깥 가], [바깥 나], "
                     "[#table(columns: 2, [안 가], [안 나])], [바깥 라])")
    found = list(read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").doc.content)
    [table] = tables(found)
    assert cell_texts(table) == [["바깥 가", "바깥 나"], ["안 가 안 나", "바깥 라"]]
    assert convert(pdf_source(data), [Format.MD]).report.coverage == 1.0
