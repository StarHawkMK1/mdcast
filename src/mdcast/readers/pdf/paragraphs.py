"""Group text lines into paragraphs and turn a paragraph's runs into inlines (spec §4.2, §4.3)."""

from __future__ import annotations

import itertools
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import panflute as pf

from mdcast.filters.importing.markers import heading_shape, list_marker
from mdcast.readers.pdf.model import Line

GAP_RATIO = 1.3  # a line whose top is more than this many usual line gaps below the last starts a paragraph
SHORT_LINE = 2.0  # a line ending more than this many body sizes short of the body's right edge ends a paragraph
SAME_SIZE = 0.5  # pt. Lines whose sizes differ by more are in different paragraphs

_DEFAULT_SIZE = 11.0
_DEFAULT_GAP_RATIO = 1.2  # line gap when no two lines can be measured: body size × this


@dataclass(frozen=True)
class Layout:
    body_size: float  # the size most characters outside tables have; 11.0 without lines
    line_gap: float  # median top-to-top distance of neighbouring same-size lines on a page
    right: float  # 95th percentile of body lines' x1; 0 without lines


def measure_layout(lines: Sequence[Line]) -> Layout:
    """The document's body size, usual line gap and right edge, measured over ``lines`` in order."""
    chars: Counter[float] = Counter()
    for ln in lines:
        chars[ln.size] += len(ln.text.replace(" ", ""))
    body_size = chars.most_common(1)[0][0] if chars else _DEFAULT_SIZE
    gaps = [
        nxt.box.top - prev.box.top
        for prev, nxt in itertools.pairwise(lines)
        if prev.page == nxt.page and abs(prev.size - nxt.size) <= SAME_SIZE and nxt.box.top > prev.box.top
    ]
    line_gap = statistics.median(gaps) if gaps else body_size * _DEFAULT_GAP_RATIO
    ends = [ln.box.x1 for ln in lines if abs(ln.size - body_size) <= SAME_SIZE]
    return Layout(body_size, line_gap, _percentile(ends, 0.95) if ends else 0.0)


def _percentile(values: list[float], q: float) -> float:
    """Linear interpolation between the closest ranks."""
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def starts_block(text: str) -> bool:
    """A line that opens with a list marker, a heading number or ``※`` — the shapes import filters read."""
    return list_marker(text) is not None or heading_shape(text) is not None or text.startswith("※")


SOFT_HYPHEN = "\u00ad"  # typst (and others) write a hyphenation break into the text layer as this


def join_text(prev: str, nxt: str) -> str:
    """Two lines of one paragraph: an English word broken after ``-`` keeps it and joins up, else one space.

    A word hyphenated at the line end (soft hyphen) joins up too; the soft hyphen stays, so no
    character is lost and it is invisible in the MD.
    """
    return prev + nxt if _glued(prev, nxt) else f"{prev} {nxt}"


def _glued(prev: str, nxt: str) -> bool:
    if prev.endswith(SOFT_HYPHEN):
        return bool(nxt)
    return len(prev) >= 2 and prev[-1] == "-" and _ascii_letter(prev[-2]) and bool(nxt) and _ascii_letter(nxt[0])


def _ascii_letter(ch: str) -> bool:
    return ch.isascii() and ch.isalpha()


def group_paragraphs(lines: Sequence[Line], layout: Layout) -> list[list[Line]]:
    """``lines`` in order, cut into paragraphs."""
    paragraphs: list[list[Line]] = []
    for ln in lines:
        if paragraphs and not _breaks(paragraphs[-1][-1], ln, layout):
            paragraphs[-1].append(ln)
        else:
            paragraphs.append([ln])
    return paragraphs


def _breaks(prev: Line, ln: Line, layout: Layout) -> bool:
    """``ln`` starts a new paragraph after ``prev``; across a page the vertical gap does not count."""
    if prev.page == ln.page and ln.box.top - prev.box.top > GAP_RATIO * layout.line_gap:
        return True
    return (
        starts_block(ln.text)
        or abs(ln.size - prev.size) > SAME_SIZE
        or ln.bold != prev.bold
        or prev.box.x1 < layout.right - SHORT_LINE * layout.body_size
    )


_SPACE = None  # a word gap in the token list below; its boldness is settled by its neighbours
_Token = list[Any] | None  # [text, bold] for a word, _SPACE for a gap


def to_inlines(lines: Sequence[Line]) -> list[pf.Inline]:
    """A paragraph's inlines: bold words in ``pf.Strong``, word gaps as ``pf.Space``.

    Lines join as :func:`join_text` does. A space is inside a Strong only between two bold
    words, so a Strong never starts or ends with one.
    """
    tokens: list[_Token] = []
    for index, ln in enumerate(lines):
        if index and not _glued(lines[index - 1].text, ln.text):
            tokens.append(_SPACE)
        for run in ln.runs:
            for part_index, part in enumerate(run.text.split(" ")):
                if part_index:
                    tokens.append(_SPACE)
                if not part:
                    continue
                last = tokens[-1] if tokens else _SPACE
                if last is not _SPACE and last[1] == run.bold:
                    last[0] += part
                else:
                    tokens.append([part, run.bold])
    words = _tidy(tokens)
    out: list[pf.Inline] = []
    group: list[pf.Inline] = []
    group_bold = False
    for index, token in enumerate(words):
        if token is _SPACE:
            bold = words[index - 1][1] and words[index + 1][1]
            inline: pf.Inline = pf.Space()
        else:
            bold = token[1]
            inline = pf.Str(token[0])
        if group and bold != group_bold:
            out += [pf.Strong(*group)] if group_bold else group
            group = []
        group.append(inline)
        group_bold = bold
    out += [pf.Strong(*group)] if group_bold else group
    return out


def _tidy(tokens: list[_Token]) -> list[_Token]:
    """No gap at either end or twice in a row."""
    out: list[_Token] = []
    for token in tokens:
        if token is _SPACE and (not out or out[-1] is _SPACE):
            continue
        out.append(token)
    if out and out[-1] is _SPACE:
        out.pop()
    return out
