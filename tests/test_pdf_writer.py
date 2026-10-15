import pypdfium2 as pdfium
from helpers import build, write_template

from mdcast.report import Codes
from mdcast.types import Format
from mdcast.writers.pdf import write_pdf


def render(tmp_path, md, template=None):
    doc, ctx = build(tmp_path, md, Format.PDF, template=template)
    return write_pdf(doc, ctx), ctx


def pages_text(data: bytes) -> list[str]:
    pdf = pdfium.PdfDocument(data)
    return [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]


def norm(text: str) -> str:
    return " ".join(text.split())


def test_pdf_has_body_header_footer(tmp_path):
    data, _ = render(tmp_path, "---\ntitle: 사업계획\n---\n\n# 개요\n\n본문 문단\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert data.startswith(b"%PDF")
    text = norm(pages_text(data)[0])
    for expected in ("개요", "본문 문단", "사업계획", "1 / 1"):
        assert expected in text


def test_pagebreak_makes_second_page(tmp_path):
    data, _ = render(tmp_path, "가\n\n<!-- pagebreak -->\n\n나\n")
    assert len(pages_text(data)) == 2


def test_korean_list_numbering_and_caption(tmp_path):
    md = "1. 첫째\n    1. 둘째\n\nTable: 요약\n\n| a |\n|---|\n| 1 |\n"
    text = pages_text(render(tmp_path, md)[0])[0]
    assert "가." in text and "<표 1> 요약" in text


def test_table_variant_renders(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\ntables: {variants: {plain: {header: {background: null}}}}\n")
    data, ctx = render(tmp_path, "<!-- table: plain -->\n\n| x |\n|---|\n| 1 |\n", str(tpl))
    assert "x" in pages_text(data)[0]
    assert '#mdcast-table(cfg, "plain", 1)[' in (ctx.work_dir / "main.typ").read_text(encoding="utf-8")


def test_unknown_primary_font_reports_fallback(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nfonts: {body: {family: 없는글꼴xyz, fallback: []}}\n")
    data, ctx = render(tmp_path, "본문\n", str(tpl))
    assert data.startswith(b"%PDF")
    fonts = [e.where["font"] for e in ctx.report.events if e.code == Codes.FONT_FALLBACK]
    assert "없는글꼴xyz" in fonts


def test_broken_custom_layout_falls_back_to_builtin(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\n", {"pdf.typ": b"#let conf = ("})
    data, ctx = render(tmp_path, "본문\n", str(tpl))
    assert data.startswith(b"%PDF")
    assert Codes.TEMPLATE_INVALID in [e.code for e in ctx.report.events]


def test_ordered_list_style_does_not_override_template_numbering(tmp_path):
    _, ctx = render(tmp_path, "1) a\n2) b\n")
    assert "#set enum(numbering:" not in (ctx.work_dir / "main.typ").read_text(encoding="utf-8")
