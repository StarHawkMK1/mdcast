"""Read the paragraphs of hwpx sections into pandoc blocks."""

from __future__ import annotations

import re
from collections.abc import Iterable

import panflute as pf
from lxml import etree

from mdcast.readers.docx_package import PAGEBREAK_SENTINEL
from mdcast.readers.hwpx.package import HP, CharStyle, HwpxPackage, ParaStyle
from mdcast.readers.hwpx.tables import read_table
from mdcast.report import Report

_PLAIN = CharStyle()
_BODY = ParaStyle()
_MAX_HEADER = 6
_BODY_OUTLINE = 9  # outline levels from 9 on read as body text
_SPLIT = re.compile(r"([ \t\r\n]+)")
_EDGE = (pf.Space, pf.LineBreak)


def hp(tag: str) -> str:
    return f"{{{HP}}}{tag}"


_T, _RUN, _P, _TBL = hp("t"), hp("run"), hp("p"), hp("tbl")
_SPACE_MARKS = (hp("tab"), hp("nbSpace"), hp("fwSpace"))
_LINE_BREAK = hp("lineBreak")


def _own_texts(p: etree._Element) -> list[str]:
    """The paragraph's own ``hp:t`` text, leaving out paragraphs nested in its tables or notes.

    A table splits the text in two, as the reader makes a block before and after it.
    """
    pieces: list[list[str]] = [[]]
    for e in p.iter(_T, _TBL):
        if next(e.iterancestors(_P), None) is not p:
            continue
        if e.tag == _TBL:
            pieces.append([])
        else:
            pieces[-1].append("".join(e.itertext()))
    return ["".join(piece) for piece in pieces]


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


def _cell_paragraphs(blocks: list[pf.Block]) -> list[pf.Block]:
    """One paragraph in a cell or caption stays Plain; several become a Para each (R3).

    The MD writer puts Plains side by side with no break between them, so read_md would join
    them into one paragraph; separate Paras come back as written.
    """
    if sum(isinstance(b, pf.Plain) for b in blocks) < 2:
        return blocks
    return [pf.Para(*b.content) if isinstance(b, pf.Plain) else b for b in blocks]


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
        # every paragraph's own text (split around its tables), nested ones (table cells, notes) as
        # their own entries; it is taken from the XML, not from what this reader makes, so the
        # coverage check sees what it drops
        self.source_text: list[str] = [
            text
            for section in pkg.sections
            for p in section.iter(_P)
            for text in _own_texts(p)
            if text
        ]

    def blocks(self) -> list[pf.Block]:
        return self.paragraphs(
            (p for section in self.pkg.sections for p in section.iterchildren(_P)), in_cell=False
        )

    def sub_list(self, sub: etree._Element | None) -> list[pf.Block]:
        """The blocks of an ``hp:subList`` (a table cell or caption); none when it is missing."""
        if sub is None:
            return []
        return _cell_paragraphs(self.paragraphs(sub.iterchildren(_P), in_cell=True))

    def paragraphs(self, ps: Iterable[etree._Element], *, in_cell: bool) -> list[pf.Block]:
        """A run of sibling paragraphs (a section's or a cell's) → their blocks, in order."""
        out: list[pf.Block] = []
        for p in ps:
            out.extend(self.paragraph(p, in_cell=in_cell))
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
                elif child.tag == _TBL:
                    flush()
                    table = read_table(child, self)
                    if table.colspec:
                        blocks.append(table)
                    else:  # no cells: an empty <table> would only be noise; keep a caption's text
                        blocks.extend(table.caption.content)
                # other block objects (text boxes) will do the same: flush(), then their own blocks
        flush()
        return blocks

    @staticmethod
    def _block(inlines: list[pf.Inline], style: ParaStyle, in_cell: bool) -> pf.Block:
        if in_cell:
            return pf.Plain(*inlines)
        if style.kind == "OUTLINE" and style.level < _BODY_OUTLINE:
            return pf.Header(*inlines, level=min(style.level + 1, _MAX_HEADER))
        return pf.Para(*inlines)
