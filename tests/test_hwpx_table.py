import pytest

from mdcast.ast import md_to_doc
from mdcast.hwpx.look import TableLook
from mdcast.hwpx.table import build_grid, column_widths, slot_fill, slot_sides, slot_valign

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
