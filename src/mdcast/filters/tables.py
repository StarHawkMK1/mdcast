from __future__ import annotations

import re
from typing import Any

import panflute as pf

from mdcast.ast import grid_cells
from mdcast.filters._raw import raw_block
from mdcast.filters.context import FilterContext
from mdcast.report import Codes
from mdcast.templates.schema import deep_merge
from mdcast.types import Format

_VARIANT = re.compile(r"^\s*<!--\s*table\s*:\s*([\w\-가-힣]+)\s*-->\s*$", re.IGNORECASE)
_ALIGN = {"left": "AlignLeft", "center": "AlignCenter", "right": "AlignRight"}


def table_settings(config: dict[str, Any], variant: str | None) -> dict[str, Any]:
    base = {k: v for k, v in config["tables"].items() if k != "variants"}
    overrides = (config["tables"].get("variants") or {}).get(variant) if variant else None
    return deep_merge(base, overrides) if overrides else base


def _embolden(cell: pf.TableCell) -> None:
    for block in cell.content:
        if isinstance(block, (pf.Plain, pf.Para)) and block.content:
            inlines = list(block.content)
            if len(inlines) == 1 and isinstance(inlines[0], pf.Strong):
                continue
            block.content = [pf.Strong(*inlines)]


def _full_widths(colspec: list[tuple[str, Any]]) -> list[Any]:
    """Fractions summing to 1; a column without one gets the others' mean (grid tables give ~0.65)."""
    given = [w for _, w in colspec if isinstance(w, (int, float)) and w > 0]
    mean = sum(given) / len(given) if given else 1.0
    filled = [w if isinstance(w, (int, float)) and w > 0 else mean for _, w in colspec]
    total = sum(filled) or 1.0
    return [w / total for w in filled]


def _style(table: pf.Table, settings: dict[str, Any]) -> None:
    body_align = _ALIGN.get(settings["body"].get("align"), "AlignDefault")
    widths = (
        _full_widths(table.colspec) if settings.get("width") == "full" else [w for _, w in table.colspec]
    )
    table.colspec = [
        (body_align if align == "AlignDefault" else align, width)
        for (align, _), width in zip(table.colspec, widths)
    ]
    header_align = _ALIGN.get(settings["header"].get("align"))
    for row in table.head.content:
        for cell in row.content:
            if header_align:
                cell.alignment = header_align
            if settings["header"].get("bold"):
                _embolden(cell)
    if settings["first_column"].get("bold"):
        for body in table.content:
            for cell in first_column_cells(list(body.content)):
                _embolden(cell)


def first_column_cells(rows: list[pf.TableRow]) -> list[pf.TableCell]:
    """Cells that start in grid column 0; a row whose column 0 is covered by a rowspan has none."""
    return [cell for cell, col in grid_cells(rows) if col == 0]


def _in_footnote(elem: pf.Element) -> bool:
    parent = elem.parent
    while parent is not None:
        if isinstance(parent, pf.Note):
            return True
        parent = parent.parent
    return False


def _variant_marker(block: pf.Element) -> str | None:
    if isinstance(block, pf.RawBlock) and block.format == "html":
        match = _VARIANT.match(block.text)
        if match:
            return match.group(1)
    return None


def _drop_pending(ctx: FilterContext, name: str) -> None:
    ctx.report.info(Codes.TABLE_VARIANT_UNKNOWN, f"표 종류 표시 '{name}' 다음에 표가 없어 무시합니다", variant=name)


def apply(doc: pf.Doc, ctx: FilterContext) -> pf.Doc:
    known = ctx.config["tables"].get("variants") or {}
    out: list[pf.Element] = []
    variant_of: dict[int, str | None] = {}
    pending: str | None = None

    for block in doc.content:
        marker = _variant_marker(block)
        if marker is not None:
            if pending is not None:
                _drop_pending(ctx, pending)
            pending = marker
            continue
        if isinstance(block, pf.Table):
            variant = None
            if pending is not None:
                if pending in known:
                    variant = pending
                else:
                    ctx.report.info(Codes.TABLE_VARIANT_UNKNOWN, f"표 종류 '{pending}' 이(가) 템플릿에 없어 기본 표 스타일을 씁니다", variant=pending)
                pending = None
            _style(block, table_settings(ctx.config, variant))
            variant_of[id(block)] = variant
            if ctx.target is Format.HWPX and variant:
                block.attributes["mdcast-variant"] = variant
            head_rows = len(block.head.content)
            if ctx.target is Format.PDF:
                out.append(raw_block(f'#mdcast-table(cfg, "{variant or "_default"}", {head_rows})[', "typst"))
                out.append(block)
                out.append(raw_block("]", "typst"))
                continue
        elif pending is not None:
            _drop_pending(ctx, pending)
            pending = None
        out.append(block)
    if pending is not None:
        _drop_pending(ctx, pending)
    doc.content = out

    default_settings = table_settings(ctx.config, None)
    records: list[dict[str, Any]] = []

    def collect(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.Table):
            if id(elem) not in variant_of:
                _style(elem, default_settings)
            if _in_footnote(elem):
                return  # footnote tables go to footnotes.xml: styled by default, but not collected
            # Known limitation: a table inside a table cell is recorded post-order (inner first), docx is pre-order.
            records.append({"variant": variant_of.get(id(elem)), "head_rows": len(elem.head.content)})

    doc.walk(collect)
    ctx.state["tables"] = records
    return doc
