"""Pandoc AST → section0.xml paragraphs (spec §5)."""

from __future__ import annotations

import copy
import itertools
import re
from contextlib import contextmanager
from dataclasses import dataclass, replace

import panflute as pf
from lxml import etree

from mdcast.hwpx.header import CharSpec, Header, ParaSpec
from mdcast.hwpx.look import Notices, Settings, TableLook
from mdcast.hwpx.picture import picture_element, picture_size
from mdcast.hwpx.shapes import Shape
from mdcast.hwpx.table import (
    Slot,
    build_grid,
    column_widths,
    slot_fill,
    slot_sides,
    slot_valign,
    text_em,
)
from mdcast.hwpx.units import hwpunit

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
PAGE_BREAK = ("mdcast-hwpx", "pagebreak")  # raw block the pagebreak filter writes for hwpx
LINK_COLOR = "#0000FF"  # Hangul's own link look (appendix A-5)
HYPERLINK_FIELD = "627600491"  # '%hlk'
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f￾￿]")  # not allowed in XML
_GAP_EM = 0.5  # between a list marker and its text, as the docx writer
_MIN_HANGING_MM = 3.0
_MIN_WIDTH_MM = 10.0  # narrowest room offered to a table or picture
# A table floats with its paragraph: Hangul never splits a table treated as a character across
# pages, it pushes it whole to the next page and cuts it there (appendix B-5). PARA keeps list indents.
TABLE_MARGIN = 283  # HWPUNIT (1mm), Hangul's own space above and below a table
_TABLE_POS = {
    "treatAsChar": "0", "affectLSpacing": "0", "flowWithText": "1", "allowOverlap": "0", "holdAnchorAndSO": "0",
    "vertRelTo": "PARA", "horzRelTo": "PARA", "vertAlign": "TOP", "horzAlign": "LEFT", "vertOffset": "0",
    "horzOffset": "0",
}
_ALIGN = {"AlignLeft": "left", "AlignCenter": "center", "AlignRight": "right"}
_DEGRADED = {
    "footnote": "hwpx 는 각주 안·캡션 안에 각주를 넣을 수 없어 문서 끝에 [주 n] 으로 모아 썼습니다",
    "math": "hwpx 수식은 M4 에서 이미지로 지원합니다 — LaTeX 원문을 썼습니다",
}


def hp(tag: str) -> str:
    return f"{{{HP}}}{tag}"


def clean(text: str) -> str:
    """``text`` without characters XML cannot hold (pasted text may carry them)."""
    return _CONTROL.sub("", text)


def append_text(t: etree._Element, text: str) -> None:
    """Add text at the end of an ``hp:t`` that may already hold tab or line-break children."""
    text = clean(text)
    if len(t):
        t[-1].tail = (t[-1].tail or "") + text
    else:
        t.text = (t.text or "") + text


def hanging_mm(markers: list[str], size_pt: float) -> float:
    """Hanging indent holding the widest marker plus a gap (appendix A-15: never narrower)."""
    em = max(text_em(marker) for marker in markers) + _GAP_EM
    return max(em * size_pt * 25.4 / 72, _MIN_HANGING_MM)


def escape_command(url: str) -> str:
    return url.replace("\\", "\\\\").replace(":", "\\:").replace(";", "\\;")


class Paragraph:
    """One ``hp:p`` being built; consecutive text with the same character shape shares a run."""

    def __init__(self, para: str, style: str, char: str, page_break: bool) -> None:
        self.element = etree.Element(
            hp("p"), id="0", paraPrIDRef=para, styleIDRef=style,
            pageBreak="1" if page_break else "0", columnBreak="0", merged="0",
        )
        self.char = char
        self.room = 0.0  # mm a picture in this paragraph may take
        self.in_note = False  # a footnote or caption: notes here fall back
        self._run: etree._Element | None = None
        self._text: etree._Element | None = None

    def _run_for(self, char: str) -> etree._Element:
        if self._run is None or self._run.get("charPrIDRef") != char:
            self._run = etree.SubElement(self.element, hp("run"), charPrIDRef=char)
            self._text = None
        return self._run

    def _t(self, char: str) -> etree._Element:
        run = self._run_for(char)
        if self._text is None:
            self._text = etree.SubElement(run, hp("t"))
        return self._text

    def text(self, char: str, value: str) -> None:
        value = clean(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        for index, part in enumerate(value.split("\t")):
            if index:
                self.mark(char, "tab")
            if part:
                append_text(self._t(char), part)

    def mark(self, char: str, kind: str) -> None:
        """A ``lineBreak`` or ``tab`` inside the text (appendix A-4, A-7)."""
        attrs = {"width": "0", "leader": "0", "type": "1"} if kind == "tab" else {}
        etree.SubElement(self._t(char), hp(kind), attrs)

    def object(self, char: str, element: etree._Element) -> None:
        """A table or picture in the run, followed by an empty ``hp:t`` (appendix B-1)."""
        run = self._run_for(char)
        run.append(element)
        self._text = etree.SubElement(run, hp("t"))

    def control(self, char: str) -> etree._Element:
        ctrl = etree.SubElement(self._run_for(char), hp("ctrl"))
        self._text = None
        return ctrl

    def finish(self) -> etree._Element:
        if self._run is None:
            etree.SubElement(etree.SubElement(self.element, hp("run"), charPrIDRef=self.char), hp("t"))
        return self.element


@dataclass(frozen=True)
class Context:
    element: str = "body"  # look of plain paragraphs here: body, quote or footnote
    quotes: int = 0  # enclosing block quotes
    extra: float = 0.0  # mm added to the element's left margin (list item bodies, definitions)
    level: int = 0  # list depth
    list_text: float = 0.0  # mm: where the enclosing list item's text starts
    tight: bool = False  # no paragraph gaps (tight list items)
    width: float = 0.0  # mm: the column this text flows in (body, table cell, footnote)
    align: str | None = None  # paragraph alignment imposed here (table cells)
    note: bool = False  # inside a footnote or caption: notes there fall back (spec 2026-10-20 §6)


def sub_list(paragraphs: list[etree._Element], valign: str) -> etree._Element:
    """The paragraph list of a cell, caption or footnote (appendix B-1)."""
    element = etree.Element(
        hp("subList"), id="", textDirection="HORIZONTAL", lineWrap="BREAK", vertAlign=valign,
        linkListIDRef="0", linkListNextIDRef="0", textWidth="0", textHeight="0", hasTextRef="0", hasNumRef="0",
    )
    element.extend(paragraphs)
    return element


def _mm(units: int) -> float:
    return units * 25.4 / 7200


class SectionWriter:
    def __init__(self, header: Header, shapes: dict[str, Shape], settings: Settings, notices: Notices,
                 width: float, pictures=None, note_format: etree._Element | None = None) -> None:
        self.header = header
        self.width = width
        self.pictures = pictures
        self.note_format = note_format
        self._objects = itertools.count(1)
        self._figure_caption: tuple[pf.Image, list[pf.Element]] | None = None
        self._footnotes = 0
        self.shapes = shapes
        self.settings = settings
        self.notices = notices
        self.paragraphs: list[Paragraph] = []
        self._page_break = False
        self._notes: list[list[pf.Element]] = []
        self._fields = itertools.count(1_000_001)
        self._quote = header.para_left(shapes["quote"].para)

    # paragraphs ---------------------------------------------------------------------------

    def build(self, doc: pf.Doc) -> list[etree._Element]:
        self.blocks(doc.content, Context(width=self.width))
        index = 0
        while index < len(self._notes):  # a note may hold notes
            self._note(index + 1, self._notes[index])
            index += 1
        if not self.paragraphs:
            self.paragraph("body", Context(width=self.width))
        return self._finish(self.paragraphs)

    def _finish(self, paragraphs: list[Paragraph]) -> list[etree._Element]:
        """The paragraph elements; a floating table takes the next paragraph's space before as its own
        bottom margin, since Hangul lays that paragraph right under the table."""
        elements = [p.finish() for p in paragraphs]
        for element, following in itertools.pairwise(elements):
            gap = self.header.para_prev(following.get("paraPrIDRef"))
            for table in element.findall(f"{hp('run')}/{hp('tbl')}"):
                margin = table.find(hp("outMargin"))
                margin.set("bottom", str(TABLE_MARGIN + gap))
        return elements

    @contextmanager
    def _collect(self):
        """Build paragraphs into a list of their own (cells, captions, footnotes)."""
        outer, page_break = self.paragraphs, self._page_break
        self.paragraphs, self._page_break = [], False
        try:
            yield self.paragraphs
        finally:
            self.paragraphs, self._page_break = outer, page_break

    def available(self, ctx: Context, element: str) -> float:
        """mm a table or picture may take here: the column less the paragraph's left indent."""
        return max(ctx.width - self._left(element, ctx), _MIN_WIDTH_MM)

    def _left(self, element: str, ctx: Context) -> float:
        own = self.header.para_left(self.shapes[element].para)
        depth = ctx.quotes - 1 if element == "quote" else ctx.quotes
        return own + self._quote * max(depth, 0) + ctx.extra

    def _para_id(self, element: str, ctx: Context, **changes) -> str:
        shape = self.shapes[element]
        left = self._left(element, ctx)
        if ctx.align is not None and "align" not in changes:
            changes["align"] = ctx.align
        if abs(left - self.header.para_left(shape.para)) < 1e-6 and not ctx.tight and not changes:
            return shape.para
        gaps = {"prev": 0.0, "next": 0.0} if ctx.tight else {}
        return self.header.add_para(shape.para, ParaSpec(left=left, **gaps, **changes))

    def paragraph(self, element: str, ctx: Context, para: str | None = None) -> Paragraph:
        shape = self.shapes[element]
        paragraph = Paragraph(para or self._para_id(element, ctx), shape.style, shape.char, self._page_break)
        paragraph.room = self.available(ctx, element)
        paragraph.in_note = ctx.note
        self._page_break = False
        self.paragraphs.append(paragraph)
        return paragraph

    # blocks -------------------------------------------------------------------------------

    def blocks(self, blocks, ctx: Context) -> None:
        for block in blocks:
            self.block(block, ctx)

    def block(self, block: pf.Element, ctx: Context) -> None:
        if isinstance(block, (pf.Para, pf.Plain)):
            paragraph = self.paragraph(ctx.element, ctx)
            self.inlines(paragraph, block.content, self.shapes[ctx.element].char)
        elif isinstance(block, pf.Header):
            element = f"heading{min(max(block.level, 1), 6)}"
            paragraph = self.paragraph(element, replace(ctx, tight=False))
            self.inlines(paragraph, block.content, self.shapes[element].char)
        elif isinstance(block, pf.CodeBlock):
            paragraph = self.paragraph("code", ctx)
            char = self.shapes["code"].char
            for index, line in enumerate(block.text.split("\n")):
                if index:
                    paragraph.mark(char, "lineBreak")
                paragraph.text(char, line)
        elif isinstance(block, pf.BlockQuote):
            self.blocks(block.content, replace(ctx, element="quote", quotes=ctx.quotes + 1))
        elif isinstance(block, pf.HorizontalRule):
            rule = self.header.add_border_fill(bottom=True)
            self.paragraph("body", ctx, self._para_id("body", ctx, border_fill=rule))
        elif isinstance(block, pf.LineBlock):
            paragraph = self.paragraph(ctx.element, ctx)
            char = self.shapes[ctx.element].char
            for index, line in enumerate(block.content):
                if index:
                    paragraph.mark(char, "lineBreak")
                self.inlines(paragraph, line.content, char)
        elif isinstance(block, pf.Div):
            self.blocks(block.content, ctx)
        elif isinstance(block, pf.DefinitionList):
            self.definitions(block, ctx)
        elif isinstance(block, (pf.BulletList, pf.OrderedList)):
            self.list(block, ctx)
        elif isinstance(block, pf.Table):
            self.table(block, ctx)
        elif isinstance(block, pf.Figure):
            self.figure(block, ctx)
        elif isinstance(block, pf.RawBlock):
            if (block.format, block.text.strip()) == PAGE_BREAK:
                self._page_break = True

    def definitions(self, block: pf.DefinitionList, ctx: Context) -> None:
        inner = replace(ctx, extra=ctx.extra + self.settings.list_indent)
        bold = self._char(self.shapes[ctx.element].char, bold=True)
        for item in block.content:
            self.inlines(self.paragraph(ctx.element, ctx), item.term, bold)
            for definition in item.definitions:
                self.blocks(definition.content, inner)

    def list(self, block: pf.Element, ctx: Context) -> None:
        """개조식: marker text + tab, hanging indent with Hangul's auto tab (spec §5.3)."""
        ordered = isinstance(block, pf.OrderedList)
        level = ctx.level + 1
        numbers = range(1, 11) if ordered else [1]
        markers = [self.settings.list_marker(ordered, level, n) for n in numbers]
        hanging = hanging_mm(markers, self.settings.body_size)
        base = self._left(ctx.element, replace(ctx, extra=0.0))
        # one indent step further per level, but never left of the parent item's text (docx rule)
        marker_left = base + self.settings.list_indent * (level - 1)
        if ctx.level:
            marker_left = max(marker_left, ctx.list_text)
        text_left = marker_left + hanging
        char = self.shapes[ctx.element].char
        start = block.start if ordered else 1
        for offset, item in enumerate(block.content):
            blocks = list(item.content)
            first = blocks[0] if blocks else None
            marker_ctx = replace(ctx, extra=marker_left - base, tight=isinstance(first, pf.Plain))
            para = self._para_id(ctx.element, marker_ctx, hanging=hanging, tab_pr=self.header.auto_tab())
            paragraph = self.paragraph(ctx.element, ctx, para)
            # the item's text starts after the marker: a picture there may only take the rest
            paragraph.room = max(ctx.width - text_left, _MIN_WIDTH_MM)
            paragraph.text(char, self.settings.list_marker(ordered, level, start + offset))
            paragraph.mark(char, "tab")
            if isinstance(first, (pf.Para, pf.Plain)):
                self.inlines(paragraph, first.content, char)
                blocks = blocks[1:]
            inner = replace(ctx, extra=text_left - base, level=level, list_text=text_left)
            for rest in blocks:
                self.block(rest, replace(inner, tight=isinstance(rest, pf.Plain)))

    # tables (spec 2026-10-20 §4, appendix B-1) ---------------------------------------------

    def table(self, table: pf.Table, ctx: Context) -> None:
        grid = build_grid(table)
        caption = self._caption_blocks(table.caption)
        if not grid.rows or not grid.cols:
            if caption:
                self._caption(caption, ctx)
            return
        tables = self.settings.tables
        look = tables.get(table.attributes.get("mdcast-variant")) or tables.get(None) or TableLook()
        size = look.font_size or self.settings.body_size
        available = self.available(ctx, ctx.element)
        units = [hwpunit(w) for w in column_widths(table, grid, look, available, size)]
        total = hwpunit(available) if look.width == "full" else sum(units)
        units[-1] += total - sum(units)
        pad = hwpunit(look.padding)
        row_height = hwpunit(size * 25.4 / 72 * (look.line_height or 1.0)) + 2 * pad
        anchor = self.paragraph(ctx.element, ctx)

        number = str(next(self._objects))
        element = etree.Element(
            hp("tbl"), id=number, zOrder=number, numberingType="TABLE", textWrap="TOP_AND_BOTTOM",
            textFlow="BOTH_SIDES", lock="0", dropcapstyle="None", pageBreak="CELL",
            repeatHeader="1" if look.header_repeat else "0", rowCnt=str(len(grid.rows)), colCnt=str(grid.cols),
            cellSpacing="0", borderFillIDRef=self.header.add_cell_border_fill((None,) * 4, None), noAdjust="0",
        )
        etree.SubElement(element, hp("sz"), width=str(total), widthRelTo="ABSOLUTE",
                         height=str(row_height * len(grid.rows)), heightRelTo="ABSOLUTE", protect="0")
        etree.SubElement(element, hp("pos"), **_TABLE_POS)
        # Hangul's 1mm above and below: without it the next paragraph runs into a floating table
        etree.SubElement(element, hp("outMargin"), left="0", right="0", top=str(TABLE_MARGIN),
                         bottom=str(TABLE_MARGIN))
        if caption:
            element.append(self.caption_element(caption, total, self.settings.table_caption_above))
        margins = {"left": str(pad), "right": str(pad), "top": str(pad), "bottom": str(pad)}
        etree.SubElement(element, hp("inMargin"), margins)
        shapes = self._cell_shapes(size, look)
        for row in grid.rows:
            tr = etree.SubElement(element, hp("tr"))
            for slot in row:
                width = sum(units[slot.col : slot.col + slot.colspan])
                fill = self.header.add_cell_border_fill(slot_sides(slot, grid, look), slot_fill(slot, look))
                tc = etree.SubElement(
                    tr, hp("tc"), name="", header="1" if slot.part == "head" else "0", hasMargin="0",
                    protect="0", editable="0", dirty="0", borderFillIDRef=fill,
                )
                inner = _mm(width) - 2 * look.padding
                tc.append(sub_list(self._cell(table, slot, shapes, inner, ctx), slot_valign(slot, look)))
                etree.SubElement(tc, hp("cellAddr"), colAddr=str(slot.col), rowAddr=str(slot.row))
                etree.SubElement(tc, hp("cellSpan"), colSpan=str(slot.colspan), rowSpan=str(slot.rowspan))
                etree.SubElement(tc, hp("cellSz"), width=str(width), height=str(row_height * slot.rowspan))
                etree.SubElement(tc, hp("cellMargin"), margins)
        anchor.object(self.shapes[ctx.element].char, element)

    def _cell_shapes(self, size: float, look: TableLook) -> dict[str, Shape]:
        """The element shapes with the body at the table's size and line height, no paragraph gaps."""
        body = self.shapes["body"]
        para = self.header.add_para(body.para, ParaSpec(line_height=look.line_height, prev=0.0, next=0.0))
        char = self.header.add_char(body.char, CharSpec(size=size))
        return {**self.shapes, "body": Shape(body.style, para, char, body.look)}

    def _cell(self, table: pf.Table, slot: Slot, shapes: dict[str, Shape], inner: float,
              ctx: Context) -> list[etree._Element]:
        alignment = slot.cell.alignment if slot.cell is not None else "AlignDefault"
        if alignment == "AlignDefault" and slot.col < len(table.colspec):
            alignment = table.colspec[slot.col][0]
        cell_ctx = Context(width=inner, align=_ALIGN.get(alignment), note=ctx.note)
        outer = self.shapes
        self.shapes = shapes
        try:
            with self._collect() as paragraphs:
                self.blocks(list(slot.cell.content) if slot.cell is not None else [], cell_ctx)
                if not paragraphs:
                    self.paragraph("body", cell_ctx)
        finally:
            self.shapes = outer
        return self._finish(paragraphs)

    def caption_element(self, blocks: list[pf.Element], width: int, above: bool) -> etree._Element:
        """Hangul's caption on a table or picture, without Hangul's own number (appendix B-8)."""
        caption = etree.Element(hp("caption"), side="TOP" if above else "BOTTOM", fullSz="0", width="8504",
                                gap="850", lastWidth=str(width))
        with self._collect() as paragraphs:
            self._caption(blocks, Context(element="caption", width=_mm(width), note=True))
        caption.append(sub_list([p.finish() for p in paragraphs], "TOP"))
        return caption

    def figure(self, figure: pf.Figure, ctx: Context) -> None:
        """One paragraph aligned per ``figures.align``; a lone picture carries the caption (spec §5.3)."""
        caption = self._caption_blocks(figure.caption)
        found: list[pf.Image] = []
        figure.content.walk(lambda e, _d: found.append(e) if isinstance(e, pf.Image) else None)
        own = len(found) == 1 and found[0].url in self.settings.images and self.pictures is not None
        above = self.settings.figure_caption_above
        if caption and not own and above:
            self._caption(caption, ctx)
        if caption and own:
            self._figure_caption = (found[0], caption)
        blocks = list(figure.content)
        if blocks and isinstance(blocks[0], (pf.Para, pf.Plain)):
            para = self._para_id(ctx.element, ctx, align=self.settings.figure_align)
            paragraph = self.paragraph(ctx.element, ctx, para)
            self.inlines(paragraph, blocks.pop(0).content, self.shapes[ctx.element].char)
        self.blocks(blocks, ctx)
        self._figure_caption = None
        if caption and not own and not above:
            self._caption(caption, ctx)

    def picture(self, paragraph: Paragraph, item: pf.Image, char: str) -> None:
        image = self.settings.images.get(item.url)
        alt = clean(pf.stringify(item).strip())
        if image is None or self.pictures is None:  # the adapter already warned about it
            paragraph.text(char, f"[이미지: {alt or item.url}]")
            return
        width, height = picture_size(image, item.attributes.get("width"), item.attributes.get("height"),
                                     paragraph.room, self.settings.figure_max_ratio, self.settings.figure_max_mm)
        caption = None
        if self._figure_caption is not None and self._figure_caption[0] is item:
            caption = self.caption_element(self._figure_caption[1], hwpunit(width), self.settings.figure_caption_above)
        item_id = self.pictures.add(image)
        paragraph.object(char, picture_element(item_id, image, width, height, alt, next(self._objects), caption))

    @staticmethod
    def _caption_blocks(caption: pf.Caption | None) -> list[pf.Element]:
        if caption is None:
            return []
        return [b for b in caption.content if isinstance(b, (pf.Para, pf.Plain)) and pf.stringify(b).strip()]

    def _caption(self, blocks: list[pf.Element], ctx: Context) -> None:
        for block in blocks:
            self.inlines(self.paragraph("caption", ctx), block.content, self.shapes["caption"].char)

    def _note(self, number: int, blocks: list[pf.Element]) -> None:
        ctx = Context(element="footnote", width=self.width, note=True)
        char = self.shapes["footnote"].char
        paragraph = self.paragraph("footnote", ctx)
        paragraph.text(char, f"[주 {number}] ")
        rest = list(blocks)
        if rest and isinstance(rest[0], (pf.Para, pf.Plain)):
            self.inlines(paragraph, rest.pop(0).content, char)
        self.blocks(rest, ctx)

    def footnote(self, paragraph: Paragraph, item: pf.Note, char: str) -> None:
        """Hangul's footnote (appendix B-12); inside a note or caption it falls back to [주 n]."""
        if paragraph.in_note:
            self.notices.add("degraded", "footnote", _DEGRADED["footnote"])
            self._notes.append(list(item.content))
            paragraph.text(char, f"[주 {len(self._notes)}]")
            return
        self._footnotes += 1
        number = str(self._footnotes)
        ctx = Context(element="footnote", width=self.width, note=True)
        note_char = self.shapes["footnote"].char
        with self._collect() as paragraphs:
            first = self.paragraph("footnote", ctx)
            auto = etree.SubElement(first.control(note_char), hp("autoNum"), num=number, numType="FOOTNOTE")
            auto.append(copy.deepcopy(self.note_format) if self.note_format is not None else etree.Element(
                hp("autoNumFormat"), type="DIGIT", userChar="", prefixChar="", suffixChar=")", supscript="0"))
            first.text(note_char, " ")
            rest = list(item.content)
            if rest and isinstance(rest[0], (pf.Para, pf.Plain)):
                self.inlines(first, rest.pop(0).content, note_char)
            self.blocks(rest, ctx)
        note = etree.SubElement(paragraph.control(char), hp("footNote"), number=number, suffixChar="41",
                                instId=str(next(self._objects)))
        note.append(sub_list(self._finish(paragraphs), "TOP"))

    # inlines ------------------------------------------------------------------------------

    def _char(self, base: str, **changes) -> str:
        return self.header.add_char(base, CharSpec(**changes))

    def _code(self, base: str) -> str:
        look = self.shapes["code"].look
        spec = CharSpec(font=look.font, font_hangul=look.font_hangul, size=look.size)
        return self.header.add_char(base, spec)

    def inlines(self, paragraph: Paragraph, items, char: str) -> None:
        for item in items:
            self.inline(paragraph, item, char)

    def inline(self, paragraph: Paragraph, item: pf.Element, char: str) -> None:
        if isinstance(item, pf.Str):
            paragraph.text(char, item.text)
        elif isinstance(item, (pf.Space, pf.SoftBreak)):
            paragraph.text(char, " ")
        elif isinstance(item, pf.LineBreak):
            paragraph.mark(char, "lineBreak")
        elif isinstance(item, pf.Emph):
            self.inlines(paragraph, item.content, self._char(char, italic=True))
        elif isinstance(item, pf.Strong):
            self.inlines(paragraph, item.content, self._char(char, bold=True))
        elif isinstance(item, pf.Underline):
            self.inlines(paragraph, item.content, self._char(char, underline=True))
        elif isinstance(item, pf.Strikeout):
            self.inlines(paragraph, item.content, self._char(char, strike=True))
        elif isinstance(item, pf.Superscript):
            self.inlines(paragraph, item.content, self._char(char, script="sup"))
        elif isinstance(item, pf.Subscript):
            self.inlines(paragraph, item.content, self._char(char, script="sub"))
        elif isinstance(item, pf.Quoted):
            left, right = ("“", "”") if item.quote_type == "DoubleQuote" else ("‘", "’")
            paragraph.text(char, left)
            self.inlines(paragraph, item.content, char)
            paragraph.text(char, right)
        elif isinstance(item, pf.Code):
            paragraph.text(self._code(char), item.text)
        elif isinstance(item, pf.Math):
            self.notices.add("degraded", "math", _DEGRADED["math"])
            paragraph.text(self._code(char), item.text)
        elif isinstance(item, pf.Image):
            self.picture(paragraph, item, char)
        elif isinstance(item, pf.Note):
            self.footnote(paragraph, item, char)
        elif isinstance(item, pf.Link):
            self.link(paragraph, item, char)
        elif isinstance(item, (pf.SmallCaps, pf.Span, pf.Cite)):
            self.inlines(paragraph, item.content, char)
        # RawInline (other formats) and anything else: dropped

    def link(self, paragraph: Paragraph, item: pf.Link, char: str) -> None:
        """Hangul hyperlink field around the link text (appendix A-5); ``#id`` links stay text."""
        url = clean(item.url or "")
        if not url or url.startswith("#"):
            self.inlines(paragraph, item.content, char)
            return
        field = str(next(self._fields))
        begin = etree.SubElement(
            paragraph.control(char), hp("fieldBegin"), id=field, type="HYPERLINK", name="",
            editable="0", dirty="0", zorder="-1", fieldid=HYPERLINK_FIELD,
        )
        params = etree.SubElement(begin, hp("parameters"), cnt="6", name="")
        etree.SubElement(params, hp("integerParam"), name="Prop").text = "0"
        for name, value in (
            ("Command", escape_command(url) + ";1;0;0;"),
            ("Path", url),
            ("Category", "HWPHYPERLINK_TYPE_URL"),
            ("TargetType", "HWPHYPERLINK_TARGET_BOOKMARK"),
            ("DocOpenType", "HWPHYPERLINK_JUMP_CURRENTTAB"),
        ):
            etree.SubElement(params, hp("stringParam"), name=name).text = value
        self.inlines(paragraph, item.content, self._char(char, color=LINK_COLOR, underline=True))
        etree.SubElement(paragraph.control(char), hp("fieldEnd"), beginIDRef=field, fieldid=HYPERLINK_FIELD)
