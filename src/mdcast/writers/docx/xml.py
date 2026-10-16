from __future__ import annotations

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

PPR_ORDER = [
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
    "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
    "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
    "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
    "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
    "sectPr", "pPrChange",
]
RPR_ORDER = [
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline",
    "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing",
    "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText",
    "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath",
]
TBLPR_ORDER = [
    "tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize", "tblStyleColBandSize",
    "tblW", "jc", "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook",
    "tblCaption", "tblDescription",
]
TCPR_ORDER = [
    "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap", "tcMar",
    "textDirection", "tcFitText", "vAlign", "hideMark",
]
STYLE_ORDER = [
    "name", "aliases", "basedOn", "next", "link", "autoRedefine", "hidden", "uiPriority",
    "semiHidden", "unhideWhenUsed", "qFormat", "locked", "personal", "personalCompose",
    "personalReply", "rsid", "pPr", "rPr", "tblPr", "trPr", "tcPr", "tblStylePr",
]
LVL_ORDER = [
    "start", "numFmt", "lvlRestart", "pStyle", "isLgl", "suff", "lvlText", "lvlPicBulletId",
    "legacy", "lvlJc", "pPr", "rPr",
]
BORDER_ORDER = ["top", "start", "left", "bottom", "end", "right", "insideH", "insideV"]
MAR_ORDER = ["top", "start", "left", "bottom", "end", "right"]


def _local(tag: str) -> str:
    return tag.split(":", 1)[1] if ":" in tag else tag


def _insert_ordered(parent, child, tag: str, order: list[str] | None) -> None:
    name = _local(tag)
    if not order or name not in order:
        parent.append(child)
        return
    later = set(order[order.index(name) + 1 :])
    for index, sibling in enumerate(parent):
        if not isinstance(sibling.tag, str):
            continue
        if etree.QName(sibling).localname in later:
            parent.insert(index, child)
            return
    parent.append(child)


def upsert(parent, tag: str, order: list[str] | None = None, **attrs: object):
    child = parent.find(qn(tag))
    if child is None:
        child = OxmlElement(tag)
        _insert_ordered(parent, child, tag, order)
    for key, value in attrs.items():
        child.set(qn(f"w:{key}"), str(value))
    return child


def remove_all(parent, tag: str) -> None:
    for child in parent.findall(qn(tag)):
        parent.remove(child)


def line_twips(ratio: float, size_pt: float) -> int:
    """Exact line height in twips for ``line_height`` (a ratio of the font size, spec 2026-10-16 §2)."""
    return round(ratio * size_pt * 20)


def mm_to_twips(mm: float) -> int:
    return round(mm / 25.4 * 1440)


def pt_to_eighths(pt: float) -> int:
    return max(2, round(pt * 8))


def half_points(pt: float) -> int:
    return round(pt * 2)
