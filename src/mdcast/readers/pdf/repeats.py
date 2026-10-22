"""Running headers and footers: what repeats in the same place at the top or bottom of the pages."""

from __future__ import annotations

from collections import Counter
from collections.abc import Hashable, Sequence

from mdcast.readers.pdf.model import Box

BAND = 0.10  # the top and the bottom tenth of a page's height
MIN_PAGES = 3  # and at least half of all pages

BandKey = tuple[str, str, int]


def band_key(box: Box, page_height: float, text: str = "") -> BandKey | None:
    """Where ``box`` sits in a band and what it says without digits, or None outside the bands.

    The whole box must lie in the top or bottom ``BAND`` of its own page, so a picture covering the
    page is in no band. Digits are dropped so page numbers match; x0 is kept to 5 points.
    """
    if box.bottom <= BAND * page_height:
        side = "top"
    elif box.top >= (1 - BAND) * page_height:
        side = "bottom"
    else:
        return None
    return side, "".join(c for c in text if not c.isdigit()).strip(), round(box.x0 / 5)


def repeated(keys_per_page: Sequence[set[Hashable]]) -> set[Hashable]:
    """The keys found on at least ``MIN_PAGES`` pages and on at least half of the pages."""
    counts = Counter(key for keys in keys_per_page for key in keys)
    need = max(MIN_PAGES, len(keys_per_page) / 2)
    return {key for key, pages in counts.items() if pages >= need}


def skipped_message(lines: int, examples: Sequence[str]) -> str:
    """What IMPORT_HEADER_SKIPPED says: how many lines were removed, with one or two of them."""
    shown = ", ".join(f"'{text}'" for text in examples[:2])
    return f"쪽마다 반복되는 머리말·꼬리말 {lines}줄을 가져오지 않습니다 (예: {shown})"
