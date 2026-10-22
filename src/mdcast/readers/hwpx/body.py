"""Read the paragraphs of hwpx sections into pandoc blocks."""

from __future__ import annotations

from collections.abc import Callable, Iterable

import panflute as pf
from lxml import etree

from mdcast.readers.docx_package import PAGEBREAK_SENTINEL
from mdcast.readers.hwpx import objects
from mdcast.readers.hwpx.inline import Fields, Hint, Line, hp, own_texts, tokens
from mdcast.readers.hwpx.lists import group_lists, is_sentinel
from mdcast.readers.hwpx.marks import accept_deletions
from mdcast.readers.hwpx.package import CharStyle, HwpxPackage, ParaLook, ParaStyle
from mdcast.readers.hwpx.tables import read_table
from mdcast.readers.media import SMALL_IMAGE_INCHES, Assets
from mdcast.readers.symbols import map_symbols
from mdcast.report import Codes, Report

_PLAIN = CharStyle()
_BODY = ParaStyle()
_MAX_HEADER = 6
_BODY_OUTLINE = 9  # outline levels from 9 on read as body text
_SMALL_IMAGE = SMALL_IMAGE_INCHES * 7200  # HWPUNIT
_T, _RUN, _P, _TBL = hp("t"), hp("run"), hp("p"), hp("tbl")
_CTRL, _SUB, _EQUATION, _SCRIPT = hp("ctrl"), hp("subList"), hp("equation"), hp("script")
_NOTES = (hp("footNote"), hp("endNote"))
_FIELD_BEGIN, _FIELD_END = hp("fieldBegin"), hp("fieldEnd")
# paragraphs under these are not body text: page headers and footers, memos (in a MEMO field or
# a memo group), hidden comments, anything else a field carries
_NOT_BODY = (hp("header"), hp("footer"), hp("memo"), hp("memogroup"), hp("hiddenComment"), _FIELD_BEGIN)
# what IMPORT_HEADER_SKIPPED reports (with MEMO fields): page headers and footers, memos, tracked changes
_SKIPPED = (hp("header"), hp("footer"), hp("memo"), hp("memogroup"))
_TRACKED = (hp("insertBegin"), hp("deleteBegin"))
_SKIPPED_MESSAGE = "머리말·꼬리말·메모는 가져오지 않습니다"
_TRACKED_MESSAGE = "변경 추적은 받아들인 상태로 가져옵니다"
_SYMBOLS_MESSAGE = "기호 글꼴 글자 {}개를 보이는 기호로 바꿨습니다"
_SYMBOLS_LEFT = " (바꾸지 못한 글자 {}개는 그대로 둡니다)"
_SYMBOLS_ONLY_LEFT = "기호 글꼴 글자 {}개는 보이는 기호로 바꾸지 못해 그대로 둡니다"


def _in_body(p: etree._Element) -> bool:
    return not any(a.tag in _NOT_BODY for a in p.iterancestors())


def _cell_paragraphs(blocks: list[pf.Block]) -> list[pf.Block]:
    """One paragraph in a cell or caption stays Plain; several become a Para each (R3).

    The MD writer puts Plains side by side with no break between them, so read_md would join
    them into one paragraph; separate Paras come back as written.
    """
    if sum(isinstance(b, pf.Plain) for b in blocks) < 2:
        return blocks
    return [pf.Para(*b.content) if isinstance(b, pf.Plain) else b for b in blocks]


class BodyReader:
    """Turns the paragraphs of every section into blocks, in document order."""

    def __init__(self, pkg: HwpxPackage, report: Report, assets: Assets | None) -> None:
        self.pkg = pkg
        self.report = report
        # an mdcast document: keep the writer's code, quote and rule marks for mdcast_doc (R17);
        # any other hwpx reads as spec §4.2 says (fonts, colours and borders dropped)
        self.hints = bool(pkg.generator)
        self.assets = assets  # None: pictures link to their BinData file name, nothing is written
        self._small: dict[int, pf.Image] = {}  # pictures that may have been text (IMPORT_IMAGE_TEXT)
        self.has_tracked = any(next(section.iter(*_TRACKED), None) is not None for section in pkg.sections)
        # tracked changes read as accepted: deleted text leaves the XML before anything reads it
        # (paired across the paragraphs of a section, and of each cell, note or caption)
        for section in pkg.sections:
            if next(section.iter(hp("deleteBegin")), None) is not None:
                for paragraphs in (section, *section.iter(_SUB)):
                    accept_deletions(list(paragraphs.iterchildren(_P)))
        # symbol-font characters become visible symbols in the XML itself, so the body and the
        # source text below both read the mapped text and coverage is not affected (spec §4.6)
        self.symbols_mapped = self.symbols_left = 0
        for section in pkg.sections:
            for t in section.iter(_T):
                p = next(t.iterancestors(_P), None)
                if p is not None and _in_body(p):
                    self._map_symbols(t)
        # every paragraph's own text (split around its tables), nested ones (table cells, notes) as
        # their own entries, page headers, footers and memos left out; it is taken from the XML,
        # not from what this reader makes, so the coverage check sees what it drops
        self.source_text: list[str] = [
            text
            for section in pkg.sections
            for p in section.iter(_P)
            if _in_body(p)
            for text in own_texts(p)
            if text
        ]
        self.has_skipped = any(
            e.tag != _FIELD_BEGIN or e.get("type") == "MEMO"
            for section in pkg.sections
            for e in section.iter(*_SKIPPED, _FIELD_BEGIN)
        )

    def _map_symbols(self, t: etree._Element) -> None:
        """Map an ``hp:t``'s text: its own, and its marks' text and tails (not ``t``'s own tail)."""
        for e in t.iter():
            for attr in ("text", "tail") if e is not t else ("text",):
                value = getattr(e, attr)
                if value:
                    mapped, count, left = map_symbols(value)
                    if count:
                        setattr(e, attr, mapped)
                    self.symbols_mapped += count
                    self.symbols_left += left

    def report_symbols(self) -> None:
        """One info when the body has symbol-font characters, mapped or left as they are."""
        if self.symbols_mapped:
            message = _SYMBOLS_MESSAGE.format(self.symbols_mapped)
            if self.symbols_left:
                message += _SYMBOLS_LEFT.format(self.symbols_left)
        elif self.symbols_left:
            message = _SYMBOLS_ONLY_LEFT.format(self.symbols_left)
        else:
            return
        self.report.info(Codes.IMPORT_SYMBOL_MAPPED, message)

    def report_skipped(self) -> None:
        """One info when the document has page headers or footers, memos or tracked changes."""
        parts = [_SKIPPED_MESSAGE] if self.has_skipped else []
        if self.has_tracked:
            parts.append(_TRACKED_MESSAGE)
        if parts:
            self.report.info(Codes.IMPORT_HEADER_SKIPPED, ". ".join(parts))

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
            ((self.para_style(p), self.paragraph(p, in_cell=in_cell, nested=nested)) for p in ps),
            self.pkg.styles.numbering_start,
        )

    def para_style(self, p: etree._Element) -> ParaStyle:
        return self.pkg.styles.paras.get(p.get("paraPrIDRef") or "", _BODY)

    def paragraph(
        self, p: etree._Element, *, in_cell: bool, nested: bool = False
    ) -> list[pf.Block]:
        """One ``hp:p`` → its blocks: a page-break sentinel, then text split around block objects.

        ``in_cell`` paragraphs are Plain, ``nested`` ones (in a note) Para. Only a top-level
        paragraph becomes a heading or leaves a page-break mark: neither belongs in a note.
        """
        style = self.para_style(p)
        top = not (in_cell or nested)
        blocks: list[pf.Block] = []
        if top and p.get("pageBreak") == "1":
            blocks.append(pf.Para(pf.Str(PAGEBREAK_SENTINEL)))
        line = Line()
        runs = list(p.iterchildren(_RUN))
        fields = Fields(
            [c for run in runs for ctrl in run.iterchildren(_CTRL) for c in ctrl], line
        )

        def flush() -> None:
            fields.close_all()
            inlines = line.take()
            if len(inlines) == 1 and isinstance(inlines[0], pf.Code):  # an equation on its own
                blocks.append(pf.CodeBlock(inlines[0].text))
            elif inlines:
                blocks.append(self._block(inlines, style, in_cell, top))

        look = self.pkg.styles.para_looks.get(p.get("paraPrIDRef") or "", ParaLook())
        for run in runs:
            char_id = run.get("charPrIDRef") or ""
            char = self.pkg.styles.chars.get(char_id, _PLAIN)
            hint = None
            if self.hints:
                char_look = self.pkg.styles.char_looks.get(char_id)
                if char_look is not None:
                    hint = Hint(char_look.font, char_look.color, look.fill)
            for child in run:
                if child.tag == _T:
                    fields.line.text(child, char, hint)
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
        if self.hints and top and look.rule and all(is_sentinel(b) for b in blocks):
            # the writer's horizontal rule: an empty paragraph with only a bottom border (R17)
            blocks.append(pf.HorizontalRule())
        return blocks

    def is_small(self, image: pf.Image) -> bool:
        """A picture with no description of at most ``SMALL_IMAGE_INCHES`` high: it may have been text."""
        return id(image) in self._small

    def _object(
        self,
        obj: etree._Element,
        in_cell: bool,
        fields: Fields,
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
                blocks.append(self._block(tokens([text]), _BODY, in_cell, top=False))
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
        image = pf.Image(*(tokens([alt]) if alt else [pf.Str("그림")]), url=url)
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
