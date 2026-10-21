from __future__ import annotations

import re
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import panflute as pf

from mdcast.counters import format_counter
from mdcast.filters import pagebreak as export_pagebreak
from mdcast.filters._raw import raw_block
from mdcast.filters.importing.context import ImportContext
from mdcast.readers.hwpx.body import HINT_CLASS
from mdcast.templates import resolve_template


def _plain(inlines: list[pf.Inline]) -> str:
    return "".join(" " if isinstance(i, (pf.Space, pf.SoftBreak)) else pf.stringify(i) for i in inlines)


def _count(inlines: list[pf.Inline], chars: int) -> int | None:
    """How many leading plain-text inlines make up exactly ``chars`` characters; None if they don't align."""
    taken = used = 0
    for inline in inlines:
        if taken >= chars:
            break
        if isinstance(inline, pf.Str):
            taken += len(inline.text)
        elif isinstance(inline, pf.Space):
            taken += 1
        else:
            return None
        used += 1
    return used if taken == chars else None


def _strip_leading(inlines: list[pf.Inline], prefix: str) -> list[pf.Inline] | None:
    if not prefix or not _plain(inlines).startswith(prefix):
        return None
    used = _count(inlines, len(prefix))
    return None if used is None else inlines[used:]


def _strip_trailing(inlines: list[pf.Inline], suffix: str) -> list[pf.Inline] | None:
    if not suffix or not _plain(inlines).endswith(suffix):
        return None
    used = _count(inlines[::-1], len(suffix))
    return None if used is None else inlines[: len(inlines) - used]


def _register(ctx: ImportContext, pattern: re.Pattern[str]) -> None:
    if pattern not in ctx.prefixes:
        ctx.prefixes.append(pattern)


def _has_caption(caption: pf.Caption | None) -> bool:
    return caption is not None and pf.stringify(caption).strip() != ""


def _unwrap_strong(block: pf.Element) -> None:
    """A block whose whole text is one Strong loses it: bold the export put on the element (hwpx run formatting)."""
    if len(block.content) == 1 and isinstance(block.content[0], pf.Strong):
        block.content = list(block.content[0].content)


def _generic(text: str) -> str:
    return re.escape(text.replace("{n}", "\0")).replace("\0", r"\d+")


def _undo_caption(caption: pf.Caption, fmt: str, n: int, ctx: ImportContext, *, bold: bool) -> None:
    before, _, after = fmt.partition("{text}")
    blocks = [b for b in caption.content if isinstance(b, (pf.Plain, pf.Para))]
    if not blocks:
        return
    if bold:  # hwpx writes the caption's bold on its runs; docx keeps it in the caption style
        for block in blocks:
            _unwrap_strong(block)
    head, last = blocks[0], blocks[-1]
    head_inlines = list(head.content)
    if before:
        stripped = _strip_leading(head_inlines, before.replace("{n}", str(n)))
        if stripped is None:
            return
        head_inlines = stripped
    last_inlines = head_inlines if last is head else list(last.content)
    if after:
        stripped = _strip_trailing(last_inlines, after.replace("{n}", str(n)))
        if stripped is None:
            return
        last_inlines = stripped
    if last is head:
        head.content = last_inlines
    else:
        head.content = head_inlines
        last.content = last_inlines
    if before:
        _register(ctx, re.compile(r"^" + _generic(before)))
    if after:
        _register(ctx, re.compile(_generic(after) + r"$"))


def _unwrap_header_strong(table: pf.Table) -> None:
    for row in table.head.content:
        for cell in row.content:
            for block in cell.content:
                if isinstance(block, (pf.Plain, pf.Para)):
                    _unwrap_strong(block)


def _reverse_inline_state(doc: pf.Doc, config: dict[str, Any], ctx: ImportContext) -> None:
    patterns = list(config["headings"].get("numbering") or [])
    table_fmt = config["tables"]["caption"]["format"]
    figure_fmt = config["figures"]["caption"]["format"]
    header_bold = bool(config["tables"]["header"].get("bold"))
    caption_bold = bool((config["elements"].get("caption") or {}).get("bold"))
    counters = [0] * 6
    seen = {"table": 0, "figure": 0}

    def action(elem: pf.Element, _doc: pf.Doc) -> None:
        if isinstance(elem, pf.Header) and patterns and elem.level <= len(patterns):
            level = elem.level
            _unwrap_strong(elem)  # hwpx: the heading's bold is on its runs (the headings filter drops it too)
            saved = list(counters)
            counters[level - 1] += 1
            for deeper in range(level, 6):
                counters[deeper] = 0
            prefix = format_counter(patterns[level - 1], counters[level - 1])
            stripped = _strip_leading(list(elem.content), prefix + " ")
            if stripped is None:
                counters[:] = saved  # an unnumbered heading never used up a number
                return
            elem.content = stripped
            _register(ctx, re.compile(r"^" + re.escape(prefix) + r"\s*"))
        elif isinstance(elem, pf.Table):
            if header_bold:
                _unwrap_header_strong(elem)
            if _has_caption(elem.caption):
                seen["table"] += 1
                _undo_caption(elem.caption, table_fmt, seen["table"], ctx, bold=caption_bold)
        elif isinstance(elem, pf.Figure) and _has_caption(elem.caption):
            seen["figure"] += 1
            _undo_caption(elem.caption, figure_fmt, seen["figure"], ctx, bold=caption_bold)

    doc.walk(action)


def _lone_image(block: pf.Element) -> pf.Image | None:
    if isinstance(block, (pf.Para, pf.Plain)) and len(block.content) == 1 and isinstance(block.content[0], pf.Image):
        return block.content[0]
    return None


def _attach_figure_captions(doc: pf.Doc, config: dict[str, Any]) -> None:
    """A picture's paragraph and the caption paragraph beside it → one Figure (hwpx).

    The hwpx writer sets a figure caption as a paragraph of its own (or as the picture's
    ``hp:caption``, which the reader also puts after the picture), on the side
    ``figures.caption.position`` says. Only a top-level paragraph that starts with the caption
    format's prefix counts; ``_reverse_inline_state`` then takes the numbered prefix off.
    """
    caption = config["figures"]["caption"]
    before = caption["format"].partition("{text}")[0]
    if not before:
        return
    lead = re.compile("^" + _generic(before))
    above = (caption.get("position") or "below") == "above"

    def caption_of(block: pf.Element) -> list[pf.Inline] | None:
        if not isinstance(block, (pf.Para, pf.Plain)) or _lone_image(block) is not None:
            return None
        inlines = list(block.content)
        return inlines if lead.match(_plain(inlines)) else None

    blocks = list(doc.content)
    out: list[pf.Element] = []
    i = 0
    while i < len(blocks):
        if i + 1 < len(blocks):
            first, second = blocks[i], blocks[i + 1]
            image = _lone_image(second if above else first)
            inlines = caption_of(first if above else second)
            if image is not None and inlines is not None:
                out.append(pf.Figure(pf.Plain(image), caption=pf.Caption(pf.Plain(*inlines))))
                i += 2
                continue
        out.append(blocks[i])
        i += 1
    doc.content = out


def _is_hint(elem: pf.Element) -> bool:
    return isinstance(elem, pf.Span) and HINT_CLASS in elem.classes


def _hints(block: pf.Element) -> list[pf.Span]:
    found: list[pf.Span] = []
    block.walk(lambda e, _d: found.append(e) if _is_hint(e) else None)
    return found


def _colour(value: Any) -> str:
    return str(value or "").upper()


def _take_hints(doc: pf.Doc, config: dict[str, Any]) -> None:
    """hwpx: the writer's code, code block and quote marks back as Code, CodeBlock, BlockQuote (R17).

    The hwpx reader keeps, for mdcast documents only, each run's Latin font and colour and its
    paragraph's background as a hint span. The writer sets inline code (and math) in the
    template's code font, a code block also on the code background, and a quote in the quote
    colour; matching them here against the template keeps the reader template-free. Every hint
    span is gone afterwards: the unmatched ones are unwrapped.
    """
    fonts, elements = config["fonts"], config["elements"]
    code_font = str((fonts.get("code") or {}).get("family") or "")
    if code_font == str((fonts.get("body") or {}).get("family") or ""):
        code_font = ""  # nothing sets code apart
    code_fill = _colour((elements.get("code") or {}).get("background"))
    quote = _colour((elements.get("quote") or {}).get("color"))
    if quote == _colour((elements.get("body") or {}).get("color") or "#000000"):
        quote = ""

    def is_code(span: pf.Span) -> bool:
        return bool(code_font) and span.attributes.get("font") == code_font

    def code_block(block: pf.Element) -> pf.CodeBlock | None:
        if not isinstance(block, pf.Para) or not block.content:
            return None
        spans = list(block.content)
        if not all(_is_hint(s) and is_code(s) for s in spans):
            return None
        if code_fill and any(s.attributes.get("fill") != code_fill for s in spans):
            return None  # code on the body background: a paragraph of inline code (or math)
        return pf.CodeBlock("".join(s.attributes.get("text", "") for s in spans))

    def quoted(block: pf.Element) -> bool:
        if not quote or not isinstance(block, pf.Para):
            return False
        spans = _hints(block)
        return bool(spans) and all(s.attributes.get("color") == quote for s in spans)

    out: list[pf.Element] = []
    open_quote: pf.BlockQuote | None = None  # the quote that quoted paragraphs in a row join
    for block in doc.content:
        if quoted(block):
            if open_quote is None:
                open_quote = pf.BlockQuote()
                out.append(open_quote)
            open_quote.content.append(block)
            continue
        open_quote = None
        replaced = code_block(block)
        if replaced is None:
            out.append(block)
        elif out and isinstance(out[-1], pf.CodeBlock):
            # code blocks side by side join, as docx does (M3a §5.4 b); written apart they would
            # come back from the MD as one block with a blank line inside
            out[-1].text += "\n" + replaced.text
        else:
            out.append(replaced)
    doc.content = out

    def unwrap(elem: pf.Element, _doc: pf.Doc):
        if not _is_hint(elem):
            return None
        if is_code(elem):
            return pf.Code(elem.attributes.get("text", "").strip())
        return list(elem.content)

    doc.walk(unwrap)


def _drop_rule_breaks(doc: pf.Doc, config: dict[str, Any], ctx: ImportContext) -> None:
    shim = SimpleNamespace(config=config, frontmatter={}, report=ctx.report)
    levels, skip_first = export_pagebreak._settings(shim)  # type: ignore[arg-type]
    if not levels:
        return
    out: list[pf.Element] = []
    seen_rule_heading = False
    for block in doc.content:
        if isinstance(block, pf.Header) and block.level in levels:
            if (seen_rule_heading or not skip_first) and out and export_pagebreak.is_marker(out[-1]):
                out.pop()
            seen_rule_heading = True
        out.append(block)
    doc.content = out


def _holders(elem: pf.Element) -> Iterator[pf.Element]:
    """Elements directly under ``elem`` whose content is a block list, in document order."""
    if isinstance(elem, (pf.BlockQuote, pf.Div, pf.Figure)):
        yield elem
    elif isinstance(elem, (pf.BulletList, pf.OrderedList)):
        yield from elem.content
    elif isinstance(elem, pf.DefinitionList):
        for item in elem.content:
            yield from item.definitions
    elif isinstance(elem, pf.Table):
        yield elem.caption
        rows = [*elem.head.content]
        for body in elem.content:
            rows += [*body.head, *body.content]
        rows += elem.foot.content
        for row in rows:
            yield from row.content


def _table_count(doc: pf.Doc) -> int:
    count = 0

    def tally(elem: pf.Element, _doc: pf.Doc) -> None:
        nonlocal count
        count += isinstance(elem, pf.Table)

    doc.walk(tally)
    return count


def _restore_table_kinds(doc: pf.Doc, styles: list[str | None]) -> None:
    """Mark tables in document pre-order, the order ``styles`` was read in."""
    if not any(styles) or len(styles) != _table_count(doc):
        return
    queue = iter(styles)

    def visit(holder: pf.Element) -> None:
        out: list[pf.Element] = []
        for block in holder.content:
            if isinstance(block, pf.Table):
                kind = next(queue)
                if kind:
                    out.append(raw_block(f"<!-- table: {kind} -->", "html"))
            out.append(block)
            for child in _holders(block):
                visit(child)
        holder.content = out

    visit(doc)


def apply(doc: pf.Doc, ctx: ImportContext) -> pf.Doc:
    if not ctx.generator:
        return doc
    name = ctx.generator.get("mdcast.template.name") or None
    tpl = resolve_template(name, cwd=ctx.cwd, home=ctx.home, report=ctx.report)
    if name:
        ctx.frontmatter["template"] = name
    _take_hints(doc, tpl.config)
    _attach_figure_captions(doc, tpl.config)
    _reverse_inline_state(doc, tpl.config, ctx)
    _drop_rule_breaks(doc, tpl.config, ctx)
    _restore_table_kinds(doc, ctx.table_styles)
    return doc
