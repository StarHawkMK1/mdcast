"""THROWAWAY: hand-written hwpx variants built on a Hangul-saved base, for Hangul to judge."""

import copy
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

BASE = Path(sys.argv[1])  # a Hangul-saved hwpx (pagebreak.hwpx)
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

NS = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "opf": "http://www.idpf.org/2007/opf/",
}
HP = "{%s}" % NS["hp"]
HH = "{%s}" % NS["hh"]
LONG = "줄 간격을 보기 위해 충분히 긴 문장을 씁니다. " * 8


def load():
    z = zipfile.ZipFile(BASE)
    return {i.filename: (z.read(i.filename), i.compress_type) for i in z.infolist()}


def save(parts, name):
    with zipfile.ZipFile(OUT / name, "w") as z:
        for fname, (data, ctype) in parts.items():
            z.writestr(zipfile.ZipInfo(fname), data, compress_type=ctype)


def xml(parts, name):
    return etree.fromstring(parts[name][0])


def put(parts, name, root):
    parts[name] = (etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), parts[name][1])


def bump(container):
    container.set("itemCnt", str(len(container)))


def add_charpr(head, height, color="#000000", base_id="0"):
    props = head.find(".//hh:charProperties", NS)
    new = copy.deepcopy(props.find(f"hh:charPr[@id='{base_id}']", NS))
    new.set("id", str(len(props)))
    new.set("height", str(height))
    new.set("textColor", color)
    props.append(new)
    bump(props)
    return new.get("id")


def add_parapr(head, line=None, border=None, connect="0", offsets=0, base_id="0", left=None):
    props = head.find(".//hh:paraProperties", NS)
    new = copy.deepcopy(props.find(f"hh:paraPr[@id='{base_id}']", NS))
    new.set("id", str(len(props)))
    if line is not None:
        new.find("hh:lineSpacing", NS).set("value", str(line))
    if left is not None:
        new.find("hh:margin/hc:left", NS).set("value", str(left))
    if border is not None:
        b = new.find("hh:border", NS)
        b.set("borderFillIDRef", border)
        b.set("connect", connect)
        for side in ("offsetLeft", "offsetRight", "offsetTop", "offsetBottom"):
            b.set(side, str(offsets))
    props.append(new)
    bump(props)
    return new.get("id")


def add_borderfill(head, fill=None, bottom=None):
    fills = head.find(".//hh:borderFills", NS)
    new = copy.deepcopy(fills.find("hh:borderFill[@id='2']", NS))
    new.set("id", str(len(fills) + 1))
    if bottom:
        b = new.find("hh:bottomBorder", NS)
        b.set("type", "SOLID")
        b.set("width", bottom)
    brush = new.find("hc:fillBrush/hc:winBrush", NS)
    if fill:
        brush.set("faceColor", fill)
    fills.append(new)
    bump(fills)
    return new.get("id")


def paragraph(sec, text, para="0", style="0", char="0", page_break="0"):
    p = etree.SubElement(sec, HP + "p", id="0", paraPrIDRef=para, styleIDRef=style, pageBreak=page_break, columnBreak="0", merged="0")
    r = etree.SubElement(p, HP + "run", charPrIDRef=char)
    t = etree.SubElement(r, HP + "t")
    t.text = text
    return p


def body_only(sec):
    """Keep the first paragraph's secPr run, drop its text and the other paragraphs."""
    first = sec[0]
    for p in sec[1:]:
        sec.remove(p)
    for run in first.findall("hp:run", NS)[1:]:
        first.remove(run)
    for arr in first.findall("hp:linesegarray", NS):
        first.remove(arr)
    return first


def variant(name, edit):
    parts = load()
    head, sec = xml(parts, "Contents/header.xml"), xml(parts, "Contents/section0.xml")
    hpf = xml(parts, "Contents/content.hpf")
    body_only(sec)
    edit(head, sec, hpf)
    put(parts, "Contents/header.xml", head)
    put(parts, "Contents/section0.xml", sec)
    put(parts, "Contents/content.hpf", hpf)
    save(parts, name)
    print("wrote", name)


def outline(blank):
    def edit(head, sec, hpf):
        if blank:
            for ph in head.iterfind(".//hh:numbering[@id='1']/hh:paraHead", NS):
                ph.text = None
        for lv in (1, 2, 3):
            paragraph(sec, f"제목 수준{lv}", para=str(lv + 1), style=str(lv + 1))
            paragraph(sec, "본문 문단")
    return edit


def margins(top, header):
    def edit(head, sec, hpf):
        m = sec.find(".//hp:pagePr/hp:margin", NS)
        m.set("top", str(top))
        m.set("header", str(header))
        paragraph(sec, "가나다 첫 줄")
    return edit


def lines(head, sec, hpf):
    c11 = add_charpr(head, 1100)
    c16 = add_charpr(head, 1600)
    p180 = add_parapr(head, line=180)
    p130 = add_parapr(head, line=130)
    paragraph(sec, "본문" + LONG, para=p180, char=c11)
    paragraph(sec, "제목" + LONG, para=p130, char=c16)


def borders(head, sec, hpf):
    bg = add_borderfill(head, fill="#F6F8FA")
    rule = add_borderfill(head, bottom="0.12 mm")
    code = add_parapr(head, border=bg, connect="1", offsets=567)
    hr = add_parapr(head, border=rule)
    paragraph(sec, "앞 문단")
    paragraph(sec, "코드 첫째", para=code)
    paragraph(sec, "코드 둘째", para=code)
    paragraph(sec, "", para=hr)
    paragraph(sec, "뒤 문단")


def meta(head, sec, hpf):
    md = hpf.find("opf:metadata", NS)
    md.find("opf:title", NS).text = "메타 제목"
    for m in md.findall("opf:meta", NS):
        if m.get("name") == "creator":
            m.text = "작성자"
        if m.get("name") == "keyword":
            m.text = "가, 나"
    extra = etree.SubElement(md, "{%s}meta" % NS["opf"], name="mdcast.generator", content="text")
    extra.text = "mdcast 0.1.0"
    paragraph(sec, "메타 본문")


def header_ctrl(kind, slots, tab_pr, para_pr, char_pr):
    ctrl = etree.Element(HP + "ctrl")
    hf = etree.SubElement(ctrl, HP + kind, id="1" if kind == "header" else "2", applyPageType="BOTH")
    sub = etree.SubElement(hf, HP + "subList", id="", textDirection="HORIZONTAL", lineWrap="BREAK", vertAlign="TOP" if kind == "header" else "BOTTOM",
                           linkListIDRef="0", linkListNextIDRef="0", textWidth="42520", textHeight="4252", hasTextRef="0", hasNumRef="0")
    p = etree.SubElement(sub, HP + "p", id="0", paraPrIDRef=para_pr, styleIDRef="13" if kind == "header" else "13", pageBreak="0", columnBreak="0", merged="0")
    r = etree.SubElement(p, HP + "run", charPrIDRef=char_pr)
    for index, slot in enumerate(slots):
        t = etree.SubElement(r, HP + "t")
        if index:
            etree.SubElement(t, HP + "tab", width="0", leader="0", type="1")
        for piece in slot:
            if piece in ("PAGE", "TOTAL_PAGE"):
                c = etree.SubElement(r, HP + "ctrl")
                a = etree.SubElement(c, HP + "autoNum", num="1", numType=piece)
                etree.SubElement(a, HP + "autoNumFormat", type="DIGIT", userChar="", prefixChar="", suffixChar="", supscript="0")
                t = etree.SubElement(r, HP + "t")
            else:
                if len(t):
                    t[-1].tail = (t[-1].tail or "") + piece
                else:
                    t.text = (t.text or "") + piece
    return ctrl


def headers(head, sec, hpf):
    tabs = head.find(".//hh:tabProperties", NS)
    tab = etree.SubElement(tabs, HH + "tabPr", id=str(len(tabs)), autoTabLeft="0", autoTabRight="0")
    etree.SubElement(tab, HH + "tabItem", pos="21260", type="CENTER", leader="NONE")
    etree.SubElement(tab, HH + "tabItem", pos="42520", type="RIGHT", leader="NONE")
    bump(tabs)
    rule = add_borderfill(head, bottom="0.12 mm")
    hpara = add_parapr(head, base_id="9", border=rule)
    head.find(f".//hh:paraPr[@id='{hpara}']", NS).set("tabPrIDRef", tab.get("id"))
    fpara = add_parapr(head, base_id="9")
    head.find(f".//hh:paraPr[@id='{fpara}']", NS).set("tabPrIDRef", tab.get("id"))
    first = sec[0]
    run = etree.SubElement(first, HP + "run", charPrIDRef="0")
    run.append(header_ctrl("header", [["왼쪽칸"], ["가운데칸"], ["오른칸"]], tab.get("id"), hpara, "2"))
    run.append(header_ctrl("footer", [[""], ["PAGE", " / ", "TOTAL_PAGE"], [""]], tab.get("id"), fpara, "2"))
    t = etree.SubElement(run, HP + "t")
    t.text = "본문 첫 쪽"
    paragraph(sec, "둘째 쪽", page_break="1")


variant("v_outline_blank.hwpx", outline(True))
variant("v_outline_default.hwpx", outline(False))
variant("v_margin_header15.hwpx", margins(5668, 4252))
variant("v_margin_header0.hwpx", margins(5668, 0))
variant("v_lines.hwpx", lines)
variant("v_borders.hwpx", borders)
variant("v_meta.hwpx", meta)
variant("v_headers.hwpx", headers)
