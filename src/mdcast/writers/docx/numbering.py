from __future__ import annotations

import unicodedata
from typing import Any

from docx.oxml.ns import qn

from mdcast.counters import format_counter, word_level
from mdcast.fonts import latin_name
from mdcast.units import parse_length_mm, parse_pt
from mdcast.writers.docx.xml import LVL_ORDER, PPR_ORDER, RPR_ORDER, mm_to_twips, remove_all, upsert

_GAP_EM = 0.5  # space between the marker and the text
_MIN_HANGING_MM = 3.0


def _text_em(text: str) -> float:
    """Rough rendered width in em: CJK and ambiguous-width symbols ~1em, the rest ~0.55em."""
    return sum(1.0 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 0.55 for ch in text)


def _hanging_twips(markers: list[str], body_pt: float) -> int:
    """Hanging indent that holds the widest of ``markers`` plus a gap, at the body font size."""
    em = max(_text_em(m) for m in markers) + _GAP_EM
    return max(round(em * body_pt * 20), mm_to_twips(_MIN_HANGING_MM))


def _body_abstract_ids(d) -> set[str]:
    """abstractNumIds behind the numIds that body paragraphs use directly (pandoc's own lists).

    Lists that only a style links to (the container's outline or list styles) are left alone.
    """
    numbering = d.part.numbering_part.element
    used = {
        num_id.get(qn("w:val"))
        for num_pr in d.element.body.iter(qn("w:numPr"))
        for num_id in num_pr.findall(qn("w:numId"))
    }
    ids = set()
    for num in numbering.findall(qn("w:num")):
        if num.get(qn("w:numId")) in used:
            abstract = num.find(qn("w:abstractNumId"))
            if abstract is not None:
                ids.add(abstract.get(qn("w:val")))
    return ids


def apply_list_numbering(d, config: dict[str, Any]) -> None:
    numbering = d.part.numbering_part.element
    lists = config["lists"]
    bullets = [str(b) for b in lists["bullet"]]
    ordered = [str(o) for o in lists["ordered"]]
    indent = parse_length_mm(lists["indent_per_level"])
    try:
        body_pt = parse_pt((config["elements"].get("body") or {}).get("size")) or 11.0
    except (TypeError, ValueError):
        body_pt = 11.0
    family = str(config["fonts"]["body"].get("family") or "").strip()
    latin = latin_name(family) if family else ""
    targets = _body_abstract_ids(d)
    for abstract in numbering.findall(qn("w:abstractNum")):
        if abstract.get(qn("w:abstractNumId")) not in targets:
            continue
        levels = abstract.findall(qn("w:lvl"))
        if not levels:
            continue
        first_fmt = levels[0].find(qn("w:numFmt"))
        is_bullet = first_fmt is not None and first_fmt.get(qn("w:val")) == "bullet"
        parent_text = 0
        for lvl in sorted(levels, key=lambda el: int(el.get(qn("w:ilvl"), "0"))):
            index = int(lvl.get(qn("w:ilvl"), "0"))
            if is_bullet:
                symbol = bullets[min(index, len(bullets) - 1)]
                upsert(lvl, "w:numFmt", LVL_ORDER, val="bullet")
                upsert(lvl, "w:lvlText", LVL_ORDER, val=symbol)
                if family:
                    rpr = upsert(lvl, "w:rPr", LVL_ORDER)
                    remove_all(rpr, "w:rFonts")
                    upsert(rpr, "w:rFonts", RPR_ORDER, ascii=latin, hAnsi=latin, eastAsia=family, cs=latin)
                markers = [symbol]
            else:
                pattern = ordered[min(index, len(ordered) - 1)]
                fmt, text = word_level(pattern, index)
                upsert(lvl, "w:numFmt", LVL_ORDER, val=fmt)
                upsert(lvl, "w:lvlText", LVL_ORDER, val=text)
                markers = [format_counter(pattern, n) for n in range(1, 11)]
            # the marker starts one indent_per_level further per level, but never left of the
            # parent level's text; the text follows the marker
            hanging = _hanging_twips(markers, body_pt)
            start = max(mm_to_twips(indent * index), parent_text)
            parent_text = start + hanging
            ppr = upsert(lvl, "w:pPr", LVL_ORDER)
            upsert(ppr, "w:ind", PPR_ORDER, left=parent_text, hanging=hanging)
