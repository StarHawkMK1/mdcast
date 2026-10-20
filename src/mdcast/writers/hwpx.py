"""hwpx writer adapter: template config → hwpx.Settings, notices → report (spec §4.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import panflute as pf

from mdcast import hwpx
from mdcast.counters import format_counter
from mdcast.fields import PageField, ResolvedFields
from mdcast.filters.tables import table_settings
from mdcast.report import Codes
from mdcast.units import normalize_color, page_size_mm, parse_length_mm, parse_pt, parse_ratio
from mdcast.writers.context import RenderError, WriterContext
from mdcast.writers.generator import generator_values

# what the PDF uses where the built-in template leaves a key empty (spec §4.3), so Hangul's
# blank-document defaults (outline indents, justified text, …) do not leak into the output
NEUTRAL = {
    "bold": False, "italic": False, "color": "#000000", "align": "left", "line_height": 1.3,
    "space_before": 0.0, "space_after": 0.0, "indent_left": 0.0, "keep_with_next": False,
}


def _role(element: str) -> str:
    if element.startswith("heading"):
        return "heading"
    return "code" if element == "code" else "body"


def _color(value: Any) -> str | None:
    color = normalize_color(value)
    return None if color is None else f"#{color}"


def _look(values: dict[str, Any], family: Any, neutral: bool, family_hangul: Any = None) -> hwpx.Look:
    def get(key: str, convert):
        value = values.get(key)
        return None if value is None else convert(value)

    look = {
        "font": str(family) if family else None,
        "font_hangul": str(family_hangul) if family_hangul else None,
        "size": get("size", parse_pt),
        "bold": get("bold", bool),
        "italic": get("italic", bool),
        "color": get("color", _color),
        "align": get("align", str),
        "line_height": get("line_height", parse_ratio),
        "space_before": get("space_before", parse_pt),
        "space_after": get("space_after", parse_pt),
        "indent_left": get("indent_left", parse_length_mm),
        "background": get("background", _color),
        "keep_with_next": get("keep_with_next", bool),
    }
    if neutral:
        look.update({key: value for key, value in NEUTRAL.items() if look[key] is None})
    return hwpx.Look(**look)


def _pieces(fields: ResolvedFields, text: str) -> list[hwpx.Piece]:
    return [hwpx.PageNumber(s.kind) if isinstance(s, PageField) else s.value for s in fields.render(text)]


def _slots(spec: dict[str, Any], fields: ResolvedFields) -> hwpx.Slots | None:
    if spec.get("source") == "reference":
        return None

    def slot(key: str) -> tuple[hwpx.Piece, ...]:
        return tuple(_pieces(fields, str(spec.get(key) or "")))

    return hwpx.Slots(slot("left"), slot("center"), slot("right"), str(spec.get("line") or "none"))


def _page(page: dict[str, Any]) -> hwpx.PageSetup:
    width = height = None
    if page.get("size") is not None:
        width, height = page_size_mm(str(page["size"]), "portrait")
    margin = page.get("margin") or {}

    def mm(key: str) -> float | None:
        value = margin.get(key)
        return None if value is None else parse_length_mm(value)

    orientation = page.get("orientation")
    return hwpx.PageSetup(
        width=width, height=height, landscape=None if orientation is None else orientation == "landscape",
        top=mm("top"), bottom=mm("bottom"), left=mm("left"), right=mm("right"),
    )


def _border(values: dict[str, Any] | None, default: hwpx.Border) -> hwpx.Border:
    values = values or {}
    width = values.get("width")
    return hwpx.Border(
        default.width if width is None else parse_pt(width),
        _color(values.get("color")) or default.color,
    )


def _table_look(values: dict[str, Any]) -> hwpx.TableLook:
    """One table kind from ``table_settings(config, variant)`` (spec 2026-10-20 §4.4)."""
    default = hwpx.TableLook()
    header, body = values.get("header") or {}, values.get("body") or {}
    first = values.get("first_column") or {}

    def get(source: dict[str, Any], key: str, convert, fallback):
        value = source.get(key)
        return fallback if value is None else convert(value)

    return hwpx.TableLook(
        width=str(values.get("width") or default.width),
        font_size=get(values, "font_size", parse_pt, None),
        line_height=get(values, "line_height", parse_ratio, None),
        padding=get(values, "cell_padding", parse_length_mm, default.padding),
        border=_border(values.get("border"), default.border),
        border_outer=_border(values.get("border_outer"), default.border_outer),
        header_background=_color(header.get("background")),
        header_valign=str(header.get("valign") or default.header_valign),
        header_repeat=bool(get(header, "repeat", bool, default.header_repeat)),
        body_valign=str(body.get("valign") or default.body_valign),
        zebra=_color(body.get("zebra")),
        first_column_background=_color(first.get("background")),
    )


def _figure_limit(value: Any) -> tuple[float | None, float | None]:
    """``figures.max_width`` as (ratio of the available width, length in mm); one of them is set."""
    if value is None:
        return 1.0, None
    if str(value).strip().endswith("%"):
        return parse_ratio(value), None
    return None, parse_length_mm(value)


def _settings(ctx: WriterContext, custom: bool) -> hwpx.Settings:
    config = ctx.template.config
    values = ctx.template.explicit if custom else config
    elements = values.get("elements") or {}
    fonts = values.get("fonts") or {}
    body_family = (fonts.get("body") or {}).get("family")
    looks = {
        element: _look(
            elements.get(element) or {},
            (fonts.get(_role(element)) or {}).get("family"),
            not custom,
            # Hangul text in code: the body face, as Word shows it (a Latin code face has no Hangul)
            body_family if element == "code" else None,
        )
        for element in hwpx.ELEMENTS
    }
    styles = {
        element: str(mapping["hwpx"])
        for element, mapping in (config.get("styles") or {}).items()
        if isinstance(mapping, dict) and mapping.get("hwpx")
    }
    lists = config["lists"]
    bullets = [str(b) for b in lists["bullet"]] or ["-"]
    ordered = [str(o) for o in lists["ordered"]] or ["1."]

    def marker(is_ordered: bool, level: int, n: int) -> str:
        if is_ordered:
            return format_counter(ordered[min(level, len(ordered)) - 1], n)
        return bullets[min(level, len(bullets)) - 1]

    body = config["elements"]["body"]
    # hwpx has no container table style to keep: the full config applies, custom container or not
    tables = {
        variant: _table_look(table_settings(config, variant))
        for variant in [None, *(config["tables"].get("variants") or {})]
    }
    figures = config["figures"]
    max_ratio, max_mm = _figure_limit(figures.get("max_width"))
    return hwpx.Settings(
        looks=looks,
        styles=styles,
        page=_page(values.get("page") or {}),
        header=_slots(config["header"], ctx.fields),
        footer=_slots(config["footer"], ctx.fields),
        fill=lambda text: _pieces(ctx.fields, text),
        list_marker=marker,
        list_indent=parse_length_mm(lists["indent_per_level"]),
        body_size=parse_pt(body.get("size") or "11pt"),
        body_line_height=parse_ratio(body["line_height"]) if body.get("line_height") is not None else 1.3,
        table_caption_above=(config["tables"]["caption"].get("position") or "above") == "above",
        figure_caption_above=(config["figures"]["caption"].get("position") or "below") == "above",
        metadata=hwpx.Metadata(
            title=ctx.fields.values.get("title", ""),
            author=ctx.fields.values.get("author", ""),
            keywords="mdcast",
            created=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            extra=tuple(generator_values(ctx.generator).items()),
        ),
        tables=tables,
        figure_max_ratio=max_ratio,
        figure_max_mm=max_mm,
        figure_align=str(figures.get("align") or "center"),
    )


def _write(doc: pf.Doc, container: bytes, ctx: WriterContext, custom: bool) -> bytes:
    data, notices = hwpx.write(doc, container, _settings(ctx, custom))
    for notice in notices:
        if notice.kind == "style-missing":
            ctx.report.info(Codes.STYLE_UNMAPPED, notice.message, format="hwpx", element=notice.element)
        else:
            ctx.report.warn(Codes.RENDER_WARNING, notice.message, format="hwpx", element=notice.element)
    return data


def write_hwpx(doc: pf.Doc, ctx: WriterContext) -> bytes:
    container = ctx.template.container_for("hwpx")
    if container.source == "custom" and container.path is not None:
        try:
            return _write(doc, container.path.read_bytes(), ctx, custom=True)
        except Exception as exc:  # noqa: BLE001 - any odd container: the built-in one still works
            ctx.report.warn(
                Codes.TEMPLATE_INVALID,
                f"커스텀 reference.hwpx 를 쓸 수 없어 내장 그릇으로 변환합니다: {exc}",
                format="hwpx",
            )
    builtin = ctx.template.builtin_container("hwpx")
    try:
        return _write(doc, builtin.path.read_bytes(), ctx, custom=False)
    except (hwpx.ContainerError, OSError) as exc:
        raise RenderError(f"내장 hwpx 그릇을 쓸 수 없습니다: {exc}") from exc
