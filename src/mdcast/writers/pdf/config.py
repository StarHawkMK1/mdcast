from __future__ import annotations

import importlib.metadata
from typing import Any

from mdcast import __version__
from mdcast.ast import pandoc_version
from mdcast.counters import typst_pattern
from mdcast.fields import PageField, ResolvedFields
from mdcast.filters.tables import table_settings
from mdcast.fonts import family_chain
from mdcast.report import Codes, Report
from mdcast.templates import ResolvedTemplate
from mdcast.units import normalize_color, page_size_mm, parse_length_mm, parse_pt, parse_ratio

ELEMENT_KEYS = ("body", "quote", "code", "caption", "footnote", *(f"heading{i}" for i in range(1, 7)))


def _pt(value: Any) -> float | None:
    return None if value is None else round(parse_pt(value), 3)


def _mm(value: Any) -> float | None:
    return None if value is None else round(parse_length_mm(value), 3)


def _color(value: Any) -> str | None:
    color = normalize_color(value)
    return None if color is None else f"#{color}"


def _leading(line_height: Any) -> float:
    """Approximate Word's "multiple" line spacing as Typst paragraph leading (em)."""
    if line_height is None:
        return 0.65
    return max(0.2, round(parse_ratio(line_height) * 1.2 - 1.0, 3))


def _element(look: dict[str, Any]) -> dict[str, Any]:
    return {
        "size": _pt(look.get("size")),
        "bold": look.get("bold"),
        "italic": look.get("italic"),
        "color": _color(look.get("color")),
        "align": look.get("align"),
        "leading": _leading(look.get("line_height")),
        "space_before": _pt(look.get("space_before")) or 0.0,
        "space_after": _pt(look.get("space_after")) or 0.0,
        "indent_left": _mm(look.get("indent_left")) or 0.0,
        "background": _color(look.get("background")),
    }


def _segments(fields: ResolvedFields, template: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for seg in fields.render(template):
        if isinstance(seg, PageField):
            out.append({"t": seg.kind})
        else:
            out.append({"t": "text", "v": seg.value})
    return out


def _slots(spec: dict[str, Any], fields: ResolvedFields) -> dict[str, Any]:
    return {
        "left": _segments(fields, spec.get("left") or ""),
        "center": _segments(fields, spec.get("center") or ""),
        "right": _segments(fields, spec.get("right") or ""),
        "line": spec.get("line") or "none",
    }


def _table(s: dict[str, Any]) -> dict[str, Any]:
    inner_color = _color(s["border"].get("color")) or "#000000"
    return {
        "font_size": _pt(s["font_size"]),
        "cell_padding": _mm(s["cell_padding"]),
        "border": {"width": _pt(s["border"]["width"]), "color": inner_color},
        "border_outer": {
            "width": _pt(s["border_outer"]["width"]),
            "color": _color(s["border_outer"].get("color")) or inner_color,
        },
        "header": {"background": _color(s["header"].get("background")), "repeat": bool(s["header"].get("repeat"))},
        "body": {"zebra": _color(s["body"].get("zebra"))},
        "first_column": {"background": _color(s["first_column"].get("background"))},
        "caption": {"position": s["caption"].get("position") or "above"},
    }


def build_typst_config(tpl: ResolvedTemplate, fields: ResolvedFields, report: Report) -> dict[str, Any]:
    c = tpl.config
    if "reference" in (c["header"].get("source"), c["footer"].get("source")):
        report.warn(
            Codes.PDF_HEADER_SIMPLIFIED,
            "PDF 는 기준 문서의 머리말/꼬리말을 쓸 수 없어 yaml 칸 정의로 단순화해 그렸습니다",
            format="pdf",
        )
    width, height = page_size_mm(c["page"]["size"], c["page"]["orientation"])
    tables = {"_default": _table(table_settings(c, None))}
    for name in c["tables"].get("variants") or {}:
        tables[str(name)] = _table(table_settings(c, str(name)))
    return {
        "document": {
            "title": fields.values.get("title") or None,
            "keywords": [
                "mdcast",
                f"mdcast:{__version__}",
                f"pandoc:{pandoc_version()}",
                f"typst:{importlib.metadata.version('typst')}",
                f"template:{tpl.name}",
                f"template-version:{tpl.version}",
                f"template-source:{tpl.source}",
            ],
        },
        "page": {
            "width": width,
            "height": height,
            "margin": {side: _mm(value) for side, value in c["page"]["margin"].items()},
        },
        "fonts": {role: family_chain(c["fonts"][role]) for role in ("body", "heading", "code")},
        "elements": {key: _element(c["elements"].get(key) or {}) for key in ELEMENT_KEYS},
        "lists": {
            "bullet": [str(b) for b in c["lists"]["bullet"]],
            "ordered": [typst_pattern(str(p)) for p in c["lists"]["ordered"]],
            "indent": _mm(c["lists"]["indent_per_level"]),
        },
        "tables": tables,
        "figures": {"caption": {"position": c["figures"]["caption"].get("position") or "below"}},
        "header": _slots(c["header"], fields),
        "footer": _slots(c["footer"], fields),
    }
