from dataclasses import replace

import pytest
from helpers import HWPX_NS as NS
from helpers import (
    build,
    builtin_hwpx,
    hwpx_integrity,
    hwpx_render,
    hwpx_settings,
    hwpx_texts,
    tiny_png,
)

from mdcast.hwpx.container import Package
from mdcast.hwpx.look import Image
from mdcast.hwpx.picture import Pictures, parse_length, picture_element, picture_size
from mdcast.hwpx.units import hwpunit
from mdcast.types import Format
from mdcast.writers.hwpx import write_hwpx

PNG400 = Image(data=b"png-bytes", ext="png", width_px=400, height_px=200, dpi=96.0)


def render(tmp_path, md, template=None):
    doc, ctx = build(tmp_path, md, Format.HWPX, template=template)
    return hwpx_integrity(write_hwpx(doc, ctx)), ctx


def test_picture_size_rules():
    assert picture_size(PNG400, None, None, 170.0, 1.0, None) == pytest.approx((105.833, 52.917), rel=1e-3)
    assert picture_size(PNG400, "50%", None, 170.0, 1.0, None) == pytest.approx((85.0, 42.5))
    assert picture_size(PNG400, "60mm", "10mm", 170.0, 1.0, None) == pytest.approx((60.0, 10.0))
    assert picture_size(PNG400, None, None, 80.0, 1.0, None) == pytest.approx((80.0, 40.0))
    assert picture_size(PNG400, None, None, 170.0, None, 50.0) == pytest.approx((50.0, 25.0))
    assert picture_size(replace(PNG400, dpi=300.0), None, None, 170.0, 1.0, None)[0] == pytest.approx(33.867, rel=1e-3)


@pytest.mark.parametrize("value, mm", [("50%", 85.0), ("60mm", 60.0), ("6cm", 60.0), ("1in", 25.4),
                                       ("72pt", 25.4), ("96px", 25.4), ("96", 25.4), ("auto", None)])
def test_parse_length(value, mm):
    assert parse_length(value, 170.0) == (None if mm is None else pytest.approx(mm))


def test_picture_element_follows_the_sample():
    pic = picture_element("mdcastimg1", PNG400, 50.0, 25.0, "설명", 7, None)
    assert pic.find("hp:orgSz", NS).attrib == {"width": "37500", "height": "18750"}
    assert pic.find("hp:imgDim", NS).attrib == {"dimwidth": "30000", "dimheight": "15000"}
    assert pic.find("hp:sz", NS).get("width") == str(hwpunit(50.0))
    assert pic.find("hp:curSz", NS).get("width") == str(hwpunit(50.0))
    assert pic.find("hc:img", NS).get("binaryItemIDRef") == "mdcastimg1"
    assert pic.find("hp:pos", NS).get("treatAsChar") == "1"
    assert pic.find("hp:shapeComment", NS).text == "설명"
    svg = picture_element("x", replace(PNG400, ext="svg"), 50.0, 25.0, "", 1, None)
    assert svg.find("hp:orgSz", NS).get("width") == "30000" and svg.find("hp:imgDim", NS).get("dimwidth") == "24000"


def test_same_image_shares_one_bindata():
    package = Package.read(builtin_hwpx())
    content = package.xml("Contents/content.hpf")
    pictures = Pictures(package, content)
    assert pictures.add(PNG400) == pictures.add(replace(PNG400)) == "mdcastimg1"
    assert [n for n in package.names() if n.startswith("BinData/")] == ["BinData/mdcastimg1.png"]


def test_pictures_do_not_clash_with_container_bindata():
    package = Package.read(builtin_hwpx())
    package.set("BinData/mdcastimg1.png", b"old")
    content = package.xml("Contents/content.hpf")
    item_id = Pictures(package, content).add(PNG400)
    assert item_id == "mdcastimg2" and package.get("BinData/mdcastimg1.png") == b"old"
    items = [i for i in content.iter("{http://www.idpf.org/2007/opf/}item") if i.get("id") == "mdcastimg2"]
    assert items[0].attrib == {"id": "mdcastimg2", "href": "BinData/mdcastimg2.png",
                               "media-type": "image/png", "isEmbeded": "1"}


def test_inline_and_figure_pictures_in_the_section():
    images = {"a.png": PNG400}
    _, _, paragraphs, _ = hwpx_render("앞 ![작게](a.png){width=20mm} 뒤\n\n![그림 설명](a.png)\n",
                                      hwpx_settings(images=images))
    inline, figure = paragraphs
    assert hwpx_texts([inline]) == ["앞  뒤"]
    assert inline.find(".//hp:pic/hp:sz", NS).get("width") == str(hwpunit(20.0))
    caption = figure.find(".//hp:pic/hp:caption", NS)
    assert caption.get("side") == "BOTTOM" and "그림 설명" in "".join(caption.itertext())


@pytest.mark.parametrize("above", [False, True])
def test_caption_wider_than_its_picture_is_a_paragraph_of_its_own(above):
    # Hangul draws a picture's caption only as wide as the picture: a narrow one wraps or vanishes
    md = "![긴 설명이 달린 작은 그림](a.png){width=8mm}\n"
    _, shapes, paragraphs, _ = hwpx_render(md, hwpx_settings(images={"a.png": PNG400}, figure_caption_above=above))
    assert all(p.find(".//hp:caption", NS) is None for p in paragraphs)
    texts = hwpx_texts(paragraphs)
    caption = texts.index("긴 설명이 달린 작은 그림")
    picture = next(i for i, p in enumerate(paragraphs) if p.find(".//hp:pic", NS) is not None)
    assert caption == (picture - 1 if above else picture + 1)
    assert paragraphs[caption].get("styleIDRef") == shapes["caption"].style


def test_picture_in_quote_fits_the_indented_width():
    wide = Image(data=b"w", ext="png", width_px=4000, height_px=1000)
    _, _, paragraphs, _ = hwpx_render("> ![넓은 그림](w.png)\n", hwpx_settings(images={"w.png": wide}))
    assert int(paragraphs[0].find(".//hp:pic/hp:sz", NS).get("width")) == hwpunit(170.0 - 5.0)


def test_picture_in_a_cell_fits_the_cell():
    wide = Image(data=b"w", ext="png", width_px=4000, height_px=1000)
    _, _, paragraphs, _ = hwpx_render("| ![a](w.png) | b |\n|---|---|\n| 1 | 2 |\n",
                                      hwpx_settings(images={"w.png": wide}))
    cell = paragraphs[0].find(".//hp:tc", NS)
    pic = cell.find(".//hp:pic", NS)
    assert int(pic.find("hp:sz", NS).get("width")) <= int(cell.find("hp:cellSz", NS).get("width")) - 2 * hwpunit(1.5)


def test_write_registers_bindata_and_manifest(tmp_path):
    (tmp_path / "a.png").write_bytes(tiny_png())
    parts, _ = render(tmp_path, "![그림](a.png)\n")
    pic = next(parts["Contents/section0.xml"].iter(f"{{{NS['hp']}}}pic"))
    item_id = pic.find("hc:img", NS).get("binaryItemIDRef")
    hrefs = {i.get("id"): i.get("href") for i in parts["Contents/content.hpf"].iter(f"{{{NS['opf']}}}item")}
    assert hrefs[item_id].startswith("BinData/mdcastimg")


@pytest.mark.parametrize("md", ["- 글 ![a](w.png)\n", "10. 글 ![a](w.png)\n", "- 바깥\n    - 안 ![a](w.png)\n"])
def test_picture_in_a_list_items_first_paragraph_fits_after_the_marker(md):
    wide = Image(data=b"w", ext="png", width_px=4000, height_px=1000)
    _, _, paragraphs, _ = hwpx_render(md, hwpx_settings(images={"w.png": wide}))
    p = next(p for p in paragraphs if p.find(".//hp:pic", NS) is not None)
    width = int(p.find(".//hp:pic/hp:sz", NS).get("width"))
    assert width <= hwpunit(170.0 - 3.0)  # the item text starts at least 3mm (the narrowest hanging) in
