"""Headings from font size (spec §4.3): short paragraphs set clearly larger than the body."""

from __future__ import annotations

import functools
from collections.abc import Mapping, Sequence

from mdcast.readers.pdf.model import Line
from mdcast.readers.pdf.paragraphs import join_text

HEADING_RATIO = 1.15  # a heading's first line is at least this many body sizes
MAX_HEADING_LINES = 2

_SAME_LEVEL = 0.5  # pt. Sizes this close to a level's largest share the level
_MAX_LEVEL = 6


def _candidate(paragraph: Sequence[Line], body_size: float) -> bool:
    """Short, large and not a sentence."""
    if not paragraph or len(paragraph) > MAX_HEADING_LINES or paragraph[0].size < body_size * HEADING_RATIO:
        return False
    text = functools.reduce(join_text, (ln.text for ln in paragraph))
    return not text.strip().endswith(".")


def heading_sizes(paragraphs: Sequence[Sequence[Line]], body_size: float) -> dict[float, int]:
    """The level (1..6) of every first-line size a heading candidate has.

    The largest candidate on the first page that has one is the document title: it and every
    size within 0.5pt of it or larger are level 1, so a bigger divider later on does not push
    the title down. Smaller sizes rank from 2, largest first.
    """
    candidates = [p for p in paragraphs if _candidate(p, body_size)]
    if not candidates:
        return {}
    first_page = min(p[0].page for p in candidates)
    anchor = max(p[0].size for p in candidates if p[0].page == first_page)
    sizes: dict[float, int] = {}
    level = 1
    top = anchor  # the largest size of the current level
    for size in sorted({p[0].size for p in candidates}, reverse=True):
        if size >= anchor - _SAME_LEVEL:
            sizes[size] = 1
            continue
        if level == 1 or top - size > _SAME_LEVEL:
            level += 1
            top = size
        sizes[size] = min(level, _MAX_LEVEL)
    return sizes


def heading_level(paragraph: Sequence[Line], sizes: Mapping[float, int], body_size: float) -> int | None:
    """The level of ``paragraph`` as a heading, or None when it is not one."""
    if not _candidate(paragraph, body_size):
        return None
    return sizes.get(paragraph[0].size)
