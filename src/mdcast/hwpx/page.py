"""Page setup, header/footer controls and the first paragraph (spec §6.1, §6.2)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from lxml import etree

from mdcast.hwpx.container import ContainerError
from mdcast.hwpx.header import Header, ParaSpec
from mdcast.hwpx.look import PageNumber, PageSetup, Piece, Settings, Slots
from mdcast.hwpx.section import append_text, hp
from mdcast.hwpx.shapes import Shape
from mdcast.hwpx.units import hwpunit

RULE = 1.5 + 0.18  # mm: the PDF's gap between a header row and its 0.5pt rule, plus the rule
BASELINE = 0.85  # Hangul: baseline below a line's top, in font sizes (appendix A-9)
SECTION_CONTROLS = ("header", "footer", "pageNum", "pageHiding")


@dataclass(frozen=True)
class Layout:
    top: float  # mm
    header: float
    bottom: float
    footer: float
    footer_prev: float  # pt: space above the footer paragraph
    below_offset: float  # mm: header rule below the text
    above_offset: float  # mm: footer rule above the text


def layout(top: float, bottom: float, size: float, ratio: float, header_line: str, footer_line: str) -> Layout:
    """Split the yaml margins so header and footer baselines land where the PDF puts them (§6.1)."""
    s = size * 25.4 / 72
    header_baseline = 0.7 * top - (RULE if header_line == "below" else 0.0) - (0.2 + (ratio - 1) / 2) * s
    page_top = max(0.0, header_baseline - BASELINE * s)
    footer_baseline = 0.3 * bottom + (RULE if footer_line == "above" else 0.0) + (0.8 + (ratio - 1) / 2) * s
    return Layout(
        top=page_top,
        header=top - page_top,
        bottom=0.0,
        footer=bottom,
        footer_prev=max(0.0, footer_baseline - BASELINE * s) * 72 / 25.4,
        below_offset=max(0.0, 1.5 + (0.55 - ratio / 2) * s),
        above_offset=max(0.0, 1.5 + ((ratio - 1) / 2 - 0.05) * s),
    )


def find_sec_pr_run(section: etree._Element) -> etree._Element:
    for paragraph in section.findall(hp("p")):
        for run in paragraph.findall(hp("run")):
            if run.find(hp("secPr")) is not None:
                return run
    raise ContainerError("section0.xml 에 쪽 설정(secPr)이 없습니다")


def auto_number(kind: str) -> etree._Element:
    ctrl = etree.Element(hp("ctrl"))
    number = etree.SubElement(ctrl, hp("autoNum"), num="1", numType="TOTAL_PAGE" if kind == "pages" else "PAGE")
    etree.SubElement(number, hp("autoNumFormat"), type="DIGIT", userChar="", prefixChar="", suffixChar="",
                     supscript="0")
    return ctrl


def _mm(value: str | None) -> float:
    return int(value or "0") * 25.4 / 7200


def _set(margin: etree._Element, **values: float) -> None:
    for name, value in values.items():
        margin.set(name, str(hwpunit(value)))


def apply_page(sec_pr: etree._Element, page: PageSetup) -> etree._Element:
    page_pr = sec_pr.find(hp("pagePr"))
    margin = None if page_pr is None else page_pr.find(hp("margin"))
    if margin is None:
        raise ContainerError("section0.xml 의 쪽 설정에 용지(pagePr)가 없습니다")
    if page.width is not None and page.height is not None:
        page_pr.set("width", str(hwpunit(min(page.width, page.height))))
        page_pr.set("height", str(hwpunit(max(page.width, page.height))))
    if page.landscape is not None:
        page_pr.set("landscape", "NARROWLY" if page.landscape else "WIDELY")
    for side in ("left", "right"):
        value = getattr(page, side)
        if value is not None:
            margin.set(side, str(hwpunit(value)))
    return margin


def body_width(sec_pr: etree._Element) -> float:
    page_pr = sec_pr.find(hp("pagePr"))
    margin = page_pr.find(hp("margin"))
    across = page_pr.get("height") if page_pr.get("landscape") == "NARROWLY" else page_pr.get("width")
    used = int(margin.get("left", "0")) + int(margin.get("right", "0")) + int(margin.get("gutter", "0"))
    return (int(across or "0") - used) * 25.4 / 7200


def _controls(section: etree._Element, kinds: list[str]) -> list[etree._Element]:
    found = []
    for paragraph in section.findall(hp("p")):
        for run in paragraph.findall(hp("run")):
            for ctrl in run.findall(hp("ctrl")):
                if any(ctrl.find(hp(kind)) is not None for kind in kinds):
                    found.append(ctrl)
    return found


def _expand(t: etree._Element, fill: Callable[[str], list[Piece]]) -> list[etree._Element]:
    """An ``hp:t`` with ``{{key}}`` text as text and page-number controls."""
    if "{{" not in "".join(t.itertext()):
        return [t]
    out: list[etree._Element] = []
    current = etree.Element(hp("t"))

    def put(value: str) -> None:
        nonlocal current
        for piece in fill(value) if "{{" in value else [value]:
            if isinstance(piece, PageNumber):
                out.append(current)
                out.append(auto_number(piece.kind))
                current = etree.Element(hp("t"))
            else:
                append_text(current, piece)

    put(t.text or "")
    for child in list(t):
        tail, child.tail = child.tail, None
        current.append(child)
        put(tail or "")
    out.append(current)
    kept = [node for node in out if node.tag != hp("t") or node.text or len(node)]
    return kept or [etree.Element(hp("t"))]


def fill_controls(controls: list[etree._Element], fill: Callable[[str], list[Piece]]) -> None:
    for ctrl in controls:
        for run in list(ctrl.iter(hp("run"))):
            children: list[etree._Element] = []
            for child in run:
                children.extend(_expand(child, fill) if child.tag == hp("t") else [child])
            run[:] = children


def _has_content(slots: Slots) -> bool:
    return bool(slots.left or slots.center or slots.right) or slots.line in ("below", "above")


def _slot_paragraph(slots: Slots, para: str, style: str, char: str) -> etree._Element:
    paragraph = etree.Element(hp("p"), id="0", paraPrIDRef=para, styleIDRef=style, pageBreak="0",
                              columnBreak="0", merged="0")
    run = etree.SubElement(paragraph, hp("run"), charPrIDRef=char)
    t = etree.SubElement(run, hp("t"))
    for index, pieces in enumerate((slots.left, slots.center, slots.right)):
        if index:
            if t is None:
                t = etree.SubElement(run, hp("t"))
            etree.SubElement(t, hp("tab"), width="0", leader="0", type="1")
        for piece in pieces:
            if isinstance(piece, PageNumber):
                run.append(auto_number(piece.kind))
                t = None
            else:
                if t is None:
                    t = etree.SubElement(run, hp("t"))
                append_text(t, piece)
    return paragraph


def _slot_control(kind: str, number: int, paragraph: etree._Element, width: float, height: float) -> etree._Element:
    ctrl = etree.Element(hp("ctrl"))
    part = etree.SubElement(ctrl, hp(kind), id=str(number), applyPageType="BOTH")
    sub = etree.SubElement(
        part, hp("subList"), id="", textDirection="HORIZONTAL", lineWrap="BREAK", vertAlign="TOP",
        linkListIDRef="0", linkListNextIDRef="0", textWidth=str(hwpunit(width)), textHeight=str(hwpunit(height)),
        hasTextRef="0", hasNumRef="0",
    )
    sub.append(paragraph)
    return ctrl


def _slot_para(header: Header, body: Shape, slots: Slots, width: float, lay: Layout, footer: bool) -> str:
    fill = offsets = None
    if slots.line in ("below", "above"):
        fill = header.add_border_fill(top=slots.line == "above", bottom=slots.line == "below")
        offsets = (0.0, 0.0, lay.above_offset if slots.line == "above" else 0.0,
                   lay.below_offset if slots.line == "below" else 0.0)
    tabs = header.add_tabs([(width / 2, "CENTER"), (width, "RIGHT")])
    spec = ParaSpec(align="left", prev=lay.footer_prev if footer else 0.0, next=0.0, left=0.0, right=0.0,
                    hanging=0.0, keep_with_next=False, border_fill=fill, offsets=offsets, tab_pr=tabs)
    return header.add_para(body.para, spec)


def assemble(section: etree._Element, paragraphs: list[etree._Element], header: Header,
             shapes: dict[str, Shape], settings: Settings) -> None:
    """Put ``paragraphs`` in the section with the container's section settings (spec §6)."""
    sec_run = find_sec_pr_run(section)
    sec_pr = sec_run.find(hp("secPr"))
    kinds = [kind for kind, slots in (("header", settings.header), ("footer", settings.footer)) if slots is None]
    if len(kinds) == 2:
        kinds.append("pageNum")
    kept = _controls(section, kinds)
    first_id = section.find(hp("p")).get("id", "0")
    sec_run.getparent().remove(sec_run)
    # section-level controls Hangul keeps in the secPr run: drop the ones mdcast replaces
    for ctrl in sec_run.findall(hp("ctrl")):
        if ctrl not in kept and any(ctrl.find(hp(k)) is not None for k in SECTION_CONTROLS):
            sec_run.remove(ctrl)
    for ctrl in kept:
        ctrl.getparent().remove(ctrl)
    for child in section.findall(hp("p")):
        section.remove(child)

    margin = apply_page(sec_pr, settings.page)
    old = {name: _mm(margin.get(name)) for name in ("top", "header", "bottom", "footer")}
    top = settings.page.top if settings.page.top is not None else old["top"] + old["header"]
    bottom = settings.page.bottom if settings.page.bottom is not None else old["bottom"] + old["footer"]
    lay = layout(top, bottom, settings.body_size, settings.body_line_height,
                 settings.header.line if settings.header else "none",
                 settings.footer.line if settings.footer else "none")
    width = body_width(sec_pr)
    visibility = sec_pr.find(hp("visibility"))
    fill_controls(kept, settings.fill)
    controls = list(kept)
    body = shapes["body"]
    style = header.style_id("머리말") or body.style
    number = max((int(c[0].get("id")) for c in kept if (c[0].get("id") or "").isdigit()), default=0)

    if settings.header is None:
        _set(margin, top=max(0.0, top - old["header"]), header=min(old["header"], top))
    else:
        _set(margin, top=lay.top, header=lay.header)
        if visibility is not None:
            visibility.set("hideFirstHeader", "0")
        if _has_content(settings.header):
            number += 1
            para = _slot_para(header, body, settings.header, width, lay, footer=False)
            paragraph = _slot_paragraph(settings.header, para, style, body.char)
            controls.append(_slot_control("header", number, paragraph, width, lay.header))
    if settings.footer is None:
        _set(margin, bottom=max(0.0, bottom - old["footer"]), footer=min(old["footer"], bottom))
    else:
        _set(margin, bottom=lay.bottom, footer=lay.footer)
        if visibility is not None:
            visibility.set("hideFirstFooter", "0")
        if _has_content(settings.footer):
            number += 1
            para = _slot_para(header, body, settings.footer, width, lay, footer=True)
            paragraph = _slot_paragraph(settings.footer, para, style, body.char)
            controls.append(_slot_control("footer", number, paragraph, width, lay.footer))

    first = paragraphs[0]
    first.set("id", first_id)
    # every run of a line counts toward its height: the container's own character shape on the
    # secPr run would set the first line's height (a code block first got a 10pt line)
    first_char = next((run.get("charPrIDRef") for run in first.findall(hp("run"))), body.char)
    sec_run.set("charPrIDRef", first_char)
    first.insert(0, sec_run)
    if controls:
        run = etree.Element(hp("run"), charPrIDRef=first_char)
        for ctrl in controls:
            run.append(ctrl)
        first.insert(1, run)
    for paragraph in paragraphs:
        section.append(paragraph)
