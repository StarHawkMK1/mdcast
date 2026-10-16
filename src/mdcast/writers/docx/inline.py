from __future__ import annotations

from typing import Any

from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

from mdcast.writers.docx.xml import PPR_ORDER, upsert

_MATH = "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"
_OBJECTS = (qn("w:drawing"), qn("w:pict"), qn("w:object"), _MATH)


def _exact_in_style_chain(style_id: str | None, styles: dict[str, Any]) -> str | None:
    seen: set[str] = set()
    while style_id is not None and style_id not in seen and style_id in styles:
        seen.add(style_id)
        element = styles[style_id]
        spacing = element.find(f"{qn('w:pPr')}/{qn('w:spacing')}")
        if spacing is not None and spacing.get(qn("w:line")) is not None:
            return spacing.get(qn("w:line")) if spacing.get(qn("w:lineRule")) == "exact" else None
        based = element.find(qn("w:basedOn"))
        style_id = None if based is None else based.get(qn("w:val"))
    return None


def _exact_line(p, styles: dict[str, Any], default_id: str | None) -> str | None:
    """The paragraph's exact line height in twips, or None when its line rule is not exact."""
    ppr = p.find(qn("w:pPr"))
    if ppr is not None:
        spacing = ppr.find(qn("w:spacing"))
        if spacing is not None and spacing.get(qn("w:line")) is not None:
            return spacing.get(qn("w:line")) if spacing.get(qn("w:lineRule")) == "exact" else None
        p_style = ppr.find(qn("w:pStyle"))
        if p_style is not None:
            return _exact_in_style_chain(p_style.get(qn("w:val")), styles)
    return _exact_in_style_chain(default_id, styles)


def _loosen(root, styles: dict[str, Any], default_id: str | None) -> bool:
    changed = False
    for p in root.iter(qn("w:p")):
        if not any(next(p.iter(tag), None) is not None for tag in _OBJECTS):
            continue
        line = _exact_line(p, styles, default_id)
        if line is None:
            continue
        ppr = p.find(qn("w:pPr"))
        if ppr is None:
            ppr = OxmlElement("w:pPr")
            p.insert(0, ppr)
        upsert(ppr, "w:spacing", PPR_ORDER, line=line, lineRule="atLeast")
        changed = True
    return changed


def loosen_inline_objects(d) -> None:
    """Let paragraphs holding images or equations grow: an "exact" line would clip them."""
    styles = {s.get(qn("w:styleId")): s for s in d.styles.element.findall(qn("w:style"))}
    default = next(
        (s for s in styles.values() if s.get(qn("w:type")) == "paragraph" and s.get(qn("w:default")) in ("1", "true")),
        None,
    )
    default_id = None if default is None else default.get(qn("w:styleId"))
    _loosen(d.element.body, styles, default_id)
    for rel in d.part.rels.values():
        if rel.is_external or rel.reltype not in (RT.FOOTNOTES, RT.ENDNOTES):
            continue
        part = rel.target_part
        if hasattr(part, "element"):
            _loosen(part.element, styles, default_id)
            continue
        # python-docx loads the notes as plain parts: edit the XML and put it back
        root = etree.fromstring(part.blob)
        if _loosen(root, styles, default_id):
            part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
