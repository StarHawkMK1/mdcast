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


_LIST_KINDS = ("NUMBER", "BULLET")
_LISTS = (pf.OrderedList, pf.BulletList)


class _Frame:
    """An open list while its paragraphs are grouped: its level and each item's blocks."""

    def __init__(self, level: int, start: int) -> None:
        self.level = level
        self.start = start
        self.items: list[list[pf.Block]] = []

    def to_list(self, kind: str) -> pf.Block:
        # pandoc writes a list tight (no blank lines) when no item has a second block besides its
        # nested lists, and tight items read back as Plain; an item holding more (a table, a
        # page-break mark) makes it write the whole list loose, which reads back as Para
        loose = any(sum(not isinstance(b, _LISTS) for b in item) > 1 for item in self.items)
        text = pf.Para if loose else pf.Plain
        items = [
            pf.ListItem(
                *(text(*b.content) if isinstance(b, (pf.Para, pf.Plain)) else b for b in item)
            )
            for item in self.items
        ]
        if kind == "NUMBER":
            return pf.OrderedList(*items, start=self.start)
        return pf.BulletList(*items)


def _nest(kind: str, start: int, paras: list[tuple[int, list[pf.Block]]]) -> pf.Block:
    """One list from its paragraphs' (level, blocks): a deeper paragraph opens a list in the item before it.

    A level that skips one (0 → 2) nests one step only, and a later paragraph between the two
    levels joins that nested list; a paragraph shallower than the first one stays in the outer
    list. No paragraph moves or is dropped.
    """
    first = paras[0][0]
    stack = [_Frame(first, start if first == 0 else 1)]

    def close() -> None:
        done = stack.pop()
        stack[-1].items[-1].append(done.to_list(kind))

    for level, blocks in paras:
        while len(stack) > 1 and stack[-1].level > level:
            if stack[-2].level < level:
                stack[-1].level = level
                break
            close()
        if level > stack[-1].level:
            stack.append(_Frame(level, 1))
        elif level < stack[-1].level:  # only the outer list, shallower than where it began
            stack[-1].level = level
        stack[-1].items.append(blocks)
    while len(stack) > 1:
        close()
    return stack[0].to_list(kind)


def group_lists(
    paras: Iterable[tuple[ParaStyle, list[pf.Block]]], starts: dict[str, int]
) -> list[pf.Block]:
    """The blocks of sibling paragraphs, Hancom numbered and bulleted paragraphs grouped into lists.

    Paragraphs of one kind and ``list_id`` that follow each other are one list (spec §4.4); a
    paragraph without blocks is passed over, so an empty line does not split a list Hancom numbers
    on across. All of a paragraph's blocks go into its item. A numbered list starts at its
    numbering's first number (``starts``); the number shape is dropped.
    """
    out: list[pf.Block] = []
    run: list[tuple[int, list[pf.Block]]] = []
    key: tuple[str, str | None] | None = None
    for style, blocks in paras:
        if not blocks:
            continue
        this = (style.kind, style.list_id) if style.kind in _LIST_KINDS else None
        if run and this != key:
            out.append(_nest(key[0], starts.get(key[1] or "", 1), run))
            run = []
        key = this
        if this is None:
            out.extend(blocks)
        else:
            run.append((style.level, blocks))
    if run:
        out.append(_nest(key[0], starts.get(key[1] or "", 1), run))
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
        """A run of sibling paragraphs (a section's or a cell's) → their blocks, in order, lists grouped."""
        return group_lists(
            ((self._style(p), self.paragraph(p, in_cell=in_cell)) for p in ps),
            self.pkg.styles.numbering_start,
        )

    def _style(self, p: etree._Element) -> ParaStyle:
        return self.pkg.styles.paras.get(p.get("paraPrIDRef") or "", _BODY)

    def paragraph(self, p: etree._Element, *, in_cell: bool) -> list[pf.Block]:
        """One ``hp:p`` → its blocks: a page-break sentinel, then text split around block objects."""
        style = self._style(p)
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
