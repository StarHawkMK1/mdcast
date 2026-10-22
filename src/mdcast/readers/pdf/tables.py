"""Ruled tables (spec §4.4): pdfplumber's line-found cells placed on a grid, merges kept."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import panflute as pf
import pdfplumber

from mdcast.readers.grid import Slot, filled, grow_head, squeeze
from mdcast.readers.pdf.model import Box

SNAP = 1.0  # pt. Cell edges this close lie on one grid line
SPAN_ROW_REACH = 2.0  # a full-width row joins a stack when no taller than this many of its tallest rows
FIT_SLACK = 2.0  # pt. A full-width row may leave this much more room around its text than the tightest row
# Accepted limit: between two open-sided tables whose rows all sit loosely around their text, a
# paragraph that fits as tightly reads as a full-width row and joins them (its text is kept).

Edge = Mapping[str, Any]  # a pdfplumber edge: x0, x1, top, bottom, orientation ("h" or "v")


@dataclass
class PageTable:
    box: Box
    slots: list[Slot[Box]]  # the squeezed grid in row order; ``item`` is the cell's box


def find_tables(page: pdfplumber.page.Page) -> list[PageTable]:
    """The tables pdfplumber finds from the page's ruling lines (its default ``lines`` strategy).

    Borderless tables are not looked for: their text stays body text. pdfplumber leaves out a
    table of a single cell, so a lone ruled box is body text too. A table drawn inside another's
    cell is left out as well: its text is the outer cell's (spec §4.4). A table drawn without
    its outer left or right rule is closed first (:func:`open_sides`).
    """
    kept: list[PageTable] = []
    rules = _ruling(e for e in page.edges if e["object_type"] != "curve_edge")  # rules, not drawings
    chars = [Box(c["x0"], c["top"], c["x1"], c["bottom"]) for c in page.chars if c["text"].strip()]
    sides = open_sides(rules, chars)
    found_tables = page.find_tables({"explicit_vertical_lines": sides}) if sides else page.find_tables()
    found = [_table(Box(*t.bbox), t.cells) for t in found_tables]
    for table in sorted(found, key=lambda t: t.box.width * t.box.height, reverse=True):  # outer first
        if not any(_inside(table.box, outer.box) for outer in kept):
            kept.append(table)
    return kept


def _ruling(edges: Iterable[Edge]) -> list[Edge]:
    """``edges`` snapped and joined as pdfplumber's ``lines`` strategy does before it finds cells."""
    s = pdfplumber.table.TableSettings.resolve(None)
    merged = pdfplumber.table.merge_edges(
        list(edges),
        snap_x_tolerance=s.snap_x_tolerance,
        snap_y_tolerance=s.snap_y_tolerance,
        join_x_tolerance=s.join_x_tolerance,
        join_y_tolerance=s.join_y_tolerance,
    )
    return pdfplumber.utils.filter_edges(merged, min_length=s.edge_min_length)


def open_sides(edges: Sequence[Edge], chars: Sequence[Box]) -> list[dict[str, Any]]:
    """Vertical edges that close tables drawn without their outer left or right rule.

    Korean public documents often leave a table's sides open: the row rules run out to where the
    side rule would be, but no rule is drawn there, so pdfplumber finds no cell in the outer
    columns. Row rules whose left (or right) ends meet within SNAP form a stack (:func:`_stacks`).
    A stack is open when the centre of a character (``chars``: their boxes) lies between the
    rules' ends and the outermost vertical rule of one of its rows: that text would fall out of
    the table. An open stack gets one side edge from its top rule to its bottom rule. A closed
    table, however far its rules overhang its side rules, has nothing there and gets none.
    """
    rules = [e for e in edges if e["orientation"] == "h"]
    uprights = [e for e in edges if e["orientation"] == "v"]
    sides: list[dict[str, Any]] = []
    for left in (True, False):
        end = "x0" if left else "x1"
        for group in _meeting(rules, end):
            x = min(r["x0"] for r in group) if left else max(r["x1"] for r in group)
            for run in _stacks(group, uprights, chars, x, left):
                if run.open:
                    sides.append(_upright(x, run.rules[0]["top"], run.rules[-1]["top"]))
    return sides


def _meeting(rules: Sequence[Edge], end: str) -> list[list[Edge]]:
    """The rules grouped by where their ``end`` ("x0" or "x1") lies, ends within SNAP together."""
    groups: list[list[Edge]] = []
    for rule in sorted(rules, key=lambda r: r[end]):
        if groups and rule[end] - groups[-1][-1][end] <= SNAP:
            groups[-1].append(rule)
        else:
            groups.append([rule])
    return groups


@dataclass
class _Run:
    rules: list[Edge]
    tallest: float = 0.0  # the tallest row a real vertical rule joins; 0 for a lone rule
    slack: float = math.inf  # the least row height left over by its text, over those rows with text
    open: bool = False  # text lies outside its outermost vertical rules: its side is missing

    @property
    def mergeable(self) -> bool:
        """A lone rule, or an open run with text, may join across a row with no vertical rule."""
        return len(self.rules) == 1 or (self.open and self.slack < math.inf)


def _stacks(
    group: Sequence[Edge], uprights: Sequence[Edge], chars: Sequence[Box], x: float, left: bool
) -> list[_Run]:
    """``group`` top to bottom in runs of two or more rules, each judged open or not.

    A rule joins the one above when a real vertical rule inside runs between them. A run is open
    when one of its rows has text outside its outermost vertical rule (:func:`_text_outside`).
    A row with no vertical inside (a cell across every column) joins its neighbours into one run
    when (:func:`_abut`) each neighbour is open with text of its own or a lone rule, its rules have
    both of their ends, within SNAP, it is at most SPAN_ROW_REACH times their tallest row high, and
    it holds text as tightly as their tightest row (within FIT_SLACK). Closed tables never join:
    their own full-width rows lie within their side rules already, and a paragraph between two of
    them stays a paragraph. A lone pair of rules never forms a run, so it never becomes a table.
    """
    runs: list[_Run] = []
    for rule in sorted(group, key=lambda r: r["top"]):
        if runs and _joined(runs[-1].rules[-1], rule, uprights, x, left):
            run, above = runs[-1], runs[-1].rules[-1]
            run.tallest = max(run.tallest, rule["top"] - above["top"])
            run.slack = min(run.slack, _slack(above, rule, chars))
            run.open = run.open or _text_outside(above, rule, uprights, chars, x, left)
            run.rules.append(rule)
        else:
            runs.append(_Run([rule]))
    i = 0
    while i + 1 < len(runs):
        upper, lower = runs[i], runs[i + 1]
        if _abut(upper, lower, chars):
            tallest, slack = max(upper.tallest, lower.tallest), min(upper.slack, lower.slack)
            runs[i : i + 2] = [_Run(upper.rules + lower.rules, tallest, slack, open=True)]
            i = max(i - 1, 0)
        else:
            i += 1
    return [run for run in runs if len(run.rules) > 1]


def _abut(upper: _Run, lower: _Run, chars: Sequence[Box]) -> bool:
    """The row between ``upper`` and ``lower``, with no vertical rule inside, belongs to their table."""
    reach = SPAN_ROW_REACH * max(upper.tallest, lower.tallest)
    above, below = upper.rules[-1], lower.rules[0]
    return (
        reach > 0  # one of them has rows
        and upper.mergeable
        and lower.mergeable
        and abs(above["x0"] - below["x0"]) <= SNAP
        and abs(above["x1"] - below["x1"]) <= SNAP
        and below["top"] - above["top"] <= reach
        and _slack(above, below, chars) <= min(upper.slack, lower.slack) + FIT_SLACK
    )


def _slack(upper: Edge, lower: Edge, chars: Sequence[Box]) -> float:
    """The row's height less the height its characters take; inf when it holds none."""
    x0, x1 = max(upper["x0"], lower["x0"]), min(upper["x1"], lower["x1"])
    inside = [c for c in chars if _between(c, x0, x1, upper, lower)]
    if not inside:
        return math.inf
    return (lower["top"] - upper["top"]) - (max(c.bottom for c in inside) - min(c.top for c in inside))


def _between(char: Box, x0: float, x1: float, upper: Edge, lower: Edge) -> bool:
    """The character's centre lies between ``x0`` and ``x1`` and between the two rules."""
    cx, cy = (char.x0 + char.x1) / 2, (char.top + char.bottom) / 2
    return x0 < cx < x1 and upper["top"] < cy < lower["top"]


def _joined(upper: Edge, lower: Edge, uprights: Sequence[Edge], x: float, left: bool) -> bool:
    """A vertical rule between ``x`` and the rules' far ends runs from ``upper`` down to ``lower``."""
    if left:
        lo, hi = x + SNAP, min(upper["x1"], lower["x1"]) - SNAP
    else:
        lo, hi = max(upper["x0"], lower["x0"]) + SNAP, x - SNAP
    return any(lo < v["x0"] < hi and _spans(v, upper["top"], lower["top"]) for v in uprights)


def _text_outside(
    upper: Edge, lower: Edge, uprights: Sequence[Edge], chars: Sequence[Box], x: float, left: bool
) -> bool:
    """A character of the row between ``upper`` and ``lower`` lies between ``x`` and the row's
    outermost vertical rule (the rules' far end when the row has none)."""
    row = [v["x0"] for v in uprights if _spans(v, upper["top"], lower["top"])]
    if left:
        far = min(upper["x1"], lower["x1"])
        lo, hi = x, min((v for v in row if x - SNAP < v < far), default=far)
    else:
        far = max(upper["x0"], lower["x0"])
        lo, hi = max((v for v in row if far < v < x + SNAP), default=far), x
    return any(_between(c, lo, hi, upper, lower) for c in chars)


def _spans(upright: Edge, top: float, bottom: float) -> bool:
    return upright["top"] <= top + SNAP and upright["bottom"] >= bottom - SNAP


def _upright(x: float, top: float, bottom: float) -> dict[str, Any]:
    """A vertical edge pdfplumber takes as it is (an ``object_type`` ending in ``_edge``)."""
    return {
        "object_type": "virtual_edge",
        "orientation": "v",
        "x0": x,
        "x1": x,
        "top": top,
        "bottom": bottom,
        "width": 0.0,
        "height": bottom - top,
    }


def _inside(inner: Box, outer: Box) -> bool:
    """``inner`` lies within ``outer``, give or take SNAP."""
    return (
        inner.x0 >= outer.x0 - SNAP
        and inner.top >= outer.top - SNAP
        and inner.x1 <= outer.x1 + SNAP
        and inner.bottom <= outer.bottom + SNAP
    )


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
