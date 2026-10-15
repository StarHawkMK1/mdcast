import io

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Mm, Pt
from helpers import build, make_reference_docx, write_template

from mdcast.report import Codes
from mdcast.types import Format
from mdcast.writers.docx import write_docx


def render(tmp_path, md, template=None):
    doc, ctx = build(tmp_path, md, Format.DOCX, template=template)
    return docx.Document(io.BytesIO(write_docx(doc, ctx))), ctx


def test_page_setup_from_template(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\npage: {size: A5, orientation: landscape, margin: {top: 10mm, bottom: 10mm, left: 12mm, right: 12mm}}\n")
    d, _ = render(tmp_path, "본문\n", str(tpl))
    s = d.sections[0]
    assert (round(s.page_width.mm), round(s.page_height.mm)) == (210, 148)
    assert round(s.top_margin.mm) == 10 and round(s.left_margin.mm) == 12


def test_default_element_looks(tmp_path):
    d, _ = render(tmp_path, "# 제목\n\n본문\n")
    h1 = d.styles["Heading 1"]
    assert h1.font.size.pt == 16 and str(h1.font.color.rgb) == "1F3864"
    body = d.styles["Body Text"]
    assert body.font.size.pt == 11
    assert body.paragraph_format.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY
    assert body.paragraph_format.line_spacing == 1.6
    rfonts = d.styles["Normal"].element.rPr.rFonts
    assert rfonts.get(qn("w:eastAsia")) == "맑은 고딕"
    assert rfonts.get(qn("w:ascii")) == "Malgun Gothic"
    assert rfonts.get(qn("w:asciiTheme")) is None


def test_heading_paragraph_remapped_to_custom_style(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nstyles: {heading1: {docx: 보고서 제목1}}\nelements: {heading1: {size: 16pt}}\n")
    make_reference_docx(tpl / "reference.docx", extra_styles=("보고서 제목1",))
    d, ctx = render(tmp_path, "# 제목\n\n본문\n", str(tpl))
    heading = next(p for p in d.paragraphs if p.text == "제목")
    assert heading.style.name == "보고서 제목1"
    assert d.styles["보고서 제목1"].font.size.pt == 16
    assert not [e for e in ctx.report.events if e.code == Codes.STYLE_UNMAPPED]


def test_missing_mapped_style_is_info_and_keeps_pandoc_style(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nstyles: {heading1: {docx: 없는스타일}}\n")
    d, ctx = render(tmp_path, "# 제목\n", str(tpl))
    heading = next(p for p in d.paragraphs if p.text == "제목")
    assert heading.style.name == "Heading 1"
    assert [(e.code, e.where.get("format")) for e in ctx.report.events if e.code == Codes.STYLE_UNMAPPED] == [
        (Codes.STYLE_UNMAPPED, "docx")
    ]


def test_code_block_style_uses_code_font(tmp_path):
    d, _ = render(tmp_path, "```\nprint(1)\n```\n")
    names = {s.name for s in d.styles}
    assert "Source Code" in names
    assert d.styles["Source Code"].font.name == "Consolas"


def test_corrupt_custom_reference_falls_back_to_builtin_container(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\n", {"reference.docx": b"not a zip"})
    d, ctx = render(tmp_path, "# 제목\n", str(tpl))
    assert any(p.text == "제목" for p in d.paragraphs)
    assert [(e.code, e.where.get("format")) for e in ctx.report.events if e.code == Codes.TEMPLATE_INVALID] == [
        (Codes.TEMPLATE_INVALID, "docx")
    ]


def test_custom_container_keeps_its_own_values_unless_yaml_sets_them(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nelements: {body: {size: 13pt}}\n")
    ref = make_reference_docx(tpl / "reference.docx")
    reference = docx.Document(str(ref))
    reference.styles["Heading 1"].font.size = Pt(20)
    reference.sections[0].page_width = Mm(150)
    reference.save(str(ref))
    d, _ = render(tmp_path, "# 제목\n\n본문\n", str(tpl))
    assert d.styles["Heading 1"].font.size.pt == 20
    assert d.styles["Body Text"].font.size.pt == 13
    assert round(d.sections[0].page_width.mm) == 150
