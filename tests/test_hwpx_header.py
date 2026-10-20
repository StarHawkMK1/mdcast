import copy

import pytest
from helpers import HWPX_NS as NS
from helpers import builtin_hwpx, hwpx_integrity
from lxml import etree

from mdcast.hwpx.container import Package
from mdcast.hwpx.header import HC, CharSpec, Header, ParaSpec, line_width
from mdcast.hwpx.look import Border
from mdcast.hwpx.units import hwpunit, para_unit

HH = f"{{{NS['hh']}}}"


def header() -> Header:
    return Header(Package.read(builtin_hwpx()).xml("Contents/header.xml"))


def test_style_lookup_by_korean_name():
    h = header()
    assert h.style_id("바탕글") == "0"
    assert h.style_id("개요 1") == "2"
    assert h.style_id("없는 스타일") is None
    assert h.first_style_id() == "0"


def test_char_shape_values():
    h = header()
    cid = h.add_char("0", CharSpec(font="맑은 고딕", size=11, color="#1f3864", bold=True, italic=False))
    char = h.item("charProperties", cid)
    assert char.get("height") == "1100" and char.get("textColor") == "#1F3864"
    assert char.find("hh:bold", NS) is not None and char.find("hh:italic", NS) is None
    ref = char.find("hh:fontRef", NS)
    for face in h.root.iter(f"{HH}fontface"):
        fonts = face.findall("hh:font", NS)
        chosen = next(f for f in fonts if f.get("id") == ref.get(face.get("lang").lower()))
        assert chosen.get("face") == "맑은 고딕"
        assert chosen.find("hh:typeInfo", NS).get("weight") == "5"  # Hangul's own, appendix A-16
        assert int(face.get("fontCnt")) == len(fonts)


def test_unknown_font_has_no_type_info():
    h = header()
    ref = h.item("charProperties", h.add_char("0", CharSpec(font="Consolas"))).find("hh:fontRef", NS)
    face = next(h.root.iter(f"{HH}fontface"))
    font = next(f for f in face.findall("hh:font", NS) if f.get("id") == ref.get("hangul"))
    assert font.get("face") == "Consolas" and font.find("hh:typeInfo", NS) is None


def test_same_definition_is_reused():
    h = header()
    first = h.add_char("0", CharSpec(size=11))
    assert h.add_char("0", CharSpec(size=11)) == first
    assert h.add_char("0", CharSpec(size=12)) != first


def test_char_flags_follow_hangul_order():
    h = header()
    cid = h.add_char("0", CharSpec(bold=True, italic=True, underline=True, strike=True, script="sup"))
    tags = [etree.QName(child).localname for child in h.item("charProperties", cid)]
    assert tags[-5:] == ["italic", "bold", "underline", "strikeout", "supscript"]
    cleared = h.add_char(cid, CharSpec(bold=False, script=""))
    tags = [etree.QName(child).localname for child in h.item("charProperties", cleared)]
    assert "bold" not in tags and "supscript" not in tags and "italic" in tags


def test_para_shape_units():
    h = header()
    pid = h.add_para(
        "0",
        ParaSpec(align="justify", line_height=1.8, prev=4, next=6, left=5, hanging=3, keep_with_next=True),
    )
    para = h.item("paraProperties", pid)
    margin = {etree.QName(c).localname: c.get("value") for c in para.find("hh:margin", NS)}
    assert margin["left"] == "2834" and margin["intent"] == str(-para_unit(3))
    assert margin["prev"] == "800" and margin["next"] == "1200"
    assert para.find("hh:lineSpacing", NS).get("value") == "180"
    assert para.find("hh:lineSpacing", NS).get("type") == "PERCENT"
    assert para.find("hh:align", NS).get("horizontal") == "JUSTIFY"
    assert para.find("hh:breakSetting", NS).get("keepWithNext") == "1"
    assert abs(h.para_left(pid) - 5.0) < 0.01


def test_margin_inside_switch_is_updated():
    h = header()
    base = h.item("paraProperties", "0")
    margin = base.find("hh:margin", NS)
    base.remove(margin)
    hp = f"{{{NS['hp']}}}"
    switch = etree.SubElement(base, f"{hp}switch")
    etree.SubElement(switch, f"{hp}case").append(copy.deepcopy(margin))
    etree.SubElement(switch, f"{hp}default").append(margin)
    pid = h.add_para("0", ParaSpec(left=5))
    values = [m.find("hc:left", NS).get("value") for m in h.item("paraProperties", pid).iter(f"{HH}margin")]
    assert values == ["2834", "2834"]


def test_border_fills():
    h = header()
    fill = h.item("borderFills", h.add_border_fill(fill="#f6f8fa"))
    assert fill.find("hc:fillBrush/hc:winBrush", NS).get("faceColor") == "#F6F8FA"
    assert fill.find("hh:bottomBorder", NS).get("type") == "NONE"
    rule = h.item("borderFills", h.add_border_fill(bottom=True))
    assert rule.find("hh:bottomBorder", NS).get("type") == "SOLID"
    assert rule.find("hc:fillBrush/hc:winBrush", NS).get("faceColor") == "none"


def test_paragraph_border_offsets_are_plain_hwpunit():
    h = header()
    rule = h.add_border_fill(bottom=True)
    pid = h.add_para("0", ParaSpec(border_fill=rule, offsets=(2, 2, 0, 1.5), connect=False))
    border = h.item("paraProperties", pid).find("hh:border", NS)
    assert border.get("borderFillIDRef") == rule
    assert border.get("offsetLeft") == str(hwpunit(2)) and border.get("offsetBottom") == str(hwpunit(1.5))
    assert border.get("connect") == "0"


def test_tab_positions_are_doubled():
    h = header()
    tab = h.item("tabProperties", h.add_tabs([(75.0, "CENTER"), (150.0, "RIGHT")]))
    assert [(i.get("pos"), i.get("type")) for i in tab] == [
        (str(para_unit(75.0)), "CENTER"),
        (str(para_unit(150.0)), "RIGHT"),
    ]


def test_auto_tab_reuses_the_container_definition():
    assert header().auto_tab() == "1"


def test_outline_numbers_are_blanked():
    h = header()
    h.blank_numbering("1")
    heads = h.root.findall(".//hh:numbering[@id='1']/hh:paraHead", NS)
    assert heads and all(not (x.text or "") and x.get("textOffset") == "0" for x in heads)


def test_package_stays_sound_after_edits():
    package = Package.read(builtin_hwpx())
    h = Header(package.xml("Contents/header.xml"))
    h.add_char("0", CharSpec(font="Consolas", underline=True))
    h.add_para("0", ParaSpec(border_fill=h.add_border_fill(fill="#EEEEEE"), tab_pr=h.add_tabs([(10, "LEFT")])))
    package.set_xml("Contents/header.xml", h.root)
    hwpx_integrity(package.write())


@pytest.mark.parametrize("pt, expected", [(0.34, "0.12 mm"), (0.5, "0.2 mm"), (1.0, "0.4 mm"),
                                          (0.1, "0.1 mm"), (3.0, "1.0 mm"), (100.0, "5.0 mm")])
def test_line_width_snaps_to_hangul_widths(pt, expected):
    assert line_width(pt) == expected


def test_cell_border_fill_sides_and_background():
    head = header()
    outer, inner = Border(1.0, "#000000"), Border(0.5, "#333333")
    fill_id = head.add_cell_border_fill((outer, inner, outer, None), "#f2f2f2")
    fill = head.item("borderFills", fill_id)
    sides = [(e.get("type"), e.get("width"), e.get("color")) for e in fill
             if e.tag.endswith(("leftBorder", "rightBorder", "topBorder", "bottomBorder"))]
    assert sides == [("SOLID", "0.4 mm", "#000000"), ("SOLID", "0.2 mm", "#333333"),
                     ("SOLID", "0.4 mm", "#000000"), ("NONE", "0.1 mm", "#000000")]
    assert fill.find(f".//{{{HC}}}winBrush").get("faceColor") == "#F2F2F2"
    assert head.add_cell_border_fill((outer, inner, outer, None), "#f2f2f2") == fill_id
    bare = head.item("borderFills", head.add_cell_border_fill((None,) * 4, None))
    assert bare.find(f"{{{HC}}}fillBrush") is None
