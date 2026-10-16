from pathlib import Path

import pypdfium2 as pdfium
import pytest
from helpers import build, line_pitch, write_template

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


def test_typst_source_has_plain_newlines(tmp_path):
    # pandoc wraps long paragraphs; on Windows a "\r\r\n" line end reads as a blank line to
    # Typst, which split every wrapped source line into its own paragraph
    md = "줄 간격을 보기 위해 충분히 긴 문장을 씁니다. " * 8 + "\n\n- 하나\n- 둘\n"
    _, ctx = render(tmp_path, md)
    assert b"\r" not in (ctx.work_dir / "main.typ").read_bytes()


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


def test_custom_layout_copy_failure_falls_back_to_builtin(tmp_path, monkeypatch):
    import shutil

    import mdcast.writers.pdf as pdf_mod

    tpl = write_template(tmp_path, "t", "name: t\n", {"pdf.typ": b"#let conf(cfg, doc) = doc\n"})
    doc, ctx = build(tmp_path, "본문\n", Format.PDF, template=str(tpl))
    real = shutil.copyfile

    def flaky(src, dst, *a, **k):
        if Path(src).parent.name == "t":
            raise OSError("boom")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(pdf_mod.shutil, "copyfile", flaky)
    assert write_pdf(doc, ctx).startswith(b"%PDF")
    assert Codes.TEMPLATE_INVALID in [e.code for e in ctx.report.events]


def test_default_pdf_embeds_malgun_when_installed(tmp_path):
    import typst

    probe = tmp_path / "p.typ"
    probe.write_text('#set text(font: "Malgun Gothic")\n가', encoding="utf-8")
    _, warnings = typst.compile_with_warnings(str(probe), root=str(tmp_path))
    if any("unknown font family" in w.message.lower() for w in warnings):
        pytest.skip("Malgun Gothic not installed")
    data, ctx = render(tmp_path, "본문\n")
    assert b"MalgunGothic" in data
    assert Codes.FONT_FALLBACK not in [e.code for e in ctx.report.events]


def long_table_md(rows: int = 120) -> str:
    lines = ["| 번호 | 항목 |", "|---|---|"]
    lines += [f"| {i} | 행{i:03d} |" for i in range(1, rows + 1)]
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("width", ["full", "auto"])
def test_long_table_breaks_across_pages_with_repeated_header(tmp_path, width):
    tpl = write_template(tmp_path, "t", f"name: t\ntables: {{width: {width}}}\n")
    data, _ = render(tmp_path, long_table_md(), str(tpl))
    texts = [norm(t) for t in pages_text(data)]
    assert len(texts) > 1
    assert "행001" in texts[0]
    assert "행120" in texts[-1]
    assert "항목" in texts[1]
    for i in range(1, 121):
        assert sum(f"행{i:03d}" in t for t in texts) == 1, i


def test_image_typst_cannot_decode_becomes_placeholder(tmp_path):
    (tmp_path / "odd.jpg").write_bytes(b"\xff\xd8\xff\xe0" + bytes(64))
    data, ctx = render(tmp_path, "앞 ![이상한 그림](odd.jpg) 뒤\n")
    assert "[이미지: 이상한 그림]" in norm(pages_text(data)[0])
    events = [(e.code, e.where.get("format")) for e in ctx.report.events if e.code != Codes.FIELD_EMPTY]
    assert events == [(Codes.IMAGE_FETCH_FAILED, "pdf")]


def test_label_of_a_figure_that_lost_its_image_survives(tmp_path):
    from helpers import tiny_bmp

    (tmp_path / "pic.bmp").write_bytes(tiny_bmp())
    md = "![그림 설명](pic.bmp){#fig-a}\n\n[그림 참조](#fig-a)\n"
    data, ctx = render(tmp_path, md)
    text = norm(pages_text(data)[0])
    assert "[이미지: 그림 설명]" in text and "그림 참조" in text
    assert "<fig-a>" in (ctx.work_dir / "main.typ").read_text(encoding="utf-8")
    assert Codes.IMAGE_FETCH_FAILED in [e.code for e in ctx.report.events]


def test_label_of_an_inline_image_that_became_a_placeholder_survives(tmp_path):
    md = "앞 ![설명](none.png){#img-a} 뒤\n\n[참조](#img-a)\n"
    data, ctx = render(tmp_path, md)
    text = norm(pages_text(data)[0])
    assert "[이미지: 설명]" in text and "참조" in text
    assert "<img-a>" in (ctx.work_dir / "main.typ").read_text(encoding="utf-8")
    assert Codes.IMAGE_FETCH_FAILED in [e.code for e in ctx.report.events]


LONG = "줄 간격을 보기 위해 충분히 긴 문장을 씁니다. " * 6


@pytest.mark.parametrize(
    ("md", "needle", "pitch"),
    [
        (f"본문{LONG}\n", "본문", 11 * 1.8),
        ("- 목록 하나\n- 목록 둘\n", "목록 하나", 11 * 1.8),
        (f"# 제목{LONG}\n", "제목", 16 * 1.3),
        (f"| 칸 |\n|---|\n| 셀{LONG} |\n", "셀", 10 * 1.3),
        ("```\n코드 첫째 줄\n코드 둘째 줄\n```\n", "코드 첫째", 9.5 * 1.3),
    ],
)
def test_line_pitch_is_size_times_line_height(tmp_path, md, needle, pitch):
    assert line_pitch(render(tmp_path, md)[0], needle) == pytest.approx(pitch, abs=0.3)


def test_table_variant_line_height(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\ntables: {variants: {dense: {line_height: 100%}}}\n")
    md = f"<!-- table: dense -->\n\n| 칸 |\n|---|\n| 셀{LONG} |\n"
    assert line_pitch(render(tmp_path, md, str(tpl))[0], "셀") == pytest.approx(10.0, abs=0.3)


def test_paragraphs_in_one_cell_have_no_gap(tmp_path):
    # as in the docx cells (before/after 0): the next paragraph sits one line pitch below
    rule, head = "+" + "-" * 40 + "+\n", "+" + "=" * 40 + "+\n"
    # grid tables align by display width; a Hangul syllable takes two columns
    row = lambda text: "| " + text + " " * (38 - 2 * len(text)) + " |\n"
    md = rule + row("칸") + head + row("첫째") + row("") + row("둘째") + rule
    assert line_pitch(render(tmp_path, md)[0], "첫째") == pytest.approx(10 * 1.3, abs=0.3)


@pytest.mark.parametrize("ratio", ["50%", "2000%"])
def test_extreme_line_heights_still_compile(tmp_path, ratio):
    tpl = write_template(tmp_path, "t", f"name: t\nelements: {{body: {{line_height: {ratio}}}}}\n")
    data, _ = render(tmp_path, f"본문{LONG}\n", str(tpl))
    assert data.startswith(b"%PDF")
