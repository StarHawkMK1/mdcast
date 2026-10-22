"""The inlines of an hwpx paragraph: text runs, character styles, hints and fields."""

from __future__ import annotations

import re
from dataclasses import dataclass

import panflute as pf
from lxml import etree

from mdcast.readers.hwpx import objects
from mdcast.readers.hwpx.marks import click_here_guide, hyperlink_url, own
from mdcast.readers.hwpx.package import HP, CharStyle
from mdcast.readers.imported import HINT_CLASS

_PLAIN = CharStyle()
_SPLIT = re.compile(r"([ \t\r\n]+)")
_EDGE = (pf.Space, pf.LineBreak)


def hp(tag: str) -> str:
    return f"{{{HP}}}{tag}"


_T, _TBL, _EQUATION = hp("t"), hp("tbl"), hp("equation")
_SPACE_MARKS = (hp("tab"), hp("nbSpace"), hp("fwSpace"))
_LINE_BREAK = hp("lineBreak")
_FIELD_BEGIN, _FIELD_END = hp("fieldBegin"), hp("fieldEnd")


def _t_text(t: etree._Element) -> str:
    """An ``hp:t``'s text as typed: a tab or space mark is a space, a line break a newline (as in §4.2)."""
    parts = [t.text or ""]
    for child in t:
        if child.tag in _SPACE_MARKS:
            parts.append(" ")
        elif child.tag == _LINE_BREAK:
            parts.append("\n")
        else:
            parts.append("".join(child.itertext()))
        parts.append(child.tail or "")
    return "".join(parts)


def own_texts(p: etree._Element) -> list[str]:
    """The paragraph's own ``hp:t`` text, leaving out paragraphs nested in its tables or notes.

    The text is split where the reader puts something that is not in it: a table (a block before
    and after it), an equation (its script as code), a click-here field (its guide text when
    it is empty) and a drawing object (a picture's alt text, a shape's text as blocks).
    """
    pieces: list[list[str]] = [[]]
    for e in own(p, _T, _TBL, _EQUATION, _FIELD_BEGIN, *objects.OBJECTS, objects.DRAW_TEXT):
        if e.tag == _T:
            pieces[-1].append(_t_text(e))
        elif e.tag != _FIELD_BEGIN or e.get("type") == "CLICK_HERE":
            pieces.append([])
    return ["".join(piece) for piece in pieces]


def tokens(pieces: list[str | pf.Inline]) -> list[pf.Inline]:
    """Join adjacent text pieces and split them into Str and single Spaces."""
    out: list[pf.Inline] = []
    text: list[str] = []

    def add(inline: pf.Inline) -> None:
        if not (isinstance(inline, pf.Space) and out and isinstance(out[-1], pf.Space)):
            out.append(inline)

    def words() -> None:
        for i, part in enumerate(_SPLIT.split("".join(text))):
            if i % 2:
                add(pf.Space())
            elif part:
                add(pf.Str(part))
        text.clear()

    for piece in pieces:
        if isinstance(piece, str):
            text.append(piece)
        else:
            words()
            add(piece)
    words()
    return out


def _edges(inlines: list[pf.Inline]) -> tuple[list[pf.Inline], list[pf.Inline], list[pf.Inline]]:
    """Leading spaces and breaks, the rest, trailing spaces and breaks."""
    start, end = 0, len(inlines)
    while start < end and isinstance(inlines[start], _EDGE):
        start += 1
    while end > start and isinstance(inlines[end - 1], _EDGE):
        end -= 1
    return inlines[:start], inlines[start:end], inlines[end:]


@dataclass(frozen=True)
class Hint:
    """How the mdcast hwpx writer set a run apart, kept for ``mdcast_doc`` (mdcast documents only).

    The writer uses no named style for code, a block quote or a code block, only the template's
    code font, quote colour and code background (R17); ``mdcast_doc`` matches them against the
    template and takes every hint out again.
    """

    font: str
    color: str
    fill: str




def _hint_span(core: list[pf.Inline], hint: Hint, raw: str) -> pf.Span:
    attributes = {"font": hint.font, "color": hint.color, "fill": hint.fill, "text": raw}
    return pf.Span(*core, classes=[HINT_CLASS], attributes=attributes)


def _raw(pieces: list[str | pf.Inline]) -> str | None:
    """A run group's text as typed (a space mark a space, a break a newline); None if it holds anything else."""
    out = []
    for piece in pieces:
        if isinstance(piece, str):
            out.append(piece)
        elif isinstance(piece, pf.Space):
            out.append(" ")
        elif isinstance(piece, pf.LineBreak):
            out.append("\n")
        else:
            return None
    return "".join(out)


def _styled(
    inlines: list[pf.Inline], style: CharStyle, hint: Hint | None = None, raw: str = ""
) -> list[pf.Inline]:
    """Wrap in the run's formatting; edge spaces and breaks stay outside (``**a **`` is not bold MD).

    A hint goes innermost, so code that was bold reads back as bold code.
    """
    if style == _PLAIN and hint is None:
        return inlines
    lead, core, trail = _edges(inlines)
    if not core:
        return inlines
    if hint is not None:
        core = [_hint_span(core, hint, raw)]
    if style.superscript:
        core = [pf.Superscript(*core)]
    elif style.subscript:
        core = [pf.Subscript(*core)]
    if style.strike:
        core = [pf.Strikeout(*core)]
    if style.italic:
        core = [pf.Emph(*core)]
    if style.bold:
        core = [pf.Strong(*core)]
    return lead + core + trail


def _tidy(inlines: list[pf.Inline]) -> list[pf.Inline]:
    """One Space between words, none at the ends; no break at the ends either."""
    out: list[pf.Inline] = []
    for inline in inlines:
        if isinstance(inline, pf.Space) and (not out or isinstance(out[-1], pf.Space)):
            continue
        out.append(inline)
    while out and isinstance(out[0], _EDGE):
        out.pop(0)
    while out and isinstance(out[-1], _EDGE):
        out.pop()
    return out


class Line:
    """The inlines of a paragraph since the last block object, grouped by character style."""

    def __init__(self) -> None:
        self._groups: list[tuple[CharStyle, Hint | None, list[str | pf.Inline]]] = []
        self.chars = 0  # characters of text added, spaces not counted

    def add(self, style: CharStyle, piece: str | pf.Inline, hint: Hint | None = None) -> None:
        if isinstance(piece, str):
            self.chars += len(piece.strip())
        if self._groups and self._groups[-1][:2] == (style, hint):
            self._groups[-1][2].append(piece)
        else:
            self._groups.append((style, hint, [piece]))

    def text(self, t: etree._Element, style: CharStyle, hint: Hint | None = None) -> None:
        """An ``hp:t``: its text, with tab/space and line-break marks between the pieces."""
        if t.text:
            self.add(style, t.text, hint)
        for child in t:
            if child.tag in _SPACE_MARKS:
                self.add(style, pf.Space(), hint)
            elif child.tag == _LINE_BREAK:
                self.add(style, pf.LineBreak(), hint)
            if child.tail:  # also after marks this reader does not know
                self.add(style, child.tail, hint)

    def inlines(self) -> list[pf.Inline]:
        """The inlines so far, formatting applied, spaces at the ends kept."""
        out: list[pf.Inline] = []
        for style, hint, pieces in self._groups:
            raw = _raw(pieces) if hint is not None else None
            out.extend(_styled(tokens(pieces), style, hint if raw is not None else None, raw or ""))
        return out

    def take(self) -> list[pf.Inline]:
        out = _tidy(self.inlines())
        self._groups = []
        return out


class Fields:
    """The fields open in a paragraph, and the line their text goes on.

    Only a ``fieldBegin`` whose ``fieldEnd`` (``beginIDRef``) comes after it in the paragraph
    opens a field; any other begin or end is passed over, so its text reads as if it were not
    there. A hyperlink's text collects on a line of its own and goes back as a Link; an empty
    click-here field gets its guide text; every other field (a memo's anchor included) keeps
    just its text.
    """

    def __init__(self, ctrls: list[etree._Element], line: Line) -> None:
        self._base = line
        self._open: list[tuple[etree._Element, Line, int]] = []  # (begin, its line, chars then)
        self._balanced: set[etree._Element] = set()
        ends: set[str | None] = set()
        for ctrl in reversed(ctrls):
            if ctrl.tag == _FIELD_END:
                ends.add(ctrl.get("beginIDRef"))
            elif ctrl.tag == _FIELD_BEGIN and ctrl.get("id") in ends:
                self._balanced.add(ctrl)

    @property
    def line(self) -> Line:
        return self._open[-1][1] if self._open else self._base

    def begin(self, field: etree._Element) -> None:
        if field in self._balanced:
            line = Line() if field.get("type") == "HYPERLINK" else self.line
            self._open.append((field, line, line.chars))

    def end(self, end: etree._Element) -> None:
        ref = end.get("beginIDRef")
        if all(field.get("id") != ref for field, _, _ in self._open):
            return
        while self._open:  # fields opened inside this one and not closed yet end with it
            done = self._open[-1][0].get("id") == ref
            self._close()
            if done:
                return

    def close_all(self) -> None:
        """End every open field where the text stops (at a block object, or the paragraph's end)."""
        while self._open:
            self._close()

    def _close(self) -> None:
        field, line, chars = self._open.pop()
        kind = field.get("type")
        if kind == "HYPERLINK":
            lead, core, trail = _edges(line.inlines())
            url = hyperlink_url(field)
            for inline in lead + ([pf.Link(*core, url=url)] if url and core else core) + trail:
                self.line.add(_PLAIN, inline)
        elif kind == "CLICK_HERE" and line.chars == chars:
            guide = click_here_guide(field)
            if guide:
                line.add(_PLAIN, guide)
