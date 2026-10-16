from __future__ import annotations

from typing import Any

from docx.enum.section import WD_ORIENT
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

from mdcast.fonts import latin_name
from mdcast.report import Codes, Report
from mdcast.units import normalize_color, page_size_mm, parse_length_mm, parse_pt, parse_ratio
from mdcast.writers.docx.xml import PPR_ORDER, upsert

PANDOC_STYLES: dict[str, list[str]] = {
    **{f"heading{i}": [f"Heading {i}"] for i in range(1, 7)},
    "body": ["Body Text", "First Paragraph", "Compact"],
    "quote": ["Block Text"],
    "code": ["Source Code"],
    "caption": ["Table Caption", "Image Caption", "Caption"],
    "footnote": ["Footnote Text"],
}
CHARACTER_ONLY = {"Compact"}
_ALIGN = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}
_THEME_ATTRS = ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme")


def apply_page(d, config: dict[str, Any]) -> None:
    """Apply the page keys present in ``config["page"]``; absent keys keep the document's own."""
    page = config.get("page") or {}
    margin = page.get("margin") or {}
    for section in d.sections:
        if page.get("size") is not None or page.get("orientation") is not None:
            landscape = (
                page["orientation"] == "landscape"
                if page.get("orientation") is not None
                else section.page_width > section.page_height
            )
            if page.get("size") is not None:
                width, height = page_size_mm(page["size"], "landscape" if landscape else "portrait")
                section.page_width = Mm(width)
                section.page_height = Mm(height)
            elif landscape != (section.page_width > section.page_height):
                section.page_width, section.page_height = section.page_height, section.page_width
            section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
        for key in ("top", "bottom", "left", "right"):
            if margin.get(key) is not None:
                setattr(section, f"{key}_margin", Mm(parse_length_mm(margin[key])))


def disable_autospace(d) -> None:
    """Turn off Word's automatic spacing between Korean and Latin/digits ("2026 년").

    Typst sets "2026년" tight, so the built-in container matches the PDF this way.
    """
    styles = d.styles.element
    defaults = styles.find(qn("w:docDefaults"))
    if defaults is None:
        defaults = OxmlElement("w:docDefaults")
        styles.insert(0, defaults)  # docDefaults comes first in w:styles
    ppr = upsert(upsert(defaults, "w:pPrDefault"), "w:pPr")  # pPrDefault follows rPrDefault
    upsert(ppr, "w:autoSpaceDE", PPR_ORDER, val=0)
    upsert(ppr, "w:autoSpaceDN", PPR_ORDER, val=0)


def _names(d) -> set[str]:
    return {s.name for s in d.styles}


def _by_name(d) -> dict[str, Any]:
    return {s.name: s for s in d.styles}


def _rebase_secondaries(d, target: str, secondaries: list[str]) -> None:
    """Base pandoc's secondary styles (First Paragraph, Compact, Image Caption, ...) on ``target``.

    They keep their own deltas (Compact's tight spacing) and inherit the rest from the mapped
    style. A secondary that ``target`` itself inherits from is skipped, or the chain would loop.
    """
    by_name = _by_name(d)
    base = by_name[target]
    if base.type != WD_STYLE_TYPE.PARAGRAPH:
        return
    chain: set[str] = set()
    ancestor = base
    while ancestor is not None and ancestor.name not in chain:
        chain.add(ancestor.name)
        ancestor = ancestor.base_style
    for name in secondaries:
        style = by_name.get(name)
        if style is None or name in chain or style.type != WD_STYLE_TYPE.PARAGRAPH:
            continue
        style.base_style = base


def remap_styles(d, config: dict[str, Any], report: Report) -> dict[str, list[str]]:
    names = _names(d)
    used: dict[str, list[str]] = {}
    for element, pandoc_names in PANDOC_STYLES.items():
        target = ((config.get("styles") or {}).get(element) or {}).get("docx")
        primary = pandoc_names[0]
        if not target or target == primary:
            used[element] = list(pandoc_names)
            continue
        if target not in names:
            report.info(
                Codes.STYLE_UNMAPPED,
                f"docx 기준 문서에 스타일 '{target}' 이(가) 없어 '{primary}' 를 씁니다",
                format="docx",
                element=element,
            )
            used[element] = list(pandoc_names)
            continue
        if primary in names:
            by_name = _by_name(d)
            old_id = by_name[primary].style_id
            new_id = by_name[target].style_id
            for p_style in d.element.body.iter(qn("w:pStyle")):
                if p_style.get(qn("w:val")) == old_id:
                    p_style.set(qn("w:val"), new_id)
        _rebase_secondaries(d, target, pandoc_names[1:])
        used[element] = [target, *pandoc_names[1:]]
    return used


def set_font(style, font_cfg: dict[str, Any]) -> None:
    family = str(font_cfg.get("family") or "").strip()
    if not family:
        return
    latin = latin_name(family)
    style.font.name = latin
    rfonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in _THEME_ATTRS:
        rfonts.attrib.pop(qn(f"w:{attr}"), None)
    rfonts.set(qn("w:ascii"), latin)
    rfonts.set(qn("w:hAnsi"), latin)
    rfonts.set(qn("w:cs"), latin)
    rfonts.set(qn("w:eastAsia"), family)


def apply_look(style, look: dict[str, Any], *, character_only: bool = False) -> None:
    font = style.font
    if look.get("size") is not None:
        font.size = Pt(parse_pt(look["size"]))
    if look.get("bold") is not None:
        font.bold = bool(look["bold"])
    if look.get("italic") is not None:
        font.italic = bool(look["italic"])
    if look.get("color") is not None:
        font.color.rgb = RGBColor.from_string(normalize_color(look["color"]))
    if character_only:
        return
    fmt = style.paragraph_format
    if look.get("align") in _ALIGN:
        fmt.alignment = _ALIGN[look["align"]]
    if look.get("line_height") is not None:
        fmt.line_spacing = parse_ratio(look["line_height"])
    if look.get("space_before") is not None:
        fmt.space_before = Pt(parse_pt(look["space_before"]))
    if look.get("space_after") is not None:
        fmt.space_after = Pt(parse_pt(look["space_after"]))
    if look.get("indent_left") is not None:
        fmt.left_indent = Mm(parse_length_mm(look["indent_left"]))
    if look.get("keep_with_next") is not None:
        fmt.keep_with_next = bool(look["keep_with_next"])
    if look.get("background") is not None:
        ppr = style.element.get_or_add_pPr()
        upsert(ppr, "w:shd", PPR_ORDER, val="clear", color="auto", fill=normalize_color(look["background"]))


def apply_elements(d, config: dict[str, Any], used: dict[str, list[str]]) -> None:
    """Write looks/fonts present in ``config`` into the style definitions; absent keys are kept."""
    by_name = _by_name(d)
    fonts = config.get("fonts") or {}
    elements = config.get("elements") or {}
    if "Normal" in by_name:
        normal = by_name["Normal"]
        if fonts.get("body"):
            set_font(normal, fonts["body"])
        apply_look(normal, {"size": (elements.get("body") or {}).get("size")}, character_only=True)
    for element, style_names in used.items():
        look = elements.get(element) or {}
        if element.startswith("heading"):
            font_cfg = fonts.get("heading")
        elif element == "code":
            font_cfg = fonts.get("code")
        else:
            font_cfg = None
        for name in style_names:
            if name not in by_name:
                continue
            style = by_name[name]
            if font_cfg:
                set_font(style, font_cfg)
            apply_look(style, look, character_only=name in CHARACTER_ONLY)
    if "Verbatim Char" in by_name and fonts.get("code"):
        set_font(by_name["Verbatim Char"], fonts["code"])
