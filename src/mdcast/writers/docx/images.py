"""Picture sizes: the rule hwpx uses (spec 2026-10-20 §5.2), against the room the picture really has.

pandoc sizes every picture against its own reference page (148mm wide) before mdcast sets the
page, and ignores the table cell a picture sits in: a picture in a cell spilled out of it, a
wide one stopped short of the body width, and ``{width=40%}`` meant 40% of 148mm.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import panflute as pf
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn
from lxml import etree

from mdcast.hwpx.look import Image
from mdcast.hwpx.picture import picture_size
from mdcast.units import page_size_mm, parse_length_mm
from mdcast.writers.images import figure_limit, image_info

_EMU_PER_MM = 36000
_TWIPS_PER_MM = 1440 / 25.4
_CELL_MARGIN = 108  # twips: Word's left and right cell margin when nothing sets one
_MIN_ROOM_MM = 10.0


@dataclass(frozen=True)
class Request:
    image: Image | None  # None: a format mdcast cannot measure (TIFF, EMF, ...): keep pandoc's size
    width: str | None
    height: str | None


def picture_requests(doc: pf.Doc, work_dir: Path) -> dict[str, Request]:
    """What each picture asks for, by its ``assets/...`` url (``localize_images`` names each one apart).

    pandoc writes that url into the picture's ``pic:cNvPr/@descr``.
    """
    requests: dict[str, Request] = {}

    def collect(elem: pf.Element, _doc: pf.Doc) -> None:
        if isinstance(elem, pf.Image) and elem.url not in requests:
            try:
                # a raster image that does not give its dpi is taken at 96, as Word places it
                # (pandoc would take 72)
                kind, width, height, dpi = image_info((work_dir / elem.url).read_bytes())
                image = Image(b"", kind, width, height, dpi)
            except (OSError, ValueError):
                image = None
            requests[elem.url] = Request(
                image, elem.attributes.get("width"), elem.attributes.get("height")
            )

    doc.walk(collect)
    return requests


def _twips(element, name: str) -> int:
    try:
        return int(element.get(qn(f"w:{name}")) or 0)
    except ValueError:
        return 0


class _Room:
    """mm a picture may take where it sits: its cell or the body, less its paragraph's indents."""

    def __init__(self, d, body_mm: float) -> None:
        self.body_mm = body_mm
        self.styles = {s.get(qn("w:styleId")): s for s in d.styles.element.findall(qn("w:style"))}
        self.default_style = next(
            (
                s.get(qn("w:styleId"))
                for s in self.styles.values()
                if s.get(qn("w:type")) == "paragraph" and s.get(qn("w:default")) in ("1", "true")
            ),
            None,
        )
        self.numbering = d.part.numbering_part.element

    def _chain(self, style_id: str | None):
        """The style and the ones it is based on."""
        seen: set[str] = set()
        while style_id is not None and style_id not in seen and style_id in self.styles:
            seen.add(style_id)
            yield self.styles[style_id]
            based = self.styles[style_id].find(qn("w:basedOn"))
            style_id = None if based is None else based.get(qn("w:val"))

    @staticmethod
    def _style_id(owner, props: str, style: str) -> str | None:
        ref = owner.find(f"{qn(props)}/{qn(style)}")
        return None if ref is None else ref.get(qn("w:val"))

    def __call__(self, inline) -> float:
        p = next(inline.iterancestors(qn("w:p")), None)
        tc = next(inline.iterancestors(qn("w:tc")), None)
        outer = self.cell(tc) if tc is not None else self.body_mm
        return max(outer - self.indents(p), _MIN_ROOM_MM) if p is not None else outer

    def indents(self, p) -> float:
        """Left plus right indent of ``p`` in mm: direct, its list level, then its style chain."""
        ppr = p.find(qn("w:pPr"))
        sources = [] if ppr is None else [ppr]
        num = None if ppr is None else ppr.find(qn("w:numPr"))
        style_id = self._style_id(p, "w:pPr", "w:pStyle") or self.default_style
        if num is None:  # a list style puts numPr in the style
            num = next(
                (
                    s.find(f"{qn('w:pPr')}/{qn('w:numPr')}")
                    for s in self._chain(style_id)
                    if s.find(f"{qn('w:pPr')}/{qn('w:numPr')}") is not None
                ),
                None,
            )
        level = self._level(num)
        if level is not None:
            sources.append(level)
        sources += [s.find(qn("w:pPr")) for s in self._chain(style_id)]
        left = right = None
        for props in sources:
            ind = None if props is None else props.find(qn("w:ind"))
            if ind is None:
                continue
            if left is None and (ind.get(qn("w:left")) or ind.get(qn("w:start"))) is not None:
                left = _twips(ind, "left") or _twips(ind, "start")
            if right is None and (ind.get(qn("w:right")) or ind.get(qn("w:end"))) is not None:
                right = _twips(ind, "right") or _twips(ind, "end")
        return ((left or 0) + (right or 0)) / _TWIPS_PER_MM

    def _level(self, num_pr):
        """The list level's ``w:pPr`` in numbering.xml."""
        if num_pr is None or self.numbering is None:
            return None
        num_id = num_pr.find(qn("w:numId"))
        ilvl = num_pr.find(qn("w:ilvl"))
        if num_id is None:
            return None
        num = next(
            (
                n
                for n in self.numbering.findall(qn("w:num"))
                if n.get(qn("w:numId")) == num_id.get(qn("w:val"))
            ),
            None,
        )
        abstract_id = None if num is None else num.find(qn("w:abstractNumId"))
        if abstract_id is None:
            return None
        abstract = next(
            (
                a
                for a in self.numbering.findall(qn("w:abstractNum"))
                if a.get(qn("w:abstractNumId")) == abstract_id.get(qn("w:val"))
            ),
            None,
        )
        wanted = "0" if ilvl is None else ilvl.get(qn("w:val"))
        lvl = (
            None
            if abstract is None
            else next(
                (lv for lv in abstract.findall(qn("w:lvl")) if lv.get(qn("w:ilvl")) == wanted), None
            )
        )
        return None if lvl is None else lvl.find(qn("w:pPr"))

    def cell(self, tc) -> float:
        """The cell's text width in mm: its share of the table's grid, less its margins."""
        tbl = next(tc.iterancestors(qn("w:tbl")))
        parent = next(tbl.iterancestors(qn("w:tc")), None)
        room = self.cell(parent) if parent is not None else self.body_mm
        tblpr = tbl.find(qn("w:tblPr"))
        tblw = None if tblpr is None else tblpr.find(qn("w:tblW"))
        kind = None if tblw is None else tblw.get(qn("w:type"))
        if kind == "pct":
            width = room * _twips(tblw, "w") / 5000
        elif kind == "dxa":
            width = _twips(tblw, "w") / _TWIPS_PER_MM
        else:  # auto: pandoc splits the grid evenly; take that share of the room
            width = room
        grid_el = tbl.find(qn("w:tblGrid"))
        grid = [] if grid_el is None else [_twips(g, "w") for g in grid_el.findall(qn("w:gridCol"))]
        col, span = self._grid_position(tc)
        if sum(grid) > 0:
            share = sum(grid[col : col + span]) / sum(grid)
        else:
            share = span / max(len(grid), 1)
        left, right = self._cell_margins(tc, tbl)
        return width * share - (left + right) / _TWIPS_PER_MM

    @staticmethod
    def _grid_position(tc) -> tuple[int, int]:
        def span(cell) -> int:
            el = cell.find(f"{qn('w:tcPr')}/{qn('w:gridSpan')}")
            return max(_twips(el, "val"), 1) if el is not None else 1

        tr = tc.getparent()
        before = tr.find(f"{qn('w:trPr')}/{qn('w:gridBefore')}")
        col = _twips(before, "val") if before is not None else 0
        for cell in tr.findall(qn("w:tc")):
            if cell is tc:
                break
            col += span(cell)
        return col, span(tc)

    def _cell_margins(self, tc, tbl) -> tuple[int, int]:
        """Left and right margin in twips: the cell's own, the table's, its style chain's, Word's."""
        containers = [
            tc.find(f"{qn('w:tcPr')}/{qn('w:tcMar')}"),
            tbl.find(f"{qn('w:tblPr')}/{qn('w:tblCellMar')}"),
        ]
        containers += [
            s.find(f"{qn('w:tblPr')}/{qn('w:tblCellMar')}")
            for s in self._chain(self._style_id(tbl, "w:tblPr", "w:tblStyle"))
        ]

        def side(*names: str) -> int:
            for margins in containers:
                for name in names:
                    el = None if margins is None else margins.find(qn(f"w:{name}"))
                    if el is not None:
                        return _twips(el, "w")
            return _CELL_MARGIN

        return side("left", "start"), side("right", "end")


def _fit(
    root, requests: dict[str, Request], room: _Room, limit: tuple[float | None, float | None]
) -> bool:
    changed = False
    for inline in root.iter(qn("wp:inline")):
        extent = inline.find(qn("wp:extent"))
        ext = inline.find(f".//{qn('a:xfrm')}/{qn('a:ext')}")
        name = inline.find(f".//{qn('pic:cNvPr')}")
        if extent is None or name is None:
            continue
        available = room(inline)
        request = requests.get(name.get("descr") or "")
        if request is not None and request.image is not None:
            width, height = picture_size(
                request.image, request.width, request.height, available, *limit
            )
        else:
            width, height = (
                int(extent.get("cx") or 0) / _EMU_PER_MM,
                int(extent.get("cy") or 0) / _EMU_PER_MM,
            )
            if width > available:
                width, height = available, height * available / width
        for element in (extent, ext):
            if element is not None:
                element.set("cx", str(round(width * _EMU_PER_MM)))
                element.set("cy", str(round(height * _EMU_PER_MM)))
        changed = True
    return changed


def _body_mm(section, config: dict[str, Any]) -> float:
    """The body width; a key the section leaves out (a custom container may) comes from the config."""
    page = config["page"]
    margin = page.get("margin") or {}

    def mm(value, fallback) -> float:
        return value / _EMU_PER_MM if value is not None else fallback()

    width = mm(section.page_width, lambda: page_size_mm(page["size"], page["orientation"])[0])
    left = mm(section.left_margin, lambda: parse_length_mm(margin["left"]))
    right = mm(section.right_margin, lambda: parse_length_mm(margin["right"]))
    return width - left - right


def fit_pictures(d, requests: dict[str, Request], config: dict[str, Any]) -> None:
    """Size every picture in the body and the notes; run after the page and the tables are set."""
    room = _Room(d, _body_mm(d.sections[-1], config))
    limit = figure_limit(config["figures"].get("max_width"))
    _fit(d.element.body, requests, room, limit)
    for rel in d.part.rels.values():
        if rel.is_external or rel.reltype not in (RT.FOOTNOTES, RT.ENDNOTES):
            continue
        part = rel.target_part
        if hasattr(part, "element"):
            _fit(part.element, requests, room, limit)
            continue
        # python-docx loads the notes as plain parts: edit the XML and put it back
        root = etree.fromstring(part.blob)
        if _fit(root, requests, room, limit):
            part._blob = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8", standalone=True
            )
