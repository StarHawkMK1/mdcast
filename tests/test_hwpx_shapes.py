from helpers import HWPX_NS as NS
from helpers import builtin_hwpx, hwpx_settings

from mdcast.hwpx.container import Package
from mdcast.hwpx.header import Header
from mdcast.hwpx.look import ELEMENTS, Look, Notices, Settings
from mdcast.hwpx.shapes import build_shapes
from mdcast.hwpx.units import para_unit


def build(settings):
    header = Header(Package.read(builtin_hwpx()).xml("Contents/header.xml"))
    notices = Notices()
    return header, build_shapes(header, settings, notices), notices


def test_every_element_has_a_shape():
    _, shapes, notices = build(hwpx_settings())
    assert set(shapes) == set(ELEMENTS)
    assert notices.items == []


def test_heading_keeps_the_outline_level_and_drops_its_indent():
    header, shapes, _ = build(hwpx_settings())
    shape = shapes["heading1"]
    assert shape.style == "2"
    para = header.item("paraProperties", shape.para)
    assert para.find("hh:heading", NS).get("type") == "OUTLINE"
    assert para.find("hh:margin/hc:left", NS).get("value") == "0"
    char = header.item("charProperties", shape.char)
    assert char.get("height") == "1600" and char.find("hh:bold", NS) is not None


def test_body_values():
    header, shapes, _ = build(hwpx_settings())
    para = header.item("paraProperties", shapes["body"].para)
    assert para.find("hh:lineSpacing", NS).get("value") == "180"
    assert para.find("hh:align", NS).get("horizontal") == "JUSTIFY"
    assert para.find("hh:margin/hc:next", NS).get("value") == "800"


def test_missing_style_falls_back_with_one_notice():
    _, shapes, notices = build(Settings(styles={"quote": "인용", "code": "인용"}))
    assert shapes["quote"].style == "0"
    assert sorted((n.kind, n.element) for n in notices.items) == [
        ("style-missing", "code"),
        ("style-missing", "quote"),
    ]


def test_background_pads_the_paragraph():
    header, shapes, _ = build(hwpx_settings())
    para = header.item("paraProperties", shapes["code"].para)
    border = para.find("hh:border", NS)
    # Hangul's background box already holds the paragraph's margins and gaps: no offsets
    assert [border.get(k) for k in ("offsetLeft", "offsetRight", "offsetTop", "offsetBottom")] == ["0"] * 4
    assert border.get("connect") == "0"
    assert para.find("hh:margin/hc:left", NS).get("value") == str(para_unit(2.0))
    assert para.find("hh:margin/hc:right", NS).get("value") == str(para_unit(2.0))
    assert para.find("hh:margin/hc:prev", NS).get("value") == str(para_unit(2.0))
    fill = header.item("borderFills", border.get("borderFillIDRef"))
    assert fill.find("hc:fillBrush/hc:winBrush", NS).get("faceColor") == "#F6F8FA"


def test_none_keeps_the_container_value():
    header, shapes, _ = build(Settings(looks={"body": Look()}, styles={"body": "바탕글"}))
    base = header.item("paraProperties", "0")
    para = header.item("paraProperties", shapes["body"].para)
    assert para.find("hh:lineSpacing", NS).get("value") == base.find("hh:lineSpacing", NS).get("value")
    assert para.find("hh:align", NS).get("horizontal") == base.find("hh:align", NS).get("horizontal")


def test_code_keeps_a_korean_font_for_hangul_text():
    # Consolas has no Hangul: without this Hangul substitutes a serif face (docx shows 맑은 고딕)
    header, shapes, _ = build(hwpx_settings())
    ref = header.item("charProperties", shapes["code"].char).find("hh:fontRef", NS)
    faces = {}
    for face in header.root.iter(f"{{{NS['hh']}}}fontface"):
        lang = face.get("lang").lower()
        faces[lang] = next(f.get("face") for f in face.findall("hh:font", NS) if f.get("id") == ref.get(lang))
    assert faces["hangul"] == "맑은 고딕" and faces["latin"] == "Consolas"
