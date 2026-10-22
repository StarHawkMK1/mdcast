"""Table grids shared by the readers: cells placed on rows and columns, holes filled, the head grown."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Slot(Generic[T]):
    """A cell on the grid; ``item`` is None for an empty cell filling a hole."""

    item: T | None
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1


def squeeze(slots: list[Slot[T]]) -> list[Slot[T]]:
    """Keep only the rows and columns where a cell starts; spans count the kept ones they cover.

    A row every cell only spans over would be an empty ``<tr>`` in HTML, which pandoc reads back as
    a row of its own; spans past the last row or column shrink to what is there.
    """
    rows = sorted({s.row for s in slots})
    cols = sorted({s.col for s in slots})
    out = []
    for s in slots:
        row, col = bisect_left(rows, s.row), bisect_left(cols, s.col)
        rowspan = bisect_left(rows, s.row + s.rowspan) - row
        colspan = bisect_left(cols, s.col + s.colspan) - col
        out.append(Slot(s.item, row, col, rowspan, colspan))
    return out


def filled(slots: list[Slot[T]]) -> list[list[Slot[T]]]:
    """Grid rows in column order, an empty cell in every hole (HTML has no addresses to skip one)."""
    height = max((s.row + 1 for s in slots), default=0)
    width = max((s.col + s.colspan for s in slots), default=0)
    covered = {
        (r, c)
        for s in slots
        for r in range(s.row, s.row + s.rowspan)
        for c in range(s.col, s.col + s.colspan)
    }
    holes: list[Slot[T]] = [
        Slot(None, r, c) for r in range(height) for c in range(width) if (r, c) not in covered
    ]
    rows: list[list[Slot[T]]] = [[] for _ in range(height)]
    for slot in sorted(slots + holes, key=lambda s: (s.row, s.col)):
        rows[slot.row].append(slot)
    return rows


def grow_head(rows: list[list[Slot[T]]], count: int) -> int:
    """The first ``count`` rows as head, grown over its cells' rowspans.

    pandoc cuts a rowspan at the thead/tbody boundary, moving the cells below it (R4). A head that
    would take every row that way is no head.
    """
    grown = count
    while (end := max((s.row + s.rowspan for row in rows[:grown] for s in row), default=0)) > grown:
        grown = end
    return 0 if grown > count and grown >= len(rows) else grown
