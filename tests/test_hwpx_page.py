import pytest
from helpers import HWPX_NS as NS
from helpers import builtin_hwpx, hwpx_settings

from mdcast.ast import md_to_doc
from mdcast.hwpx.container import Package
from mdcast.hwpx.header import Header
from mdcast.hwpx.look import Notices, PageNumber, PageSetup, Slots
from mdcast.hwpx.page import assemble, layout
from mdcast.hwpx.section import SectionWriter
from mdcast.hwpx.shapes import build_shapes
from mdcast.hwpx.units import hwpunit, para_unit, para_unit_pt

PAGE = PageSetup(width=210, height=297, landscape=False, top=20, bottom=15, left=20, right=20)
HEADER = Slots(left=("왼쪽",), right=("오른쪽",), line="below")
FOOTER = Slots(center=(PageNumber("page"), " / ", PageNumber("pages")))


def build(md="본문\n", container=None, **changes):
    values = {"page": PAGE, "header": HEADER, "footer": FOOTER}
    values.update(changes)
    settings = hwpx_settings(**values)
    package = Package.read(container or builtin_hwpx())
    header = Header(package.xml("Contents/header.xml"))
    section = package.xml("Contents/section0.xml")
    notices = Notices()
    shapes = build_shapes(header, settings, notices)
    paragraphs = SectionWriter(header, shapes, settings, notices, width=170.0).build(md_to_doc(md))
    assemble(section, paragraphs, header, shapes, settings)
    package.set_xml("Contents/header.xml", header.root)
    package.set_xml("Contents/section0.xml", section)
    return header, section, package


def test_layout_matches_the_pdf_model():
    lay = layout(20, 15, 11, 1.8, "below", "none")
    assert lay.top == pytest.approx(6.69, abs=0.01)
    assert lay.header == pytest.approx(13.31, abs=0.01)
    assert (lay.bottom, lay.footer) == (0.0, 15)
    assert lay.footer_prev == pytest.approx(16.6, abs=0.1)
    assert lay.below_offset == pytest.approx(0.14, abs=0.01)


def test_layout_never_goes_above_the_page():
    lay = layout(3, 3, 11, 1.8, "below", "above")
    assert lay.top == 0.0 and lay.header == 3


def test_first_paragraph_carries_the_section_settings_and_controls():
    _, section, _ = build("# 제목\n\n본문\n")
    first = section[0]
    assert first.find("hp:run/hp:secPr", NS) is not None and first[0].find("hp:secPr", NS) is not None
    controls = first[1].findall("hp:ctrl", NS)
    assert [c[0].tag.split("}")[1] for c in controls] == ["header", "footer"]
    assert "".join(first.find("hp:run/hp:t", NS).itertext()) == "제목"
    assert len(section.findall("hp:p", NS)) == 2


def test_section_runs_take_the_first_paragraphs_look():
    # the container's own 10pt character shape on the secPr run set the first line's height
    _, section, _ = build("```\n코드\n```\n")
    first = section[0]
    chars = {run.get("charPrIDRef") for run in first.findall("hp:run", NS)}
    assert len(chars) == 1


def test_page_size_margins_and_split():
    _, section, _ = build()
    page = section.find(".//hp:pagePr", NS)
    assert (page.get("width"), page.get("height"), page.get("landscape")) == (
        str(hwpunit(210)), str(hwpunit(297)), "WIDELY")
    margin = page.find("hp:margin", NS)
    lay = layout(20, 15, 11, 1.8, "below", "none")
    assert margin.get("left") == str(hwpunit(20))
    assert margin.get("top") == str(hwpunit(lay.top))
    assert abs(int(margin.get("top")) + int(margin.get("header")) - hwpunit(20)) <= 1  # rounding
    assert (margin.get("bottom"), margin.get("footer")) == ("0", str(hwpunit(15)))
    assert section.find(".//hp:visibility", NS).get("hideFirstHeader") == "0"


def test_landscape_keeps_portrait_dimensions():
    _, section, _ = build(page=PageSetup(width=210, height=297, landscape=True))
    page = section.find(".//hp:pagePr", NS)
    assert page.get("landscape") == "NARROWLY" and page.get("width") == str(hwpunit(210))


def test_header_slots_tabs_and_rule():
    header, section, _ = build()
    control = section.find(".//hp:header", NS)
    sub = control.find("hp:subList", NS)
    assert abs(int(sub.get("textWidth")) - hwpunit(170)) <= 1 and sub.get("vertAlign") == "TOP"
    p = sub.find("hp:p", NS)
    t = p.find("hp:run/hp:t", NS)
    assert t.text == "왼쪽" and len(t.findall("hp:tab", NS)) == 2 and t[-1].tail == "오른쪽"
    para = header.item("paraProperties", p.get("paraPrIDRef"))
    tabs = header.item("tabProperties", para.get("tabPrIDRef"))
    positions = [int(i.get("pos")) for i in tabs]
    assert abs(positions[0] - para_unit(85)) <= 2 and abs(positions[1] - para_unit(170)) <= 2
    fill = header.item("borderFills", para.find("hh:border", NS).get("borderFillIDRef"))
    assert fill.find("hh:bottomBorder", NS).get("type") == "SOLID"


def test_footer_page_numbers_and_offset():
    header, section, _ = build()
    p = section.find(".//hp:footer/hp:subList/hp:p", NS)
    numbers = [n.get("numType") for n in p.iter(f"{{{NS['hp']}}}autoNum")]
    assert numbers == ["PAGE", "TOTAL_PAGE"]
    lay = layout(20, 15, 11, 1.8, "below", "none")
    prev = header.item("paraProperties", p.get("paraPrIDRef")).find("hh:margin/hc:prev", NS)
    assert prev.get("value") == str(para_unit_pt(lay.footer_prev))


def test_empty_slots_write_no_control():
    _, section, _ = build(header=Slots(), footer=Slots())
    assert section.find(".//hp:header", NS) is None and section.find(".//hp:footer", NS) is None


def test_reference_header_is_kept_and_filled():
    _, _, package = build(header=Slots(left=("{{title}} 쪽 {{page}}",)), footer=Slots(center=("꼬리",)))

    def fill(text):
        out = []
        for part in text.replace("{{title}}", "제목값").split("{{page}}"):
            if out:
                out.append(PageNumber("page"))
            out.append(part)
        return out

    _, section, _ = build(container=package.write(), header=None, footer=None, fill=fill)
    p = section.find(".//hp:header/hp:subList/hp:p", NS)
    texts = "".join("".join(t.itertext()) for t in p.iter(f"{{{NS['hp']}}}t"))
    assert texts == "제목값 쪽 "
    assert [n.get("numType") for n in p.iter(f"{{{NS['hp']}}}autoNum")] == ["PAGE"]
    assert len(section.findall(".//hp:header", NS)) == 1 and len(section.findall(".//hp:footer", NS)) == 1


def test_container_controls_in_the_section_run_do_not_double_a_yaml_header():
    # Hangul keeps section-level controls in the secPr run; a yaml header must replace them
    _, section, package = build()
    first = section[0]
    sec_run, ctrl_run = first[0], first[1]
    for ctrl in list(ctrl_run):
        sec_run.append(ctrl)
    first.remove(ctrl_run)
    package.set_xml("Contents/section0.xml", section)
    _, section, _ = build(container=package.write())
    assert len(section.findall(".//hp:header", NS)) == 1 and len(section.findall(".//hp:footer", NS)) == 1
