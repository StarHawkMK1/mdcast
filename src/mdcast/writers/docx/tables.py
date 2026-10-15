from __future__ import annotations

import copy
from typing import Any

from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from mdcast.filters.tables import table_settings
from mdcast.report import Codes, Report
from mdcast.templates.schema import deep_merge
from mdcast.units import normalize_color, parse_length_mm, parse_pt
from mdcast.writers.docx.xml import (
    BORDER_ORDER,
    MAR_ORDER,
    RPR_ORDER,
    STYLE_ORDER,
    TBLPR_ORDER,
    TCPR_ORDER,
    half_points,
    mm_to_twips,
    pt_to_eighths,
    remove_all,
    upsert,
)

_VALIGN = {"top": "top", "middle": "center", "bottom": "bottom"}
_MISSING = object()


def _border(parent, side: str, width: Any, color: Any) -> None:
    upsert(
        parent,
        f"w:{side}",
        BORDER_ORDER,
        val="single",
        sz=pt_to_eighths(parse_pt(width)),
        space=0,
        color=normalize_color(color) or "000000",
    )


def _conditional(style_el, kind: str, background: Any = _MISSING, valign: Any = _MISSING) -> None:
    """Write the ``kind`` conditional format; a ``None`` background clears an inherited fill."""
    element = next((p for p in style_el.findall(qn("w:tblStylePr")) if p.get(qn("w:type")) == kind), None)
    if element is None:
        element = OxmlElement("w:tblStylePr")
        element.set(qn("w:type"), kind)
        style_el.append(element)
    tcpr = element.find(qn("w:tcPr"))
    if tcpr is None:
        tcpr = OxmlElement("w:tcPr")
        element.append(tcpr)
    if background is not _MISSING:
        remove_all(tcpr, "w:shd")
        if background:
            upsert(tcpr, "w:shd", TCPR_ORDER, val="clear", color="auto", fill=normalize_color(background))
    if valign not in (_MISSING, None):
        upsert(tcpr, "w:vAlign", TCPR_ORDER, val=_VALIGN.get(str(valign), "top"))
    if not len(tcpr):
        style_el.remove(element)


def _configure_style(style_el, s: dict[str, Any]) -> None:
    """Apply the keys present in ``s`` (a full table config, or only a part of one)."""
    border, outer = s.get("border") or {}, s.get("border_outer") or {}
    header, body, first = s.get("header") or {}, s.get("body") or {}, s.get("first_column") or {}
    tblpr = upsert(style_el, "w:tblPr", STYLE_ORDER)
    if border.get("width") is not None or outer.get("width") is not None:
        upsert(tblpr, "w:tblStyleRowBandSize", TBLPR_ORDER, val=1)
        borders = upsert(tblpr, "w:tblBorders", TBLPR_ORDER)
        inner_color = border.get("color")
        outer_color = outer.get("color") or inner_color
        if outer.get("width") is not None:
            for side in ("top", "left", "bottom", "right"):
                _border(borders, side, outer["width"], outer_color)
        if border.get("width") is not None:
            for side in ("insideH", "insideV"):
                _border(borders, side, border["width"], inner_color)
    if s.get("cell_padding") is not None:
        margins = upsert(tblpr, "w:tblCellMar", TBLPR_ORDER)
        pad = mm_to_twips(parse_length_mm(s["cell_padding"]))
        for side in ("top", "left", "bottom", "right"):
            upsert(margins, f"w:{side}", MAR_ORDER, w=pad, type="dxa")
    if s.get("font_size") is not None:
        rpr = upsert(style_el, "w:rPr", STYLE_ORDER)
        size = half_points(parse_pt(s["font_size"]))
        upsert(rpr, "w:sz", RPR_ORDER, val=size)
        upsert(rpr, "w:szCs", RPR_ORDER, val=size)
    if body.get("valign") is not None:
        tcpr = upsert(style_el, "w:tcPr", STYLE_ORDER)
        upsert(tcpr, "w:vAlign", TCPR_ORDER, val=_VALIGN.get(str(body["valign"]), "top"))
    if "background" in header or header.get("valign") is not None:
        _conditional(style_el, "firstRow", header.get("background", _MISSING), header.get("valign"))
    if "zebra" in body:
        _conditional(style_el, "band2Horz", body["zebra"])
    if "background" in first:
        _conditional(style_el, "firstCol", first["background"])


def _tr_pr(tr):
    trpr = tr.find(qn("w:trPr"))
    if trpr is None:
        trpr = OxmlElement("w:trPr")
        index = 1 if len(tr) and tr[0].tag == qn("w:tblPrEx") else 0
        tr.insert(index, trpr)
    return trpr


def apply_tables(
    d,
    config: dict[str, Any],
    explicit: dict[str, Any] | None,
    records: list[dict[str, Any]],
    report: Report,
) -> None:
    """Style tables.

    ``explicit`` is the template-written part of the config when a custom reference.docx is in
    use (its own table style wins for everything else); ``None`` means the built-in container,
    which gets the full config. Variants and header-row features always apply.
    """
    names = {s.name for s in d.styles}
    base_name = (config["styles"].get("table") or {}).get("docx") or "Table"
    if base_name not in names:
        if base_name != "Table":
            report.info(
                Codes.STYLE_UNMAPPED,
                f"docx 기준 문서에 표 스타일 '{base_name}' 이(가) 없어 'Table' 을 씁니다",
                format="docx",
                element="table",
            )
        base_name = "Table"
        if "Table" not in names:
            d.styles.add_style("Table", WD_STYLE_TYPE.TABLE)
    base = d.styles[base_name]
    variants = config["tables"].get("variants") or {}

    def style_look(variant: str | None) -> dict[str, Any]:
        """What the table style gets: the full config, or only what the template set."""
        if explicit is None:
            return table_settings(config, variant)
        partial = {k: v for k, v in (explicit.get("tables") or {}).items() if k != "variants"}
        overrides = variants.get(variant) if variant else None
        return deep_merge(partial, overrides) if overrides else partial

    _configure_style(base.element, style_look(None))

    # body pre-order, matching the filter's records (footnote tables are not in the body)
    tables = list(d.element.body.iter(qn("w:tbl")))
    if len(tables) != len(records):
        report.warn(
            Codes.STYLE_UNMAPPED,
            f"문서의 표 {len(tables)}개와 변환 기록 {len(records)}개가 맞지 않아 표 종류·머리글 반복을 적용하지 않습니다",
            format="docx",
            element="table",
        )
        records = [{"variant": None, "head_rows": 0} for _ in tables]
    style_ids: dict[str, str] = {}
    for index, variant in enumerate(sorted({r["variant"] for r in records if r["variant"]}), start=1):
        element = copy.deepcopy(base.element)
        style_id = f"MdcastTable{index}"
        element.set(qn("w:styleId"), style_id)
        element.attrib.pop(qn("w:default"), None)
        element.find(qn("w:name")).set(qn("w:val"), f"Table ({variant})")
        d.styles.element.append(element)
        # the copy already carries the base look; a custom container only needs the variant's overrides
        _configure_style(element, table_settings(config, variant) if explicit is None else variants.get(variant) or {})
        style_ids[variant] = style_id

    for tbl, record in zip(tables, records):
        # header repeat follows I2 (per-table content feature); width=full is my judgement call in the same spirit
        s = table_settings(config, record["variant"])
        look = style_look(record["variant"])
        tblpr = tbl.find(qn("w:tblPr"))
        if tblpr is None:
            tblpr = OxmlElement("w:tblPr")
            tbl.insert(0, tblpr)
        upsert(tblpr, "w:tblStyle", TBLPR_ORDER, val=style_ids[record["variant"]] if record["variant"] else base.style_id)
        look_el = upsert(tblpr, "w:tblLook", TBLPR_ORDER)
        look_el.attrib.pop(qn("w:val"), None)
        flags = {
            "firstRow": "1",
            "lastRow": "0",
            "firstColumn": "1" if (look.get("first_column") or {}).get("background") else "0",
            "lastColumn": "0",
            "noHBand": "0" if (look.get("body") or {}).get("zebra") else "1",
            "noVBand": "1",
        }
        for key, value in flags.items():
            look_el.set(qn(f"w:{key}"), value)
        if s.get("width") == "full":
            upsert(tblpr, "w:tblW", TBLPR_ORDER, w=5000, type="pct")
        for tr in tbl.findall(qn("w:tr"))[: record["head_rows"]]:
            trpr = _tr_pr(tr)
            remove_all(trpr, "w:tblHeader")
            if s["header"].get("repeat"):
                upsert(trpr, "w:tblHeader", None, val="true")
