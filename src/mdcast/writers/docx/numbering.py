from __future__ import annotations

from typing import Any

from docx.oxml.ns import qn

from mdcast.counters import word_level
from mdcast.fonts import latin_name
from mdcast.units import parse_length_mm
from mdcast.writers.docx.xml import LVL_ORDER, PPR_ORDER, RPR_ORDER, mm_to_twips, remove_all, upsert


def apply_list_numbering(d, config: dict[str, Any]) -> None:
    numbering = d.part.numbering_part.element
    lists = config["lists"]
    bullets = [str(b) for b in lists["bullet"]]
    ordered = [str(o) for o in lists["ordered"]]
    indent = parse_length_mm(lists["indent_per_level"])
    family = str(config["fonts"]["body"].get("family") or "").strip()
    latin = latin_name(family) if family else ""
    for abstract in numbering.findall(qn("w:abstractNum")):
        levels = abstract.findall(qn("w:lvl"))
        if not levels:
            continue
        first_fmt = levels[0].find(qn("w:numFmt"))
        is_bullet = first_fmt is not None and first_fmt.get(qn("w:val")) == "bullet"
        for lvl in levels:
            index = int(lvl.get(qn("w:ilvl"), "0"))
            if is_bullet:
                upsert(lvl, "w:numFmt", LVL_ORDER, val="bullet")
                upsert(lvl, "w:lvlText", LVL_ORDER, val=bullets[min(index, len(bullets) - 1)])
                if family:
                    rpr = upsert(lvl, "w:rPr", LVL_ORDER)
                    remove_all(rpr, "w:rFonts")
                    upsert(rpr, "w:rFonts", RPR_ORDER, ascii=latin, hAnsi=latin, eastAsia=family, cs=latin)
            else:
                fmt, text = word_level(ordered[min(index, len(ordered) - 1)], index)
                upsert(lvl, "w:numFmt", LVL_ORDER, val=fmt)
                upsert(lvl, "w:lvlText", LVL_ORDER, val=text)
            ppr = upsert(lvl, "w:pPr", LVL_ORDER)
            upsert(ppr, "w:ind", PPR_ORDER, left=mm_to_twips(indent * (index + 1)), hanging=mm_to_twips(indent))
