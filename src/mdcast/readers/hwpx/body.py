"""Read the paragraphs of hwpx sections into pandoc blocks."""

from __future__ import annotations

import re

import panflute as pf
from lxml import etree

from mdcast.readers.docx_package import PAGEBREAK_SENTINEL
from mdcast.readers.hwpx.package import HP, CharStyle, HwpxPackage, ParaStyle
from mdcast.report import Report

_PLAIN = CharStyle()
_BODY = ParaStyle()
_MAX_HEADER = 6
_BODY_OUTLINE = 9  # outline levels from 9 on read as body text
_SPLIT = re.compile(r"([ \t\r\n]+)")
_EDGE = (pf.Space, pf.LineBreak)


def hp(tag: str) -> str:
    return f"{{{HP}}}{tag}"


_T, _RUN, _P = hp("t"), hp("run"), hp("p")
_SPACE_MARKS = (hp("tab"), hp("nbSpace"), hp("fwSpace"))
_LINE_BREAK = hp("lineBreak")


def _own_text(p: etree._Element) -> str:
    """The paragraph's own ``hp:t`` text, leaving out paragraphs nested in its tables or notes."""
    return "".join(
        "".join(t.itertext()) for t in p.iter(_T) if next(t.iterancestors(_P), None) is p
    )


def _tokens(pieces: list[str | pf.Inline]) -> list[pf.Inline]:
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


def _styled(inlines: list[pf.Inline], style: CharStyle) -> list[pf.Inline]:
    """Wrap in the run's formatting; edge spaces and breaks stay outside (``**a **`` is not bold MD)."""
    if style == _PLAIN:
        return inlines
    start, end = 0, len(inlines)
    while start < end and isinstance(inlines[start], _EDGE):
        start += 1
    while end > start and isinstance(inlines[end - 1], _EDGE):
        end -= 1
    core = inlines[start:end]
    if not core:
        return inlines
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
    return inlines[:start] + core + inlines[end:]


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


class _Line:
    """The inlines of a paragraph since the last block object, grouped by character style."""

    def __init__(self) -> None:
        self._groups: list[tuple[CharStyle, list[str | pf.Inline]]] = []

    def add(self, style: CharStyle, piece: str | pf.Inline) -> None:
        if self._groups and self._groups[-1][0] == style:
            self._groups[-1][1].append(piece)
        else:
            self._groups.append((style, [piece]))

    def text(self, t: etree._Element, style: CharStyle) -> None:
        """An ``hp:t``: its text, with tab/space and line-break marks between the pieces."""
        if t.text:
            self.add(style, t.text)
        for child in t:
            if child.tag in _SPACE_MARKS:
                self.add(style, pf.Space())
            elif child.tag == _LINE_BREAK:
                self.add(style, pf.LineBreak())
            if child.tail:  # also after marks this reader does not know
                self.add(style, child.tail)

    def take(self) -> list[pf.Inline]:
        groups, self._groups = self._groups, []
        out: list[pf.Inline] = []
        for style, pieces in groups:
            out.extend(_styled(_tokens(pieces), style))
        return _tidy(out)


class BodyReader:
    """Turns the paragraphs of every section into blocks, in document order."""

    def __init__(self, pkg: HwpxPackage, report: Report, assets: object | None) -> None:
        self.pkg = pkg
        self.report = report
        self.assets = assets  # Task 6 gives this its type; None until pictures are read
        # every paragraph's own text, nested ones (table cells, notes) as their own entries; it is
        # taken from the XML, not from what this reader makes, so the coverage check sees what it drops
        self.source_text: list[str] = [
            text for section in pkg.sections for p in section.iter(_P) if (text := _own_text(p))
        ]

    def blocks(self) -> list[pf.Block]:
        out: list[pf.Block] = []
        for section in self.pkg.sections:
            for p in section.iterchildren(_P):
                out.extend(self.paragraph(p, in_cell=False))
        return out

    def paragraph(self, p: etree._Element, *, in_cell: bool) -> list[pf.Block]:
        """One ``hp:p`` → its blocks: a page-break sentinel, then text split around block objects."""
        style = self.pkg.styles.paras.get(p.get("paraPrIDRef") or "", _BODY)
        blocks: list[pf.Block] = []
        if not in_cell and p.get("pageBreak") == "1":
            blocks.append(pf.Para(pf.Str(PAGEBREAK_SENTINEL)))
        line = _Line()

        def flush() -> None:
            inlines = line.take()
            if inlines:
                blocks.append(self._block(inlines, style, in_cell))

        for run in p.iterchildren(_RUN):
            char = self.pkg.styles.chars.get(run.get("charPrIDRef") or "", _PLAIN)
            for child in run:
                if child.tag == _T:
                    line.text(child, char)
                # a block object (table, text box) calls flush(), then adds its own blocks
        flush()
        return blocks

    @staticmethod
    def _block(inlines: list[pf.Inline], style: ParaStyle, in_cell: bool) -> pf.Block:
        if in_cell:
            return pf.Plain(*inlines)
        if style.kind == "OUTLINE" and style.level < _BODY_OUTLINE:
            return pf.Header(*inlines, level=min(style.level + 1, _MAX_HEADER))
        return pf.Para(*inlines)
