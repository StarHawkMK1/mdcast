from __future__ import annotations

import re
from typing import Any

import panflute as pf

from mdcast.filters._raw import raw_block
from mdcast.filters.context import FilterContext
from mdcast.report import Codes
from mdcast.types import Format

_MARKER = re.compile(r"^\s*<!--\s*pagebreak\s*-->\s*$", re.IGNORECASE)
_LEVELS = {f"h{i}": i for i in range(1, 7)}
_WARN_MESSAGE = "frontmatter 의 page_break 값이 올바르지 않아 템플릿 값을 씁니다"


def is_marker(elem: pf.Element) -> bool:
    return isinstance(elem, pf.RawBlock) and elem.format == "html" and bool(_MARKER.match(elem.text))


def break_block(target: Format) -> pf.RawBlock:
    if target is Format.DOCX:
        return raw_block('<w:p><w:r><w:br w:type="page"/></w:r></w:p>', "openxml")
    if target is Format.PDF:
        return raw_block("#pagebreak()", "typst")
    if target is Format.HWPX:
        return raw_block("pagebreak", "mdcast-hwpx")  # read by mdcast.hwpx.section
    return raw_block("<!-- pagebreak -->", "html")


def _is_break(elem: pf.Element, target: Format) -> bool:
    sample = break_block(target)
    return isinstance(elem, pf.RawBlock) and elem.format == sample.format and elem.text == sample.text


def _parse_levels(value: Any, ctx: FilterContext, template_levels: set[int]) -> set[int]:
    """Valid heading names become levels; a bad value falls back to the template, bad names drop individually."""
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list):
        ctx.report.warn(Codes.TEMPLATE_INVALID, _WARN_MESSAGE, once=True, key="page_break")
        return template_levels
    levels: set[int] = set()
    for item in items:
        name = str(item).strip().lower()
        if name in _LEVELS:
            levels.add(_LEVELS[name])
        else:
            ctx.report.warn(Codes.TEMPLATE_INVALID, _WARN_MESSAGE, once=True, key="page_break")
    if items and not levels:
        # every name was invalid: keep the template's levels instead of disabling heading breaks
        return template_levels
    return levels


def _settings(ctx: FilterContext) -> tuple[set[int], bool]:
    template = ctx.config["layout"]["page_break"]
    template_levels = _parse_levels(template.get("before") or [], ctx, set())
    skip_first = bool(template.get("skip_first", True))
    override = ctx.frontmatter.get("page_break")
    if override is None:
        return template_levels, skip_first
    if isinstance(override, dict):
        levels = template_levels
        if "before" in override:
            levels = _parse_levels(override["before"], ctx, template_levels)
        if "skip_first" in override:
            if isinstance(override["skip_first"], bool):
                skip_first = override["skip_first"]
            else:
                ctx.report.warn(Codes.TEMPLATE_INVALID, _WARN_MESSAGE, once=True, key="page_break")
        return levels, skip_first
    if isinstance(override, (list, str)):
        return _parse_levels(override, ctx, template_levels), skip_first
    ctx.report.warn(Codes.TEMPLATE_INVALID, _WARN_MESSAGE, once=True, key="page_break")
    return template_levels, skip_first


def apply(doc: pf.Doc, ctx: FilterContext) -> pf.Doc:
    levels, skip_first = _settings(ctx)
    out: list[pf.Element] = []
    seen_rule_heading = False

    def add_break() -> None:
        if out and not _is_break(out[-1], ctx.target):
            out.append(break_block(ctx.target))

    for block in doc.content:
        if is_marker(block):
            add_break()
            continue
        if isinstance(block, pf.Header) and block.level in levels:
            if seen_rule_heading or not skip_first:
                add_break()
            seen_rule_heading = True
        out.append(block)
    doc.content = out
    return doc
