"""Read the paragraphs of hwpx sections into pandoc blocks."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

import panflute as pf
from lxml import etree

from mdcast.readers.docx_package import PAGEBREAK_SENTINEL
from mdcast.readers.hwpx import objects
from mdcast.readers.hwpx.marks import accept_deletions, click_here_guide, hyperlink_url, own
from mdcast.readers.hwpx.package import HP, CharStyle, HwpxPackage, ParaStyle
from mdcast.readers.hwpx.tables import read_table
from mdcast.readers.media import SMALL_IMAGE_INCHES, Assets
from mdcast.report import Codes, Report

_PLAIN = CharStyle()
_BODY = ParaStyle()
_MAX_HEADER = 6
_BODY_OUTLINE = 9  # outline levels from 9 on read as body text
_SPLIT = re.compile(r"([ \t\r\n]+)")
_EDGE = (pf.Space, pf.LineBreak)
_SMALL_IMAGE = SMALL_IMAGE_INCHES * 7200  # HWPUNIT


def hp(tag: str) -> str:
    return f"{{{HP}}}{tag}"


_T, _RUN, _P, _TBL = hp("t"), hp("run"), hp("p"), hp("tbl")
_SPACE_MARKS = (hp("tab"), hp("nbSpace"), hp("fwSpace"))
_LINE_BREAK = hp("lineBreak")
_CTRL, _SUB, _EQUATION, _SCRIPT = hp("ctrl"), hp("subList"), hp("equation"), hp("script")
_NOTES = (hp("footNote"), hp("endNote"))
_FIELD_BEGIN, _FIELD_END = hp("fieldBegin"), hp("fieldEnd")
# paragraphs under these are not body text: page headers and footers, memos (in a MEMO field or
# a memo group), anything else a field carries
_NOT_BODY = (hp("header"), hp("footer"), hp("memo"), hp("memogroup"), _FIELD_BEGIN)
# what IMPORT_HEADER_SKIPPED reports (with MEMO fields): page headers and footers, memos, tracked changes
_SKIPPED = (
    hp("header"),
    hp("footer"),
    hp("memo"),
    hp("memogroup"),
    hp("insertBegin"),
    hp("deleteBegin"),
)
_SKIPPED_MESSAGE = "머리말·꼬리말·메모는 가져오지 않습니다"


def _in_body(p: etree._Element) -> bool:
    return not any(a.tag in _NOT_BODY for a in p.iterancestors())


def _own_texts(p: etree._Element) -> list[str]:
    """The paragraph's own ``hp:t`` text, leaving out paragraphs nested in its tables or notes.

    The text is split where the reader puts something that is not in it: a table (a block before
    and after it), an equation (its script as code), a click-here field (its guide text when
    it is empty) and a drawing object (a picture's alt text, a shape's text as blocks).
    """
    pieces: list[list[str]] = [[]]
    for e in own(p, _T, _TBL, _EQUATION, _FIELD_BEGIN, *objects.OBJECTS, objects.DRAW_TEXT):
        if e.tag == _T:
            pieces[-1].append("".join(e.itertext()))
        elif e.tag != _FIELD_BEGIN or e.get("type") == "CLICK_HERE":
            pieces.append([])
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


def _edges(inlines: list[pf.Inline]) -> tuple[list[pf.Inline], list[pf.Inline], list[pf.Inline]]:
    """Leading spaces and breaks, the rest, trailing spaces and breaks."""
    start, end = 0, len(inlines)
    while start < end and isinstance(inlines[start], _EDGE):
        start += 1
    while end > start and isinstance(inlines[end - 1], _EDGE):
        end -= 1
    return inlines[:start], inlines[start:end], inlines[end:]


def _styled(inlines: list[pf.Inline], style: CharStyle) -> list[pf.Inline]:
    """Wrap in the run's formatting; edge spaces and breaks stay outside (``**a **`` is not bold MD)."""
    if style == _PLAIN:
        return inlines
    lead, core, trail = _edges(inlines)
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


def _is_sentinel(block: pf.Block) -> bool:
    return isinstance(block, pf.Para) and pf.stringify(block, newlines=False) == PAGEBREAK_SENTINEL


def _is_text(block: pf.Block) -> bool:
    """A Para or Plain the MD writer keeps as text (the page-break mark becomes a raw block)."""
    return isinstance(block, (pf.Para, pf.Plain)) and not _is_sentinel(block)


class _Frame:
    """An open list while its paragraphs are grouped: its level and each item's blocks."""

    def __init__(self, level: int, start: int) -> None:
        self.level = level
        self.start = start
        self.items: list[list[pf.Block]] = []

    def to_list(self, kind: str) -> pf.Block:
        # pandoc writes a list tight only when every item starts with text and has no second block
        # besides its nested lists; tight items read back as Plain. Anything else (an item that is
        # a table or a page-break mark, or holds one after its text) makes it write the whole list
        # loose, which reads back as Para (ruling R6a)
        loose = any(
            not _is_text(item[0]) or sum(not isinstance(b, _LISTS) for b in item) > 1
            for item in self.items
        )
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
    on across. All of a paragraph's blocks go into its item, except a page break on a list's first
    paragraph, which goes before the list. A numbered list starts at its numbering's first number
    (``starts``); the number shape is dropped.
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
            continue
        if not run and _is_sentinel(blocks[0]):
            out.append(blocks[0])
            blocks = blocks[1:]
        if blocks:
            run.append((style.level, blocks))
    if run:
        out.append(_nest(key[0], starts.get(key[1] or "", 1), run))
    return out


class _Line:
    """The inlines of a paragraph since the last block object, grouped by character style."""

    def __init__(self) -> None:
        self._groups: list[tuple[CharStyle, list[str | pf.Inline]]] = []
        self.chars = 0  # characters of text added, spaces not counted

    def add(self, style: CharStyle, piece: str | pf.Inline) -> None:
        if isinstance(piece, str):
            self.chars += len(piece.strip())
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

    def inlines(self) -> list[pf.Inline]:
        """The inlines so far, formatting applied, spaces at the ends kept."""
        out: list[pf.Inline] = []
        for style, pieces in self._groups:
            out.extend(_styled(_tokens(pieces), style))
        return out

    def take(self) -> list[pf.Inline]:
        out = _tidy(self.inlines())
        self._groups = []
        return out


class _Fields:
    """The fields open in a paragraph, and the line their text goes on.

    Only a ``fieldBegin`` whose ``fieldEnd`` (``beginIDRef``) comes after it in the paragraph
    opens a field; any other begin or end is passed over, so its text reads as if it were not
    there. A hyperlink's text collects on a line of its own and goes back as a Link; an empty
    click-here field gets its guide text; every other field (a memo's anchor included) keeps
    just its text.
    """

    def __init__(self, ctrls: list[etree._Element], line: _Line) -> None:
        self._base = line
        self._open: list[tuple[etree._Element, _Line, int]] = []  # (begin, its line, chars then)
        self._balanced: set[etree._Element] = set()
        ends: set[str | None] = set()
        for ctrl in reversed(ctrls):
            if ctrl.tag == _FIELD_END:
                ends.add(ctrl.get("beginIDRef"))
            elif ctrl.tag == _FIELD_BEGIN and ctrl.get("id") in ends:
                self._balanced.add(ctrl)

    @property
    def line(self) -> _Line:
        return self._open[-1][1] if self._open else self._base

    def begin(self, field: etree._Element) -> None:
        if field in self._balanced:
            line = _Line() if field.get("type") == "HYPERLINK" else self.line
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


class BodyReader:
    """Turns the paragraphs of every section into blocks, in document order."""

    def __init__(self, pkg: HwpxPackage, report: Report, assets: Assets | None) -> None:
        self.pkg = pkg
        self.report = report
        self.assets = assets  # None: pictures link to their BinData file name, nothing is written
        self._small: dict[int, pf.Image] = {}  # pictures that may have been text (IMPORT_IMAGE_TEXT)
        # tracked changes read as accepted: deleted text leaves the XML before anything reads it
        # (paired across the paragraphs of a section, and of each cell, note or caption)
        for section in pkg.sections:
            if next(section.iter(hp("deleteBegin")), None) is not None:
                for paragraphs in (section, *section.iter(_SUB)):
                    accept_deletions(list(paragraphs.iterchildren(_P)))
        # every paragraph's own text (split around its tables), nested ones (table cells, notes) as
        # their own entries, page headers, footers and memos left out; it is taken from the XML,
        # not from what this reader makes, so the coverage check sees what it drops
        self.source_text: list[str] = [
            text
            for section in pkg.sections
            for p in section.iter(_P)
            if _in_body(p)
            for text in _own_texts(p)
            if text
        ]
        self.has_skipped = any(
            e.tag != _FIELD_BEGIN or e.get("type") == "MEMO"
            for section in pkg.sections
            for e in section.iter(*_SKIPPED, _FIELD_BEGIN)
        )

    def report_skipped(self) -> None:
        """One info when the document has page headers or footers, memos or tracked changes."""
        if self.has_skipped:
            self.report.info(Codes.IMPORT_HEADER_SKIPPED, _SKIPPED_MESSAGE)

    def blocks(self) -> list[pf.Block]:
        return self.paragraphs(
            (p for section in self.pkg.sections for p in section.iterchildren(_P)), in_cell=False
        )

    def sub_list(self, sub: etree._Element | None) -> list[pf.Block]:
        """The blocks of an ``hp:subList`` (a table cell or caption); none when it is missing."""
        if sub is None:
            return []
        return _cell_paragraphs(self.paragraphs(sub.iterchildren(_P), in_cell=True))

    def paragraphs(
        self, ps: Iterable[etree._Element], *, in_cell: bool, nested: bool = False
    ) -> list[pf.Block]:
        """Sibling paragraphs (a section's, a cell's or a note's) → their blocks, in order, lists grouped."""
        return group_lists(
            ((self._style(p), self.paragraph(p, in_cell=in_cell, nested=nested)) for p in ps),
            self.pkg.styles.numbering_start,
        )

    def _style(self, p: etree._Element) -> ParaStyle:
        return self.pkg.styles.paras.get(p.get("paraPrIDRef") or "", _BODY)

    def paragraph(
        self, p: etree._Element, *, in_cell: bool, nested: bool = False
    ) -> list[pf.Block]:
        """One ``hp:p`` → its blocks: a page-break sentinel, then text split around block objects.

        ``in_cell`` paragraphs are Plain, ``nested`` ones (in a note) Para. Only a top-level
        paragraph becomes a heading or leaves a page-break mark: neither belongs in a note.
        """
        style = self._style(p)
        top = not (in_cell or nested)
        blocks: list[pf.Block] = []
        if top and p.get("pageBreak") == "1":
            blocks.append(pf.Para(pf.Str(PAGEBREAK_SENTINEL)))
        line = _Line()
        runs = list(p.iterchildren(_RUN))
        fields = _Fields(
            [c for run in runs for ctrl in run.iterchildren(_CTRL) for c in ctrl], line
        )

        def flush() -> None:
            fields.close_all()
            inlines = line.take()
            if len(inlines) == 1 and isinstance(inlines[0], pf.Code):  # an equation on its own
                blocks.append(pf.CodeBlock(inlines[0].text))
            elif inlines:
                blocks.append(self._block(inlines, style, in_cell, top))

        for run in runs:
            char = self.pkg.styles.chars.get(run.get("charPrIDRef") or "", _PLAIN)
            for child in run:
                if child.tag == _T:
                    fields.line.text(child, char)
                elif child.tag == _EQUATION:
                    code = self._equation(child)
                    if code is not None:
                        fields.line.add(_PLAIN, code)
                elif child.tag == _CTRL:
                    for ctrl in child:
                        if ctrl.tag in _NOTES:
                            note = self._note(ctrl)
                            if note is not None:
                                fields.line.add(_PLAIN, note)
                        elif ctrl.tag == _FIELD_BEGIN:
                            fields.begin(ctrl)
                        elif ctrl.tag == _FIELD_END:
                            fields.end(ctrl)
                        # page headers and footers, page numbers, bookmarks: not read
                elif child.tag == _TBL:
                    flush()
                    table = read_table(child, self)
                    if table.colspec:
                        blocks.append(table)
                    else:  # no cells: an empty <table> would only be noise; keep a caption's text
                        blocks.extend(table.caption.content)
                elif objects.is_object(child):
                    self._object(child, in_cell, fields, flush, blocks)
        flush()
        return blocks

    def is_small(self, image: pf.Image) -> bool:
        """A picture with no description of at most ``SMALL_IMAGE_INCHES`` high: it may have been text."""
        return id(image) in self._small

    def _object(
        self,
        obj: etree._Element,
        in_cell: bool,
        fields: _Fields,
        flush: Callable[[], None],
        blocks: list[pf.Block],
    ) -> None:
        """A drawing object where it stands: a picture inline, anything else as blocks.

        A shape's text (a text box), each object of a group in order, the description of an
        object that has no text, and any object's caption go in as blocks: the paragraph is
        broken before them. They read like the paragraphs around them (a cell's are Plain and R3
        applies to the cell as a whole), but never become a heading or leave a page-break mark.
        """
        if obj.tag == objects.PIC:
            for piece in self._picture(obj):
                fields.line.add(_PLAIN, piece)
        elif obj.tag == objects.CONTAINER:
            flush()
            for child in obj:
                if objects.is_object(child):
                    self._object(child, in_cell, fields, flush, blocks)
            flush()
        elif obj.tag in objects.NO_TEXT:
            self.report.warn(Codes.IMPORT_OBJECT_SKIPPED, "글로 옮길 수 없는 개체를 건너뜁니다")
            text = objects.human_comment(obj)
            if text:
                flush()
                blocks.append(self._block(_tokens([text]), _BODY, in_cell, top=False))
        else:
            flush()
            blocks.extend(self._drawn(objects.sub_list(obj, objects.DRAW_TEXT), in_cell))
        caption = self._drawn(objects.sub_list(obj, objects.CAPTION), in_cell)
        if caption:
            flush()
            blocks.extend(caption)

    def _drawn(self, sub: etree._Element | None, in_cell: bool) -> list[pf.Block]:
        """The paragraphs of a shape's text or an object's caption."""
        if sub is None:
            return []
        return self.paragraphs(sub.iterchildren(_P), in_cell=in_cell, nested=True)

    def _picture(self, pic: etree._Element) -> list[str | pf.Inline]:
        """An Image of the picture's file, its alt text the human description or ``그림``.

        A picture whose file is not in the package leaves its human description as text, with a
        warn ``IMPORT_OBJECT_SKIPPED``.
        """
        alt = objects.human_comment(pic)
        ref = objects.picture_ref(pic)
        if ref not in self.pkg.bin_data:
            self.report.warn(
                Codes.IMPORT_OBJECT_SKIPPED, "그림 파일을 찾을 수 없어 그림을 건너뜁니다", name=ref
            )
            return [alt] if alt else []
        name, blob = self.pkg.bin_data[ref]
        url = self.assets.add(name, blob) if self.assets is not None else name
        image = pf.Image(*(_tokens([alt]) if alt else [pf.Str("그림")]), url=url)
        height = objects.height(pic)
        if not alt and height is not None and height <= _SMALL_IMAGE:
            self._small[id(image)] = image
        return [image]

    def _note(self, note: etree._Element) -> pf.Note | None:
        """A footnote or endnote; its paragraphs are Para (R1). None when it has no text."""
        sub = note.find(_SUB)
        if sub is None:
            return None
        blocks = self.paragraphs(sub.iterchildren(_P), in_cell=False, nested=True)
        return pf.Note(*blocks) if blocks else None

    def _equation(self, equation: etree._Element) -> pf.Code | None:
        """A Hangul equation's script as code; None when it has none."""
        script = equation.find(_SCRIPT)
        text = "".join(script.itertext()).strip() if script is not None else ""
        if not text:
            return None
        self.report.warn(Codes.HWPX_EQUATION_PRESERVED, "한글 수식을 코드로 남깁니다")
        return pf.Code(text)

    @staticmethod
    def _block(inlines: list[pf.Inline], style: ParaStyle, in_cell: bool, top: bool) -> pf.Block:
        if in_cell:
            return pf.Plain(*inlines)
        if top and style.kind == "OUTLINE" and style.level < _BODY_OUTLINE:
            return pf.Header(*inlines, level=min(style.level + 1, _MAX_HEADER))
        return pf.Para(*inlines)
