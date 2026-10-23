"""Headings from font size (spec §4.3): short paragraphs set clearly larger than the body.

A paragraph that opens with a heading number (``1.``, ``가.``, ``Ⅰ.`` …) or a ``□``·``■`` needs
only to be set a size above the body (D14): section titles a point over the body are common.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping, Sequence

from mdcast.filters.importing.markers import heading_shape
from mdcast.readers.pdf.model import Line
from mdcast.readers.pdf.paragraphs import join_text

HEADING_RATIO = 1.15  # a heading's first line is at least this many body sizes
MAX_HEADING_LINES = 2

_SAME_LEVEL = 0.5  # pt. Sizes this close to a level's largest share the level
_MAX_LEVEL = 6
_MAX_NUMBERED = 60  # characters, as the common heading inference (filters/importing/headings.py)
_HEADING_BULLETS = ("□ ", "■ ")


def _candidate(paragraph: Sequence[Line], body_size: float) -> bool:
    """Short, large (or numbered and a size above the body) and not a sentence."""
    if not paragraph or len(paragraph) > MAX_HEADING_LINES:
        return False
    size = paragraph[0].size
    if size - body_size <= _SAME_LEVEL:
        return False
    text = functools.reduce(join_text, (ln.text for ln in paragraph)).strip()
    if text.endswith("."):
        return False
    return size >= body_size * HEADING_RATIO or _numbered(text)


def _numbered(text: str) -> bool:
    return len(text) <= _MAX_NUMBERED and (heading_shape(text) is not None or text.startswith(_HEADING_BULLETS))


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
