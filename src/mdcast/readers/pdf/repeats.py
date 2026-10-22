"""Running headers and footers: what repeats in the same place at the top or bottom of the pages."""

from __future__ import annotations

from collections import Counter
from collections.abc import Hashable, Iterable, Sequence

from mdcast.readers.pdf.model import Box

BAND = 0.10  # the top and the bottom tenth of a page's height
MIN_PAGES = 3  # and at least half of all pages
BUCKET = 5.0  # points: x positions in one bucket are the same place
# × a line's own size: the next body line is under one line away (a paragraph gap is 8.9 pt at
# 11 pt in typst), while the margin between the body and a footer is wider (20 pt or more)
GAP = 1.5

BandKey = tuple[str, str, str, float, int]  # side, text without digits, anchor, grid offset, bucket


def band_key(box: Box, page_height: float, text: str = "") -> frozenset[BandKey] | None:
    """Where ``box`` sits in a band and what it says without digits, or None outside the bands.

    The whole box must lie in the top or bottom ``BAND`` of its own page, so a picture covering the
    page is in no band. Digits are dropped so page numbers match. The place is keyed three ways,
    by the start, the centre and the end of the box, so a centred "- 9 -" and "- 10 -" still match.
    Each is bucketed on two grids half a bucket apart: two positions under half a bucket apart
    share a bucket on at least one grid, so rounding never splits near-equal positions.
    """
    if box.bottom <= BAND * page_height:
        side = "top"
    elif box.top >= (1 - BAND) * page_height:
        side = "bottom"
    else:
        return None
    words = digitless(text)
    anchors = (("start", box.x0), ("centre", (box.x0 + box.x1) / 2), ("end", box.x1))
    return frozenset(
        (side, words, anchor, offset, round((x - offset) / BUCKET))
        for anchor, x in anchors
        for offset in (0.0, BUCKET / 2)
    )


def digitless(text: str) -> str:
    return "".join(c for c in text if not c.isdigit()).strip()


def repeated(keys_per_page: Sequence[set[Hashable]]) -> set[Hashable]:
    """The keys found on at least ``MIN_PAGES`` pages and on at least half of the pages."""
    counts = Counter(key for keys in keys_per_page for key in keys)
    need = max(MIN_PAGES, len(keys_per_page) / 2)
    return {key for key, pages in counts.items() if pages >= need}


def isolated(box: Box, size: float, body: Iterable[Box]) -> bool:
    """No ``body`` box lies within ``GAP`` × ``size`` above or below ``box``."""
    return all(max(other.top - box.bottom, box.top - other.bottom) >= GAP * size for other in body)


def skipped_message(lines: int, examples: Sequence[str], pictures: int = 0) -> str:
    """What IMPORT_HEADER_SKIPPED says: how many lines and pictures were removed, with one or two
    of the lines."""
    if not lines:
        return f"쪽마다 반복되는 머리말·꼬리말 그림 {pictures}개를 가져오지 않습니다"
    shown = ", ".join(f"'{text}'" for text in examples[:2])
    what = f"{lines}줄과 그림 {pictures}개를" if pictures else f"{lines}줄을"
    return f"쪽마다 반복되는 머리말·꼬리말 {what} 가져오지 않습니다 (예: {shown})"
