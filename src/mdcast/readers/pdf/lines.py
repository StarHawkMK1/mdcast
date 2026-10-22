"""Group a page's characters (pdfplumber ``page.chars``) into text lines."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from mdcast.readers.pdf.model import Box, Line, Run

X_TOLERANCE = 3.0  # as pdfplumber's default: a wider gap between two characters is a space
Y_TOLERANCE = 3.0  # characters whose tops are this close are on one line

Char = Mapping[str, Any]


def is_bold(fontname: str) -> bool:
    return "bold" in fontname.lower()


def page_lines(page: int, chars: Sequence[Char], skip: Sequence[Box] = ()) -> list[Line]:
    """The lines of ``chars``, top to bottom and left to right at the same height.

    A character whose centre lies in a ``skip`` box is left out. Rotated characters (not
    ``upright``) are kept: they make lines of their own, read down a column.
    """
    kept = [c for c in chars if not any(box.contains(*centre(c)) for box in skip)]
    upright = [c for c in kept if c.get("upright", True)]
    rotated = [c for c in kept if not c.get("upright", True)]
    lines = [_line(page, group, "x0", "x1") for group in _groups(upright, "top", "x0")]
    lines += [_line(page, group, "top", "bottom") for group in _groups(rotated, "x0", "top")]
    return sorted((ln for ln in lines if ln is not None), key=lambda ln: (ln.box.top, ln.box.x0))


def centre(c: Char) -> tuple[float, float]:
    return (c["x0"] + c["x1"]) / 2, (c["top"] + c["bottom"]) / 2


def _groups(chars: list[Char], across: str, along: str) -> list[list[Char]]:
    """Characters whose ``across`` values chain within Y_TOLERANCE, each group ordered by ``along``."""
    groups: list[list[Char]] = []
    last = 0.0
    for c in sorted(chars, key=lambda c: c[across]):
        if groups and c[across] - last <= Y_TOLERANCE:
            groups[-1].append(c)
        else:
            groups.append([c])
        last = c[across]
    return [sorted(group, key=lambda c: c[along]) for group in groups]


def _line(page: int, chars: list[Char], start: str, end: str) -> Line | None:
    """One line of ``chars`` (in reading order), or None when they are all spaces.

    A space char or a gap wider than X_TOLERANCE puts one space between two words; the space is
    bold only between two bold characters, so a bold run never starts or ends with one.
    """
    glyphs: list[Char] = []
    runs: list[list[Any]] = []  # [text, bold]
    space = False
    for c in chars:
        if not c["text"].strip():
            space = True
            continue
        bold = is_bold(c["fontname"])
        if glyphs and (space or c[start] - glyphs[-1][end] > X_TOLERANCE):
            _append(runs, " ", bold and is_bold(glyphs[-1]["fontname"]))
        _append(runs, c["text"], bold)
        glyphs.append(c)
        space = False
    if not glyphs:
        return None
    box = Box(
        min(c["x0"] for c in glyphs),
        min(c["top"] for c in glyphs),
        max(c["x1"] for c in glyphs),
        max(c["bottom"] for c in glyphs),
    )
    size = Counter(round(c["size"], 2) for c in glyphs).most_common(1)[0][0]
    return Line(page, box, size, [Run(text, bold) for text, bold in runs])


def _append(runs: list[list[Any]], text: str, bold: bool) -> None:
    if runs and runs[-1][1] == bold:
        runs[-1][0] += text
    else:
        runs.append([text, bold])
