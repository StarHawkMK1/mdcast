"""Judgements on one PDF page the reader cannot fix, only warn about: several columns, a scan, a
drawing made of lines and curves (spec §4.6, §4.7)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mdcast.readers.pdf.model import Box, Line

MIN_SIDE_LINES = 8  # 좌·우 덩어리 각각의 최소 글줄 수
GUTTER = 12.0  # pt. 가운데 빈 틈의 최소 너비
CROSSING_SHARE = 0.1  # 가운데를 가로지르는 글줄이 이 비율을 넘으면 1단
SCAN_COVER = 0.8  # 쪽 넓이 중 그림이 덮는 비율
SCAN_MAX_CHARS = 20
VECTOR_CURVES = 10  # 표 밖 곡선 수

SPLIT = GUTTER  # lines for ``multicolumn`` break at gaps this wide: a narrower one cannot hold the gutter
MIDDLE = (0.3, 0.7)  # the gutter lies within these shares of the page's width
BORDER = 1.0  # pt. a curve poking this far past a table's box is still the table's


def multicolumn(lines: Sequence[Line], page_width: float) -> bool:
    """Lines split into a left and a right block by a strip ``GUTTER`` wide in the middle of the page.

    The strip slides across 30–70% of ``page_width``. Each line ends left of it, starts right of it,
    or crosses it. The page has columns when at most ``CROSSING_SHARE`` of all lines cross (a title
    or a page number across both columns) and at least ``MIN_SIDE_LINES`` on each side stand beside
    a line on the other side, at the same height: a display formula, a running header or a page
    number off to the right of a page of short lines is not a column. ``lines`` must be split at
    wide gaps (``SPLIT``), or two columns' lines on one baseline would be one line crossing the strip.
    """
    low, high = MIDDLE[0] * page_width, MIDDLE[1] * page_width - GUTTER  # where the strip's left edge goes
    if len(lines) < 2 * MIN_SIDE_LINES or high < low:
        return False
    # moving the strip right adds lines to the left only where one ends, and only takes lines
    # from the right, so the edge best for each left block is ``low`` or a line's end
    for left_edge in sorted({low, *(ln.box.x1 for ln in lines if low < ln.box.x1 <= high)}):
        left = [ln.box for ln in lines if ln.box.x1 <= left_edge]
        right = [ln.box for ln in lines if ln.box.x0 >= left_edge + GUTTER]
        if len(lines) - len(left) - len(right) > CROSSING_SHARE * len(lines):
            continue
        if _beside(left, right) >= MIN_SIDE_LINES and _beside(right, left) >= MIN_SIDE_LINES:
            return True
    return False


def _beside(boxes: Sequence[Box], others: Sequence[Box]) -> int:
    """How many of ``boxes`` share some height with one of ``others``."""
    if len(boxes) < MIN_SIDE_LINES:
        return 0
    return sum(any(b.top < o.bottom and o.top < b.bottom for o in others) for b in boxes)


def scanned(char_count: int, images: Sequence[Box], page_box: Box) -> bool:
    """At most ``SCAN_MAX_CHARS`` characters and pictures covering ``SCAN_COVER`` of the page.

    The cover adds the pictures' areas, capped at the whole page: pictures overlapping one another
    count twice, which a scan (one picture per page) never does.
    """
    area = page_box.width * page_box.height
    if area <= 0:
        return False
    cover = min(1.0, sum(box.width * box.height for box in images) / area)
    return char_count <= SCAN_MAX_CHARS and cover >= SCAN_COVER


def vector_heavy(curves: Sequence[Mapping[str, Any]], tables: Sequence[Box]) -> bool:
    """At least ``VECTOR_CURVES`` curves (pdfplumber ``page.curves``) outside every table's box."""
    outside = sum(not any(_inside(c, table) for table in tables) for c in curves)
    return outside >= VECTOR_CURVES


def _inside(curve: Mapping[str, Any], box: Box) -> bool:
    return (
        curve["x0"] >= box.x0 - BORDER
        and curve["top"] >= box.top - BORDER
        and curve["x1"] <= box.x1 + BORDER
        and curve["bottom"] <= box.bottom + BORDER
    )
