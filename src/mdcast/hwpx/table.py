"""Table grid, column widths and cell looks (spec 2026-10-20 §4.1–§4.4); no XML here."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import panflute as pf

from mdcast.hwpx.look import Border, TableLook

MIN_COLUMN_MM = 10.0  # narrowest auto column
_VALIGN = {"top": "TOP", "middle": "CENTER", "bottom": "BOTTOM"}


def text_em(text: str) -> float:
    """Rough rendered width in em, as the docx writer estimates list markers."""
    return sum(1.0 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 0.55 for ch in text)


@dataclass(frozen=True)
class Slot:
    row: int
    col: int
    rowspan: int
    colspan: int
    cell: pf.TableCell | None  # None: a filler for a short row
    part: str  # "head" (table.head rows) | "body" (body.head + body.content rows) | "foot"
    body_row: int  # 0-based index among body-part rows (zebra); -1 outside the body


@dataclass(frozen=True)
class Grid:
    rows: list[list[Slot]]  # slots that start in each row, left to right
    cols: int


def _rows(table: pf.Table) -> list[tuple[pf.TableRow, str]]:
    rows = [(row, "head") for row in (table.head.content if table.head else [])]
    for body in table.content:
        rows += [(row, "body") for row in [*body.head, *body.content]]
    rows += [(row, "foot") for row in (table.foot.content if table.foot else [])]
    return rows


def build_grid(table: pf.Table) -> Grid:
    rows = _rows(table)
    cols = len(table.colspec) or max(
        (sum(max(1, cell.colspan) for cell in row.content) for row, _ in rows), default=0
    )
    covered = [0] * cols  # per column: rows still covered by a span from above
    grid: list[list[Slot]] = []
    body_row = 0
    for index, (row, part) in enumerate(rows):
        slots: list[Slot] = []
        number = body_row if part == "body" else -1
        col = 0
        for cell in row.content:
            while col < cols and covered[col]:
                col += 1
            if col >= cols:
                break
            colspan = min(max(1, cell.colspan), cols - col)
            rowspan = min(max(1, cell.rowspan), len(rows) - index)
            slots.append(Slot(index, col, rowspan, colspan, cell, part, number))
            for c in range(col, col + colspan):
                covered[c] = rowspan
            col += colspan
        for c in range(cols):
            if not covered[c]:  # a short row: fill the places nothing covers
                slots.append(Slot(index, c, 1, 1, None, part, number))
                covered[c] = 1
        slots.sort(key=lambda slot: slot.col)
        grid.append(slots)
        covered = [max(0, n - 1) for n in covered]
        if part == "body":
            body_row += 1
    return Grid(grid, cols)


def _natural(grid: Grid, look: TableLook, size_pt: float) -> list[float]:
    """Each column's widest one-column cell text plus padding, at least MIN_COLUMN_MM."""
    widths = [MIN_COLUMN_MM] * grid.cols
    for row in grid.rows:
        for slot in row:
            if slot.colspan == 1 and slot.cell is not None:
                text = text_em(pf.stringify(slot.cell)) * size_pt * 25.4 / 72 + 2 * look.padding
                widths[slot.col] = max(widths[slot.col], text)
    return widths


def column_widths(table: pf.Table, grid: Grid, look: TableLook, available: float, size_pt: float) -> list[float]:
    """Column widths in mm (spec §4.2)."""
    fractions: list[float | None] = []
    for index in range(grid.cols):
        spec = table.colspec[index] if index < len(table.colspec) else None
        width = spec[1] if spec else "ColWidthDefault"
        fractions.append(float(width) if isinstance(width, (int, float)) and width > 0 else None)
    given = [f for f in fractions if f is not None]
    if look.width == "auto":
        natural = _natural(grid, look, size_pt)
        widths = [f * available if f is not None else natural[i] for i, f in enumerate(fractions)]
    else:
        mean = sum(given) / len(given) if given else 1.0
        filled = [f if f is not None else mean for f in fractions]
        total = sum(filled) or 1.0
        widths = [f / total * available for f in filled]
    total = sum(widths)
    if total > available:
        widths = [w * available / total for w in widths]
    return widths


def slot_sides(slot: Slot, grid: Grid, look: TableLook) -> tuple[Border, Border, Border, Border]:
    """left, right, top, bottom: ``border_outer`` where the side is on the table's edge."""
    last_row = len(grid.rows)
    return (
        look.border_outer if slot.col == 0 else look.border,
        look.border_outer if slot.col + slot.colspan >= grid.cols else look.border,
        look.border_outer if slot.row == 0 else look.border,
        look.border_outer if slot.row + slot.rowspan >= last_row else look.border,
    )


def slot_fill(slot: Slot, look: TableLook) -> str | None:
    """Background: header > first column > zebra (Word's conditional formatting order)."""
    if slot.part == "head":
        return look.header_background
    if slot.col == 0 and look.first_column_background:
        return look.first_column_background
    if slot.part == "body" and look.zebra and slot.body_row % 2 == 1:
        return look.zebra
    return None


def slot_valign(slot: Slot, look: TableLook) -> str:
    return _VALIGN.get(look.header_valign if slot.part == "head" else look.body_valign, "CENTER")
