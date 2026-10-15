import io
import json
import zipfile

import docx
import pytest
from docx.oxml.ns import qn
from helpers import build, make_reference_docx, write_template
from lxml import etree

from mdcast.report import Codes, Report
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
    assert values["mdcast.generator"].startswith("mdcast ")
    assert values["mdcast.typst"] and values["mdcast.pandoc"]
    assert min(int(p.get("pid")) for p in root.findall("cp:property", ns)) == 2
    assert "custom.xml" in archive.read("[Content_Types].xml").decode()
    assert "custom-properties" in archive.read("_rels/.rels").decode()


CP = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
VT = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"


def add_custom_xml(path, blob: bytes) -> None:
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part

    reference = docx.Document(str(path))
    package = reference.part.package
    for rel in package.rels.values():
        if rel.reltype == RT.CUSTOM_PROPERTIES:
            rel.target_part._blob = blob
            reference.save(str(path))
            return
    part_ = Part(PackURI("/docProps/custom.xml"), "application/vnd.openxmlformats-officedocument.custom-properties+xml", blob, package)
    package.relate_to(part_, RT.CUSTOM_PROPERTIES)
    reference.save(str(path))


def custom_values(data: bytes) -> dict[str, str]:
    root = part(data, "docProps/custom.xml")
    return {p.get("name"): p[0].text for p in root.findall(f"{{{CP}}}property")}


def seeded_document(tmp_path, blob: bytes):
    # pandoc does not carry a reference.docx's custom.xml into its output, so seed the finished document
    path = tmp_path / "seed.docx"
    docx.Document().save(str(path))
    add_custom_xml(path, blob)
    return docx.Document(str(path))


def apply_to(d, report):
    from mdcast.fields import ResolvedFields
    from mdcast.writers.docx.meta import apply_metadata

    generator = {"generator": "mdcast test", "pandoc": "3.9", "template": {"name": "t"}}
    apply_metadata(d, generator, ResolvedFields({}, report), report)
    buffer = io.BytesIO()
    d.save(buffer)
    return buffer.getvalue()


def test_custom_properties_merge_keeps_foreign_and_replaces_ours(tmp_path):
    blob = (
        f'<Properties xmlns="{CP}" xmlns:vt="{VT}">'
        '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="Company"><vt:lpwstr>ACME</vt:lpwstr></property>'
        '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="3" name="mdcast.pandoc"><vt:lpwstr>stale</vt:lpwstr></property>'
        "</Properties>"
    ).encode()
    data = apply_to(seeded_document(tmp_path, blob), Report("doc.md", Format.MD))
    values = custom_values(data)
    assert values["Company"] == "ACME"
    assert values["mdcast.template.name"] == "t"
    assert values["mdcast.pandoc"] == "3.9"
    assert len(zipfile.ZipFile(io.BytesIO(data)).namelist()) == len(set(zipfile.ZipFile(io.BytesIO(data)).namelist()))


def test_malformed_custom_xml_is_replaced_with_warning(tmp_path):
    report = Report("doc.md", Format.MD)
    data = apply_to(seeded_document(tmp_path, b"<Properties><oops"), report)
    assert custom_values(data)["mdcast.template.name"] == "t"
    assert [(e.code, e.where.get("format")) for e in report.events] == [(Codes.TEMPLATE_INVALID, "docx")]


def test_doctype_entity_custom_xml_is_replaced_with_warning(tmp_path):
    blob = (
        '<?xml version="1.0"?><!DOCTYPE Properties [<!ENTITY x "boom">]>'
        f'<Properties xmlns="{CP}" xmlns:vt="{VT}">'
        '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="Company"><vt:lpwstr>&x;</vt:lpwstr></property>'
        "</Properties>"
    ).encode()
    report = Report("doc.md", Format.MD)
    data = apply_to(seeded_document(tmp_path, blob), report)
    raw = zipfile.ZipFile(io.BytesIO(data)).read("docProps/custom.xml")
    root = etree.fromstring(raw, etree.XMLParser(resolve_entities=False, load_dtd=False))
    assert b"&x;" not in raw and b"DOCTYPE" not in raw and next(root.iter(etree.Entity), None) is None
    assert custom_values(data)["mdcast.template.name"] == "t"
    assert [(e.code, e.where.get("format")) for e in report.events] == [(Codes.TEMPLATE_INVALID, "docx")]


def test_record_count_mismatch_applies_no_variants_and_warns(tmp_path):
    from mdcast.writers.docx.tables import apply_tables

    tpl = write_template(tmp_path, "t", VARIANT_TPL)
    md = "| a |\n|---|\n| 1 |\n\n| b |\n|---|\n| 2 |\n"
    doc, ctx = build(tmp_path, md, Format.DOCX, template=str(tpl))
    d = docx.Document(io.BytesIO(write_docx(doc, ctx)))
    report = Report("doc.md", Format.MD)
    apply_tables(d, ctx.template.config, None, [{"variant": "plain", "head_rows": 1}], report)
    ids = [t.find(qn("w:tblPr")).find(qn("w:tblStyle")).get(qn("w:val")) for t in d.element.body.iter(qn("w:tbl"))]
    assert ids == ["Table", "Table"]
    assert len(report.events) == 1 and report.events[0].where.get("format") == "docx"
    assert not any(st.style_id.startswith("MdcastTable") for st in d.styles)


@pytest.mark.parametrize("url", ["none.png", "data:image/png;base64,iVBORw0KGgo="])
def test_failed_figure_image_keeps_table_variants(tmp_path, url):
    tpl = write_template(tmp_path, "t", VARIANT_TPL)
    md = f"![없는 그림]({url})\n\n<!-- table: plain -->\n\n| a |\n|---|\n| 1 |\n"
    doc, ctx = build(tmp_path, md, Format.DOCX, template=str(tpl))
    data = write_docx(doc, ctx)
    assert table_style_ids(data) == ["MdcastTable1"]
    codes = [e.code for e in ctx.report.events]
    assert Codes.IMAGE_FETCH_FAILED in codes
    assert Codes.STYLE_UNMAPPED not in codes and Codes.RENDER_WARNING not in codes
