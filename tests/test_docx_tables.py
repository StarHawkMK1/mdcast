import io
import json
import zipfile

import docx
from docx.oxml.ns import qn
from helpers import build, make_reference_docx, write_template
from lxml import etree

from mdcast.types import Format
from mdcast.writers.docx import write_docx

VARIANT_TPL = "name: t\ntables: {variants: {plain: {header: {background: null}, border_outer: {width: 0.5pt}}}}\n"


def render(tmp_path, md, template=None):
    doc, ctx = build(tmp_path, md, Format.DOCX, template=template)
    return write_docx(doc, ctx)


def part(data: bytes, name: str):
    return etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read(name))


def style(styles, style_id):
    return next(s for s in styles.findall(qn("w:style")) if s.get(qn("w:styleId")) == style_id)


def table_style_ids(data: bytes) -> list[str]:
    body = part(data, "word/document.xml").find(qn("w:body"))
    return [t.find(qn("w:tblPr")).find(qn("w:tblStyle")).get(qn("w:val")) for t in body.iter(qn("w:tbl"))]


def first_row_shd(table_style):
    first_row = next((p for p in table_style.findall(qn("w:tblStylePr")) if p.get(qn("w:type")) == "firstRow"), None)
    if first_row is None:
        return None
    shd = first_row.find(qn("w:tcPr")).find(qn("w:shd"))
    return None if shd is None else shd.get(qn("w:fill"))


def test_base_table_style_has_header_fill_and_borders(tmp_path):
    data = render(tmp_path, "| a | b |\n|---|---|\n| 1 | 2 |\n")
    table_style = style(part(data, "word/styles.xml"), "Table")
    assert first_row_shd(table_style) == "F2F2F2"
    borders = table_style.find(qn("w:tblPr")).find(qn("w:tblBorders"))
    assert borders.find(qn("w:top")).get(qn("w:sz")) == "8"
    assert borders.find(qn("w:insideH")).get(qn("w:sz")) == "4"


def test_variant_style_created_and_assigned_to_right_table(tmp_path):
    tpl = write_template(tmp_path, "t", VARIANT_TPL)
    md = "<!-- table: plain -->\n\n| a |\n|---|\n| 1 |\n\n| b |\n|---|\n| 2 |\n"
    data = render(tmp_path, md, str(tpl))
    assert table_style_ids(data) == ["MdcastTable1", "Table"]
    styles = part(data, "word/styles.xml")
    variant = style(styles, "MdcastTable1")
    assert variant.find(qn("w:name")).get(qn("w:val")) == "Table (plain)"
    assert first_row_shd(variant) is None
    assert variant.find(qn("w:tblPr")).find(qn("w:tblBorders")).find(qn("w:top")).get(qn("w:sz")) == "4"
    assert first_row_shd(style(styles, "Table")) == "F2F2F2"


def test_nested_table_does_not_shift_variant(tmp_path):
    tpl = write_template(tmp_path, "t", VARIANT_TPL)
    md = "> | n |\n> |---|\n> | 1 |\n\n<!-- table: plain -->\n\n| a |\n|---|\n| 1 |\n"
    assert table_style_ids(render(tmp_path, md, str(tpl))) == ["Table", "MdcastTable1"]


def test_header_rows_repeat_and_full_width(tmp_path):
    data = render(tmp_path, "| a | b |\n|---|---|\n| 1 | 2 |\n")
    tbl = next(part(data, "word/document.xml").iter(qn("w:tbl")))
    first_tr = tbl.findall(qn("w:tr"))[0]
    assert first_tr.find(qn("w:trPr")).find(qn("w:tblHeader")) is not None
    assert tbl.findall(qn("w:tr"))[1].find(qn("w:trPr")) is None
    width = tbl.find(qn("w:tblPr")).find(qn("w:tblW"))
    assert (width.get(qn("w:type")), width.get(qn("w:w"))) == ("pct", "5000")


def test_custom_container_table_style_wins_but_variants_and_header_apply(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\ntables: {variants: {plain: {header: {background: null}}}}\n")
    make_reference_docx(tpl / "reference.docx")
    reference_style = style(part((tpl / "reference.docx").read_bytes(), "word/styles.xml"), "Table")
    md = "<!-- table: plain -->\n\n| a |\n|---|\n| 1 |\n\n| b |\n|---|\n| 2 |\n"
    data = render(tmp_path, md, str(tpl))
    styles = part(data, "word/styles.xml")
    base = style(styles, "Table")
    assert etree.tostring(base.find(qn("w:tblPr")), method="c14n") == etree.tostring(
        reference_style.find(qn("w:tblPr")), method="c14n"
    )
    assert first_row_shd(base) is None  # the template yaml did not set a header fill
    assert table_style_ids(data) == ["MdcastTable1", "Table"]
    for tbl in part(data, "word/document.xml").iter(qn("w:tbl")):
        assert tbl.find(qn("w:tr")).find(qn("w:trPr")).find(qn("w:tblHeader")) is not None


def test_custom_container_applies_explicit_table_keys(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\ntables: {header: {background: '#DDEEFF'}}\n")
    make_reference_docx(tpl / "reference.docx")
    data = render(tmp_path, "| a |\n|---|\n| 1 |\n", str(tpl))
    assert first_row_shd(style(part(data, "word/styles.xml"), "Table")) == "DDEEFF"


def test_metadata_records_generator_and_title(tmp_path):
    data = render(tmp_path, "---\ntitle: 사업계획\n---\n\n본문\n")
    props = docx.Document(io.BytesIO(data)).core_properties
    assert props.title == "사업계획" and props.keywords == "mdcast"
    assert json.loads(props.comments)["template"]["name"] == "default"


def test_custom_properties_part_has_template_name(tmp_path):
    data = render(tmp_path, "본문\n")
    archive = zipfile.ZipFile(io.BytesIO(data))
    root = etree.fromstring(archive.read("docProps/custom.xml"))
    ns = {"cp": "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties",
          "vt": "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"}
    values = {p.get("name"): p.find("vt:lpwstr", ns).text for p in root.findall("cp:property", ns)}
    assert values["mdcast.template.name"] == "default"
    assert values["mdcast.generator"] == "mdcast test"
    assert min(int(p.get("pid")) for p in root.findall("cp:property", ns)) == 2
    assert "custom.xml" in archive.read("[Content_Types].xml").decode()
    assert "custom-properties" in archive.read("_rels/.rels").decode()
