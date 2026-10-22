"""Ruled tables (spec §4.4): pdfplumber's line-found cells placed on a grid, merges kept."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

import panflute as pf
import pdfplumber

from mdcast.readers.grid import Slot, filled, grow_head, squeeze
from mdcast.readers.pdf.model import Box

SNAP = 1.0  # pt. Cell edges this close lie on one grid line


@dataclass
class PageTable:
    box: Box
    slots: list[Slot[Box]]  # the squeezed grid in row order; ``item`` is the cell's box


def find_tables(page: pdfplumber.page.Page) -> list[PageTable]:
    """The tables pdfplumber finds from the page's ruling lines (its default ``lines`` strategy).

    Borderless tables are not looked for: their text stays body text. pdfplumber leaves out a
    table of a single cell, so a lone ruled box is body text too.
    """
    return [_table(Box(*found.bbox), found.cells) for found in page.find_tables()]


def _table(box: Box, cells: list[tuple[float, float, float, float]]) -> PageTable:
    """Each cell spans the grid lines its edges lie on; rows and columns where no cell starts go."""
    boxes = [Box(*cell) for cell in cells]
    xs = _grid_lines(v for b in boxes for v in (b.x0, b.x1))
    ys = _grid_lines(v for b in boxes for v in (b.top, b.bottom))
    slots = [
        Slot(
            b,
            ys[b.top],
            xs[b.x0],
            rowspan=max(1, ys[b.bottom] - ys[b.top]),
            colspan=max(1, xs[b.x1] - xs[b.x0]),
        )
        for b in boxes
    ]
    return PageTable(box, sorted(squeeze(slots), key=lambda s: (s.row, s.col)))


def _grid_lines(values: Iterable[float]) -> dict[float, int]:
    """Each value → the number of its grid line; values within SNAP of a line's first value are on it."""
    lines: dict[float, int] = {}
    number, first = -1, 0.0
    for value in sorted(set(values)):
        if number < 0 or value - first > SNAP:
            number, first = number + 1, value
        lines[value] = number
    return lines


def build_table(table: PageTable, cell_blocks: Callable[[Box], list[pf.Block]]) -> list[pf.Block]:
    """``[pf.Table]`` shaped as hwpx ``read_table`` makes it: the first row is the head, no caption,
    default column alignment.

    A table of one cell is a text box, not a table: its blocks come out as they are, a Plain as
    Para since a top-level Plain is written as a paragraph and reads back as one.
    """
    if len(table.slots) == 1:
        return [pf.Para(*b.content) if isinstance(b, pf.Plain) else b for b in cell_blocks(table.slots[0].item)]
    rows = filled(table.slots)
    built = [
        pf.TableRow(
            *(
                pf.TableCell(*cell_blocks(s.item), rowspan=s.rowspan, colspan=s.colspan)
                if s.item is not None
                else pf.TableCell()
                for s in row
            )
        )
        for row in rows
    ]
    head = grow_head(rows, min(1, len(rows)))
    width = max((s.col + s.colspan for s in table.slots), default=0)
    return [
        pf.Table(
            pf.TableBody(*built[head:]),
            head=pf.TableHead(*built[:head]),
            caption=pf.Caption(),
            colspec=[("AlignDefault", "ColWidthDefault")] * width,
        )
    ]
