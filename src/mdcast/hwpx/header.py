"""header.xml editing: character and paragraph shapes, border fills, tabs, fonts (spec §5)."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from lxml import etree

from mdcast.hwpx.container import ContainerError
from mdcast.hwpx.units import hwpunit, hwpunit_pt, para_unit, para_unit_pt

HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
LANGS = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")
# child order of hh:charPr as Hangul writes it (appendix A-16)
CHAR_ORDER = (
    "fontRef", "ratio", "spacing", "relSz", "offset", "italic", "bold", "underline",
    "strikeout", "outline", "shadow", "emboss", "engrave", "supscript", "subscript",
)
# the typeInfo Hangul writes for fonts it knows (appendix A-16); other faces go without one
TYPE_INFO = {
    "맑은 고딕": {
        "familyType": "FCAT_GOTHIC", "weight": "5", "proportion": "3", "contrast": "2",
        "strokeVariation": "0", "armStyle": "0", "letterform": "2", "midline": "0", "xHeight": "4",
    },
}
LINE_WIDTH = "0.12 mm"  # border width seen working in Hangul (appendix A-6)
OFFSETS = ("offsetLeft", "offsetRight", "offsetTop", "offsetBottom")


def hh(tag: str) -> str:
    return f"{{{HH}}}{tag}"


def hc(tag: str) -> str:
    return f"{{{HC}}}{tag}"


@dataclass(frozen=True)
class CharSpec:
    """Changes to a base character shape; ``None`` keeps the base value."""

    font: str | None = None
    size: float | None = None  # pt
    color: str | None = None  # "#RRGGBB"
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strike: bool | None = None
    script: str | None = None  # "sup" | "sub" | "" (neither)


@dataclass(frozen=True)
class ParaSpec:
    """Changes to a base paragraph shape; ``None`` keeps the base value. Lengths mm, gaps pt."""

    align: str | None = None
    line_height: float | None = None
    prev: float | None = None
    next: float | None = None
    left: float | None = None
    right: float | None = None
    hanging: float | None = None
    keep_with_next: bool | None = None
    border_fill: str | None = None
    offsets: tuple[float, float, float, float] | None = None  # left, right, top, bottom
    connect: bool | None = None
    tab_pr: str | None = None


def _flag(element: etree._Element, name: str, on: bool | None, **attrs: str) -> None:
    if on is None:
        return
    for old in element.findall(hh(name)):
        element.remove(old)
    if on:
        etree.SubElement(element, hh(name), attrs)


def _order(element: etree._Element, order: tuple[str, ...]) -> None:
    rank = {hh(name): index for index, name in enumerate(order)}
    children = sorted(element, key=lambda child: rank.get(child.tag, len(order)))
    element[:] = children


class Header:
    def __init__(self, root: etree._Element) -> None:
        self.root = root
        self._known: dict[tuple[str, bytes], str] = {}

    def _list(self, tag: str) -> etree._Element:
        element = self.root.find(f".//{hh(tag)}")
        if element is None:
            raise ContainerError(f"header.xml 에 {tag} 가 없습니다")
        return element

    def item(self, list_tag: str, item_id: str) -> etree._Element:
        for element in self._list(list_tag):
            if element.get("id") == item_id:
                return element
        raise ContainerError(f"header.xml 에 {list_tag} id={item_id} 가 없습니다")

    def style_id(self, name: str) -> str | None:
        for style in self._list("styles"):
            if style.get("name") == name:
                return style.get("id")
        return None

    def style(self, style_id: str) -> etree._Element:
        return self.item("styles", style_id)

    def first_style_id(self) -> str:
        first = next(iter(self._list("styles")), None)
        if first is None:
            raise ContainerError("header.xml 에 스타일이 없습니다")
        return first.get("id")

    def para_left(self, para_id: str) -> float:
        """Left margin of a paragraph shape in mm."""
        left = self.item("paraProperties", para_id).find(f".//{hh('margin')}/{hc('left')}")
        return 0.0 if left is None else int(left.get("value", "0")) * 25.4 / 14400

    def _add(self, list_tag: str, element: etree._Element) -> str:
        element.attrib.pop("id", None)
        key = (list_tag, etree.tostring(element))
        if key in self._known:
            return self._known[key]
        container = self._list(list_tag)
        ids = [int(e.get("id")) for e in container if (e.get("id") or "").isdigit()]
        new_id = str(max(ids, default=-1) + 1)
        attrs = dict(element.attrib)
        element.attrib.clear()
        element.set("id", new_id)
        for name, value in attrs.items():
            element.set(name, value)
        container.append(element)
        container.set("itemCnt", str(len(container)))
        self._known[key] = new_id
        return new_id

    def font_refs(self, face: str) -> dict[str, str]:
        """The font's id in every language group, adding it where missing."""
        refs: dict[str, str] = {}
        for fontface in self._list("fontfaces").findall(hh("fontface")):
            fonts = fontface.findall(hh("font"))
            found = next((f for f in fonts if f.get("face") == face), None)
            if found is None:
                ids = [int(f.get("id")) for f in fonts if (f.get("id") or "").isdigit()]
                found = etree.SubElement(
                    fontface, hh("font"), id=str(max(ids, default=-1) + 1), face=face, type="TTF", isEmbedded="0"
                )
                if face in TYPE_INFO:
                    etree.SubElement(found, hh("typeInfo"), TYPE_INFO[face])
                fontface.set("fontCnt", str(len(fontface.findall(hh("font")))))
            refs[(fontface.get("lang") or "").lower()] = found.get("id")
        return refs

    def add_char(self, base_id: str, spec: CharSpec) -> str:
        element = copy.deepcopy(self.item("charProperties", base_id))
        if spec.size is not None:
            element.set("height", str(hwpunit_pt(spec.size)))
        if spec.color is not None:
            element.set("textColor", spec.color.upper())
        if spec.font is not None:
            ref = element.find(hh("fontRef"))
            if ref is not None:
                for lang, font_id in self.font_refs(spec.font).items():
                    if lang in LANGS:
                        ref.set(lang, font_id)
        _flag(element, "bold", spec.bold)
        _flag(element, "italic", spec.italic)
        color = element.get("textColor", "#000000")
        _flag(element, "underline", spec.underline, type="BOTTOM", shape="SOLID", color=color)
        _flag(element, "strikeout", spec.strike, shape="SOLID", color=color)
        if spec.script is not None:
            _flag(element, "supscript", spec.script == "sup")
            _flag(element, "subscript", spec.script == "sub")
        _order(element, CHAR_ORDER)
        return self._add("charProperties", element)

    def add_para(self, base_id: str, spec: ParaSpec) -> str:
        # hh:margin / hh:lineSpacing may sit in hp:switch case/default copies: update every copy
        element = copy.deepcopy(self.item("paraProperties", base_id))
        if spec.align is not None:
            for align in element.iter(hh("align")):
                align.set("horizontal", spec.align.upper())
        if spec.line_height is not None:
            for spacing in element.iter(hh("lineSpacing")):
                spacing.set("type", "PERCENT")
                spacing.set("value", str(round(spec.line_height * 100)))
        margins = {
            "intent": None if spec.hanging is None else -para_unit(spec.hanging),
            "left": None if spec.left is None else para_unit(spec.left),
            "right": None if spec.right is None else para_unit(spec.right),
            "prev": None if spec.prev is None else para_unit_pt(spec.prev),
            "next": None if spec.next is None else para_unit_pt(spec.next),
        }
        for margin in element.iter(hh("margin")):
            for name, value in margins.items():
                if value is None:
                    continue
                child = margin.find(hc(name))
                if child is None:
                    child = etree.SubElement(margin, hc(name), unit="HWPUNIT")
                child.set("value", str(value))
        if spec.keep_with_next is not None:
            for brk in element.iter(hh("breakSetting")):
                brk.set("keepWithNext", "1" if spec.keep_with_next else "0")
        borders = list(element.iter(hh("border")))
        if spec.border_fill is not None and not borders:
            borders = [etree.SubElement(element, hh("border"), offsetLeft="0", offsetRight="0",
                                        offsetTop="0", offsetBottom="0", connect="0", ignoreMargin="0")]
        for border in borders:
            if spec.border_fill is not None:
                border.set("borderFillIDRef", spec.border_fill)
            if spec.offsets is not None:
                for name, value in zip(OFFSETS, spec.offsets):
                    border.set(name, str(hwpunit(value)))
            if spec.connect is not None:
                border.set("connect", "1" if spec.connect else "0")
        if spec.tab_pr is not None:
            element.set("tabPrIDRef", spec.tab_pr)
        return self._add("paraProperties", element)

    def add_border_fill(self, *, fill: str | None = None, top: bool = False, bottom: bool = False) -> str:
        element = etree.Element(
            hh("borderFill"), threeD="0", shadow="0", centerLine="NONE", breakCellSeparateLine="0"
        )
        for name in ("slash", "backSlash"):
            etree.SubElement(element, hh(name), type="NONE", Crooked="0", isCounter="0")
        sides = (("leftBorder", False), ("rightBorder", False), ("topBorder", top), ("bottomBorder", bottom))
        for name, on in sides:
            etree.SubElement(element, hh(name), type="SOLID" if on else "NONE",
                             width=LINE_WIDTH if on else "0.1 mm", color="#000000")
        etree.SubElement(element, hh("diagonal"), type="SOLID", width="0.1 mm", color="#000000")
        brush = etree.SubElement(element, hc("fillBrush"))
        etree.SubElement(brush, hc("winBrush"), faceColor=fill.upper() if fill else "none",
                         hatchColor="#999999", alpha="0")
        return self._add("borderFills", element)

    def add_tabs(self, stops: list[tuple[float, str]]) -> str:
        element = etree.Element(hh("tabPr"), autoTabLeft="0", autoTabRight="0")
        for position, kind in stops:
            etree.SubElement(element, hh("tabItem"), pos=str(para_unit(position)), type=kind, leader="NONE")
        return self._add("tabProperties", element)

    def auto_tab(self) -> str:
        """Tabs whose tab after a list marker lands on the hanging indent (appendix A-15)."""
        for tab in self._list("tabProperties"):
            if tab.get("autoTabLeft") == "1" and tab.get("autoTabRight", "0") == "0" and not len(tab):
                return tab.get("id")
        return self._add("tabProperties", etree.Element(hh("tabPr"), autoTabLeft="1", autoTabRight="0"))

    def blank_numbering(self, numbering_id: str) -> None:
        """Hangul's outline numbers off: mdcast's numbering filter writes the numbers (spec §5.2)."""
        for numbering in self.root.iter(hh("numbering")):
            if numbering.get("id") == numbering_id:
                for head in numbering.findall(hh("paraHead")):
                    head.text = None
                    head.set("textOffset", "0")
