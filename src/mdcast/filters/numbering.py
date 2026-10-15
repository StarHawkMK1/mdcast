from __future__ import annotations

import panflute as pf

from mdcast.counters import format_counter
from mdcast.filters.context import FilterContext


def _inlines(text: str) -> list[pf.Inline]:
    out: list[pf.Inline] = []
    for index, part in enumerate(text.split(" ")):
        if index:
            out.append(pf.Space())
        if part:
            out.append(pf.Str(part))
    return out


def _has_caption(caption: pf.Caption | None) -> bool:
    return caption is not None and pf.stringify(caption).strip() != ""


def _decorate(caption: pf.Caption, fmt: str, n: int) -> None:
    before, _, after = fmt.partition("{text}")
    before = before.replace("{n}", str(n))
    after = after.replace("{n}", str(n))
    blocks = [b for b in caption.content if isinstance(b, (pf.Plain, pf.Para))]
    if not blocks:
        return
    if before:
        blocks[0].content = [*_inlines(before), *blocks[0].content]
    if after:
        blocks[-1].content = [*blocks[-1].content, *_inlines(after)]


def apply(doc: pf.Doc, ctx: FilterContext) -> pf.Doc:
    patterns = list(ctx.config["headings"].get("numbering") or [])
    counters = [0] * 6
    table_fmt = ctx.config["tables"]["caption"]["format"]
    figure_fmt = ctx.config["figures"]["caption"]["format"]
    seen = {"table": 0, "figure": 0}

    def action(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.Header) and patterns and "unnumbered" not in elem.classes:
            level = elem.level
            if level <= len(patterns):
                counters[level - 1] += 1
                for deeper in range(level, 6):
                    counters[deeper] = 0
                prefix = format_counter(patterns[level - 1], counters[level - 1])
                elem.content = [pf.Str(prefix), pf.Space(), *elem.content]
                elem.attributes["mdcast-number"] = prefix
        elif isinstance(elem, pf.Table) and _has_caption(elem.caption):
            seen["table"] += 1
            _decorate(elem.caption, table_fmt, seen["table"])
        elif isinstance(elem, pf.Figure) and _has_caption(elem.caption):
            seen["figure"] += 1
            _decorate(elem.caption, figure_fmt, seen["figure"])

    doc.walk(action)
    return doc
