import io
import zipfile

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from helpers import build, write_template
from lxml import etree
from PIL import Image

from mdcast.types import Format
from mdcast.writers.docx import write_docx

BODY_MM = 170.0  # A4 less the default 20mm margins
CELL_PADDING_MM = 1.5


def png(path, width: int, height: int) -> None:
    Image.new("RGB", (width, height), (40, 120, 200)).save(path, format="PNG")


def render(tmp_path, md, template=None):
    doc, ctx = build(tmp_path, md, Format.DOCX, template=template)
    return write_docx(doc, ctx)


def widths_mm(data: bytes, part: str = "word/document.xml") -> list[float]:
    """Each picture's width in mm, in document order; extent and xfrm must agree."""
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read(part))
    out = []
    for inline in root.iter(qn("wp:inline")):
        cx = inline.find(qn("wp:extent")).get("cx")
        assert inline.find(f".//{qn('a:xfrm')}/{qn('a:ext')}").get("cx") == cx
        out.append(int(cx) / 36000)
    return out


def test_wide_picture_shrinks_to_the_body_width(tmp_path):
    png(tmp_path / "wide.png", 2400, 600)  # 635mm at 96 dpi
    (width,) = widths_mm(render(tmp_path, "![넓은 그림](wide.png)\n"))
    assert width == pytest.approx(BODY_MM, abs=0.05)


@pytest.mark.parametrize(("dpi", "natural_dpi"), [(None, 72), (150, 150)])
def test_small_picture_keeps_its_natural_size(tmp_path, dpi, natural_dpi):
    # a PNG that does not give its dpi is taken at 72, as pandoc and Typst (the PDF) take it
    Image.new("RGB", (200, 100)).save(tmp_path / "small.png", **({"dpi": (dpi, dpi)} if dpi else {}))
    (width,) = widths_mm(render(tmp_path, "![작은 그림](small.png)\n"))
    assert width == pytest.approx(200 / natural_dpi * 25.4, abs=0.05)


def test_percent_width_is_of_the_body_width(tmp_path):
    png(tmp_path / "a.png", 800, 500)
    (width,) = widths_mm(render(tmp_path, "![폭 40%](a.png){width=40%}\n"))
    assert width == pytest.approx(0.4 * BODY_MM, abs=0.05)


@pytest.mark.parametrize("table_width", ["full", "auto"])
def test_pictures_in_cells_fit_their_cell(tmp_path, table_width):
    png(tmp_path / "a.png", 800, 500)
    tpl = write_template(tmp_path, "t", f"name: t\ntables: {{width: {table_width}}}\n")
    md = "| ![](a.png) | ![](a.png) |\n|:---:|:---:|\n| 왼쪽 | 오른쪽 |\n"
    widths = widths_mm(render(tmp_path, md, str(tpl)))
    assert widths == pytest.approx([BODY_MM / 2 - 2 * CELL_PADDING_MM] * 2, abs=0.05)


def test_figures_max_width_caps_pictures(tmp_path):
    png(tmp_path / "wide.png", 2400, 600)
    tpl = write_template(tmp_path, "t", "name: t\nfigures: {max_width: 50%}\n")
    (width,) = widths_mm(render(tmp_path, "![넓은 그림](wide.png)\n", str(tpl)))
    assert width == pytest.approx(BODY_MM / 2, abs=0.05)


def test_picture_in_a_quote_leaves_room_for_the_indent(tmp_path):
    png(tmp_path / "wide.png", 2400, 600)
    (width,) = widths_mm(render(tmp_path, "> ![](wide.png)\n"))
    # quote indent_left 5mm; pandoc's Block Text keeps its right indent of 480 twips
    assert width == pytest.approx(BODY_MM - 5 - 480 / 1440 * 25.4, abs=0.05)


def test_picture_in_a_footnote_is_sized_too(tmp_path):
    png(tmp_path / "a.png", 800, 500)
    data = render(tmp_path, "본문[^1]\n\n[^1]: 각주 ![](a.png){width=40%}\n")
    assert widths_mm(data, "word/footnotes.xml") == pytest.approx([0.4 * BODY_MM], abs=0.05)


def test_figures_follow_figures_align(tmp_path):
    png(tmp_path / "a.png", 200, 100)
    styles = Document(io.BytesIO(render(tmp_path, "![그림](a.png)\n"))).styles
    assert styles["Figure"].paragraph_format.alignment == WD_ALIGN_PARAGRAPH.CENTER
    tpl = write_template(tmp_path, "t", "name: t\nfigures: {align: right}\n")
    styles = Document(io.BytesIO(render(tmp_path, "![그림](a.png)\n", str(tpl)))).styles
    assert styles["Figure"].paragraph_format.alignment == WD_ALIGN_PARAGRAPH.RIGHT


def test_picture_in_a_list_item_leaves_room_for_the_list_indent(tmp_path):
    png(tmp_path / "wide.png", 2400, 600)
    data = render(tmp_path, "- ![](wide.png)\n")
    d = Document(io.BytesIO(data))
    p = next(p for p in d.paragraphs if p._p.find(f".//{qn('wp:inline')}") is not None)
    num = p._p.find(f"{qn('w:pPr')}/{qn('w:numPr')}")
    assert num is not None  # the indent comes from the list level in numbering.xml
    numbering = d.part.numbering_part.element
    num_id = num.find(qn("w:numId")).get(qn("w:val"))
    abstract = next(n for n in numbering.findall(qn("w:num")) if n.get(qn("w:numId")) == num_id)
    abstract_id = abstract.find(qn("w:abstractNumId")).get(qn("w:val"))
    lvl = next(
        a for a in numbering.findall(qn("w:abstractNum")) if a.get(qn("w:abstractNumId")) == abstract_id
    ).find(qn("w:lvl"))
    left = int(lvl.find(f"{qn('w:pPr')}/{qn('w:ind')}").get(qn("w:left")))
    (width,) = widths_mm(data)
    assert left > 0
    assert width == pytest.approx(BODY_MM - left / 1440 * 25.4, abs=0.05)
