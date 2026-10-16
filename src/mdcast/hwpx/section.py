"""Pandoc AST → section0.xml paragraphs (spec §5)."""

from __future__ import annotations

import itertools
import re
import unicodedata
from dataclasses import dataclass, replace

import panflute as pf
from lxml import etree

from mdcast.hwpx.header import CharSpec, Header, ParaSpec
from mdcast.hwpx.look import Notices, Settings
from mdcast.hwpx.shapes import Shape

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
PAGE_BREAK = ("mdcast-hwpx", "pagebreak")  # raw block the pagebreak filter writes for hwpx
LINK_COLOR = "#0000FF"  # Hangul's own link look (appendix A-5)
HYPERLINK_FIELD = "627600491"  # '%hlk'
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_GAP_EM = 0.5  # between a list marker and its text, as the docx writer
_MIN_HANGING_MM = 3.0
_DEGRADED = {
    "table": "hwpx 표는 M2b 에서 지원합니다 — 행마다 한 문단으로 낮춰 썼습니다",
    "image": "hwpx 이미지는 M2b 에서 지원합니다 — [이미지: 설명] 으로 대신 썼습니다",
    "footnote": "hwpx 각주는 M2b 에서 지원합니다 — 문서 끝에 모아 썼습니다",
    "math": "hwpx 수식은 M4 에서 이미지로 지원합니다 — LaTeX 원문을 썼습니다",
}


def hp(tag: str) -> str:
    return f"{{{HP}}}{tag}"


def append_text(t: etree._Element, text: str) -> None:
    """Add text at the end of an ``hp:t`` that may already hold tab or line-break children."""
    if len(t):
        t[-1].tail = (t[-1].tail or "") + text
    else:
        t.text = (t.text or "") + text


def text_em(text: str) -> float:
    """Rough rendered width in em, as the docx writer estimates list markers."""
    return sum(1.0 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 0.55 for ch in text)


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
        value = _CONTROL.sub("", value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        for index, part in enumerate(value.split("\t")):
            if index:
                self.mark(char, "tab")
            if part:
                append_text(self._t(char), part)

    def mark(self, char: str, kind: str) -> None:
        """A ``lineBreak`` or ``tab`` inside the text (appendix A-4, A-7)."""
        attrs = {"width": "0", "leader": "0", "type": "1"} if kind == "tab" else {}
        etree.SubElement(self._t(char), hp(kind), attrs)

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


class SectionWriter:
    def __init__(self, header: Header, shapes: dict[str, Shape], settings: Settings, notices: Notices) -> None:
        self.header = header
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
        self.blocks(doc.content, Context())
        index = 0
        while index < len(self._notes):  # a note may hold notes
            self._note(index + 1, self._notes[index])
            index += 1
        if not self.paragraphs:
            self.paragraph("body", Context())
        return [p.finish() for p in self.paragraphs]

    def _left(self, element: str, ctx: Context) -> float:
        own = self.header.para_left(self.shapes[element].para)
        depth = ctx.quotes - 1 if element == "quote" else ctx.quotes
        return own + self._quote * max(depth, 0) + ctx.extra

    def _para_id(self, element: str, ctx: Context, **changes) -> str:
        shape = self.shapes[element]
        left = self._left(element, ctx)
        if abs(left - self.header.para_left(shape.para)) < 1e-6 and not ctx.tight and not changes:
            return shape.para
        gaps = {"prev": 0.0, "next": 0.0} if ctx.tight else {}
        return self.header.add_para(shape.para, ParaSpec(left=left, **gaps, **changes))

    def paragraph(self, element: str, ctx: Context, para: str | None = None) -> Paragraph:
        shape = self.shapes[element]
        paragraph = Paragraph(para or self._para_id(element, ctx), shape.style, shape.char, self._page_break)
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
            paragraph.text(char, self.settings.list_marker(ordered, level, start + offset))
            paragraph.mark(char, "tab")
            if isinstance(first, (pf.Para, pf.Plain)):
                self.inlines(paragraph, first.content, char)
                blocks = blocks[1:]
            inner = replace(ctx, extra=text_left - base, level=level, list_text=text_left)
            for rest in blocks:
                self.block(rest, replace(inner, tight=isinstance(rest, pf.Plain)))

    # degraded until M2b (spec §5.6) -------------------------------------------------------

    def table(self, table: pf.Table, ctx: Context) -> None:
        self.notices.add("degraded", "table", _DEGRADED["table"])
        caption = self._caption_blocks(table.caption)
        above = self.settings.table_caption_above
        if caption and above:
            self._caption(caption, ctx)
        rows = list(table.head.content) if table.head else []
        for body in table.content:
            rows += list(body.head) + list(body.content)
        if table.foot:
            rows += list(table.foot.content)
        char = self.shapes[ctx.element].char
        for row in rows:
            paragraph = self.paragraph(ctx.element, ctx)
            for index, cell in enumerate(row.content):
                if index:
                    paragraph.text(char, " | ")
                for number, inner in enumerate(cell.content):
                    if number:
                        paragraph.text(char, " ")
                    if isinstance(inner, (pf.Para, pf.Plain)):
                        self.inlines(paragraph, inner.content, char)
                    else:
                        paragraph.text(char, pf.stringify(inner))
        if caption and not above:
            self._caption(caption, ctx)

    def figure(self, figure: pf.Figure, ctx: Context) -> None:
        caption = self._caption_blocks(figure.caption)
        above = self.settings.figure_caption_above
        if caption and above:
            self._caption(caption, ctx)
        self.blocks(figure.content, ctx)
        if caption and not above:
            self._caption(caption, ctx)

    @staticmethod
    def _caption_blocks(caption: pf.Caption | None) -> list[pf.Element]:
        if caption is None:
            return []
        return [b for b in caption.content if isinstance(b, (pf.Para, pf.Plain)) and pf.stringify(b).strip()]

    def _caption(self, blocks: list[pf.Element], ctx: Context) -> None:
        for block in blocks:
            self.inlines(self.paragraph("caption", ctx), block.content, self.shapes["caption"].char)

    def _note(self, number: int, blocks: list[pf.Element]) -> None:
        ctx = Context(element="footnote")
        char = self.shapes["footnote"].char
        paragraph = self.paragraph("footnote", ctx)
        paragraph.text(char, f"[{number}] ")
        rest = list(blocks)
        if rest and isinstance(rest[0], (pf.Para, pf.Plain)):
            self.inlines(paragraph, rest.pop(0).content, char)
        self.blocks(rest, ctx)

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
            self.notices.add("degraded", "image", _DEGRADED["image"])
            paragraph.text(char, f"[이미지: {pf.stringify(item).strip() or item.url}]")
        elif isinstance(item, pf.Note):
            self.notices.add("degraded", "footnote", _DEGRADED["footnote"])
            self._notes.append(list(item.content))
            paragraph.text(char, f"[{len(self._notes)}]")
        elif isinstance(item, pf.Link):
            self.link(paragraph, item, char)
        elif isinstance(item, (pf.SmallCaps, pf.Span, pf.Cite)):
            self.inlines(paragraph, item.content, char)
        # RawInline (other formats) and anything else: dropped

    def link(self, paragraph: Paragraph, item: pf.Link, char: str) -> None:
        """Hangul hyperlink field around the link text (appendix A-5); ``#id`` links stay text."""
        if not item.url or item.url.startswith("#"):
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
            ("Command", escape_command(item.url) + ";1;0;0;"),
            ("Path", item.url),
            ("Category", "HWPHYPERLINK_TYPE_URL"),
            ("TargetType", "HWPHYPERLINK_TARGET_BOOKMARK"),
            ("DocOpenType", "HWPHYPERLINK_JUMP_CURRENTTAB"),
        ):
            etree.SubElement(params, hp("stringParam"), name=name).text = value
        self.inlines(paragraph, item.content, self._char(char, color=LINK_COLOR, underline=True))
        etree.SubElement(paragraph.control(char), hp("fieldEnd"), beginIDRef=field, fieldid=HYPERLINK_FIELD)
