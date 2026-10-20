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


def _generic(text: str) -> str:
    return re.escape(text.replace("{n}", "\0")).replace("\0", r"\d+")


def _undo_caption(caption: pf.Caption, fmt: str, n: int, ctx: ImportContext) -> None:
    before, _, after = fmt.partition("{text}")
    blocks = [b for b in caption.content if isinstance(b, (pf.Plain, pf.Para))]
    if not blocks:
        return
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
                if isinstance(block, (pf.Plain, pf.Para)) and len(block.content) == 1 and isinstance(block.content[0], pf.Strong):
                    block.content = list(block.content[0].content)


def _reverse_inline_state(doc: pf.Doc, config: dict[str, Any], ctx: ImportContext) -> None:
    patterns = list(config["headings"].get("numbering") or [])
    table_fmt = config["tables"]["caption"]["format"]
    figure_fmt = config["figures"]["caption"]["format"]
    header_bold = bool(config["tables"]["header"].get("bold"))
    counters = [0] * 6
    seen = {"table": 0, "figure": 0}

    def action(elem: pf.Element, _doc: pf.Doc) -> None:
        if isinstance(elem, pf.Header) and patterns and elem.level <= len(patterns):
            level = elem.level
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
                _undo_caption(elem.caption, table_fmt, seen["table"], ctx)
        elif isinstance(elem, pf.Figure) and _has_caption(elem.caption):
            seen["figure"] += 1
            _undo_caption(elem.caption, figure_fmt, seen["figure"], ctx)

    doc.walk(action)


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
    _reverse_inline_state(doc, tpl.config, ctx)
    _drop_rule_breaks(doc, tpl.config, ctx)
    _restore_table_kinds(doc, ctx.table_styles)
    return doc
