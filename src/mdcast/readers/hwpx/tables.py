"""Read an ``hp:tbl`` into a pandoc table: cells placed by address, merges and header rows kept."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from itertools import chain
from typing import TYPE_CHECKING

import panflute as pf
from lxml import etree

from mdcast.readers.hwpx.package import HP

if TYPE_CHECKING:
    from mdcast.readers.hwpx.body import BodyReader

_TR, _TC = f"{{{HP}}}tr", f"{{{HP}}}tc"
_ADDR, _SPAN = f"{{{HP}}}cellAddr", f"{{{HP}}}cellSpan"
_SUB, _CAPTION = f"{{{HP}}}subList", f"{{{HP}}}caption"
_COLUMN = ("AlignDefault", "ColWidthDefault")


@dataclass
class _Slot:
    """A cell on the grid; ``tc`` is None for an empty cell filling a hole."""

    tc: etree._Element | None
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1


def _number(value: str | None) -> int | None:
    """A non-negative integer attribute, or None."""
    try:
        number = int(value or "")
    except ValueError:
        return None
    return number if number >= 0 else None


def _spans(tc: etree._Element) -> tuple[int, int]:
    span = tc.find(_SPAN)
    if span is None:
        return 1, 1
    return max(1, _number(span.get("rowSpan")) or 1), max(1, _number(span.get("colSpan")) or 1)


def _by_address(tbl: etree._Element, tcs: list[etree._Element]) -> list[_Slot] | None:
    """Cells where ``cellAddr`` puts them; None when an address is missing, out of range or overlaps."""
    rows, cols = _number(tbl.get("rowCnt")), _number(tbl.get("colCnt"))
    slots = []
    for tc in tcs:
        addr = tc.find(_ADDR)
        if addr is None:
            return None
        row, col = _number(addr.get("rowAddr")), _number(addr.get("colAddr"))
        if row is None or col is None or (rows and row >= rows) or (cols and col >= cols):
            return None
        slots.append(_Slot(tc, row, col, *_spans(tc)))
    slots = _squeeze(slots)
    taken: set[tuple[int, int]] = set()
    for slot in slots:
        area = {
            (r, c)
            for r in range(slot.row, slot.row + slot.rowspan)
            for c in range(slot.col, slot.col + slot.colspan)
        }
        if area & taken:
            return None
        taken |= area
    return slots


def _by_order(rows: list[list[etree._Element]]) -> list[_Slot]:
    """Cells in ``hp:tr``/``hp:tc`` order, each in the next column no span from above or the left covers."""
    limit = max(1, sum(map(len, rows)))  # wider spans only cover columns where no cell starts
    taken: set[tuple[int, int]] = set()
    slots = []
    for r, tcs in enumerate(rows):
        col = 0
        for tc in tcs:
            while (r, col) in taken:
                col += 1
            rowspan, colspan = _spans(tc)
            rowspan = min(rowspan, len(rows) - r)
            width = 1
            while width < min(colspan, limit) and (r, col + width) not in taken:
                width += 1
            height = 1
            while height < rowspan and all(
                (r + height, c) not in taken for c in range(col, col + width)
            ):
                height += 1
            taken |= {(row, c) for row in range(r, r + height) for c in range(col, col + width)}
            slots.append(_Slot(tc, r, col, height, width))
            col += width
    return _squeeze(slots)


def _squeeze(slots: list[_Slot]) -> list[_Slot]:
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
        out.append(_Slot(s.tc, row, col, rowspan, colspan))
    return out


def _filled(slots: list[_Slot]) -> list[list[_Slot]]:
    """Grid rows in column order, an empty cell in every hole (HTML has no addresses to skip one)."""
    height = max((s.row + 1 for s in slots), default=0)
    width = max((s.col + s.colspan for s in slots), default=0)
    covered = {
        (r, c)
        for s in slots
        for r in range(s.row, s.row + s.rowspan)
        for c in range(s.col, s.col + s.colspan)
    }
    holes = [
        _Slot(None, r, c) for r in range(height) for c in range(width) if (r, c) not in covered
    ]
    rows: list[list[_Slot]] = [[] for _ in range(height)]
    for slot in sorted(slots + holes, key=lambda s: (s.row, s.col)):
        rows[slot.row].append(slot)
    return rows


def _head_rows(rows: list[list[_Slot]]) -> int:
    """Rows from the top whose cells are all ``header="1"``; with no mark in the table, the first row.

    The head then grows over its cells' rowspans: pandoc cuts a span at the end of the head, which
    would move the cells below. A head that would take every row that way is no head.
    """

    def marked(slot: _Slot) -> bool:
        return slot.tc is not None and slot.tc.get("header") == "1"

    real = [[s for s in row if s.tc is not None] for row in rows]
    if not any(marked(s) for row in real for s in row):
        count = min(1, len(rows))
    else:
        count = 0
        while count < len(rows) and real[count] and all(marked(s) for s in real[count]):
            count += 1
    grown = count
    while (end := max((s.row + s.rowspan for row in rows[:grown] for s in row), default=0)) > grown:
        grown = end
    return 0 if grown > count and grown >= len(rows) else grown


def read_table(tbl: etree._Element, reader: BodyReader) -> pf.Table:
    """One ``hp:tbl``; cells whose addresses do not add up are placed in document order instead."""
    by_row = [list(tr.iterchildren(_TC)) for tr in tbl.iterchildren(_TR)]
    slots = _by_address(tbl, list(chain.from_iterable(by_row))) or _by_order(by_row)
    rows = _filled(slots)

    def table_row(row: list[_Slot]) -> pf.TableRow:
        return pf.TableRow(
            *(
                pf.TableCell(
                    *reader.sub_list(s.tc.find(_SUB)), rowspan=s.rowspan, colspan=s.colspan
                )
                if s.tc is not None
                else pf.TableCell()
                for s in row
            )
        )

    built = [table_row(row) for row in rows]
    head = _head_rows(rows)
    caption = tbl.find(_CAPTION)
    return pf.Table(
        pf.TableBody(*built[head:]),
        head=pf.TableHead(*built[:head]),
        caption=pf.Caption(*reader.sub_list(caption.find(_SUB) if caption is not None else None)),
        colspec=[_COLUMN] * max((s.col + s.colspan for s in slots), default=0),
    )
