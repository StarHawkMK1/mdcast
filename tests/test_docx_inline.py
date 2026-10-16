import io
import zipfile

from docx.oxml.ns import qn
from helpers import build, tiny_png
from lxml import etree

from mdcast.types import Format
from mdcast.writers.docx import write_docx


def render(tmp_path, md):
    doc, ctx = build(tmp_path, md, Format.DOCX)
    return write_docx(doc, ctx)


def spacing_by_text(data: bytes, part: str) -> dict[str, tuple[str | None, str | None]]:
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read(part))
    out = {}
    for p in root.iter(qn("w:p")):
        text = "".join(t.text or "" for t in p.iter(qn("w:t"))).strip()
        if not text:
            continue
        ppr = p.find(qn("w:pPr"))
        spacing = None if ppr is None else ppr.find(qn("w:spacing"))
        out[text] = (None, None) if spacing is None else (spacing.get(qn("w:line")), spacing.get(qn("w:lineRule")))
    return out


def test_inline_image_paragraph_grows_instead_of_clipping(tmp_path):
    (tmp_path / "a.png").write_bytes(tiny_png())
    found = spacing_by_text(render(tmp_path, "앞 ![](a.png){width=3cm} 뒤\n\n그냥 문단\n"), "word/document.xml")
    assert found["앞  뒤"] == ("352", "atLeast")
    assert found["그냥 문단"] == (None, None)  # the style's exact line applies


def test_inline_math_paragraph_grows(tmp_path):
    found = spacing_by_text(render(tmp_path, "식 $\\frac{a}{b}$ 끝\n"), "word/document.xml")
    assert found["식  끝"] == ("352", "atLeast")


def test_math_in_a_table_cell_grows(tmp_path):
    found = spacing_by_text(render(tmp_path, "| 칸 |\n|---|\n| 셀 $\\frac{a}{b}$ |\n"), "word/document.xml")
    assert found["셀"] == ("260", "atLeast")


def test_math_in_a_footnote_grows(tmp_path):
    found = spacing_by_text(render(tmp_path, "본문[^1]\n\n[^1]: 각주 $\\frac{a}{b}$\n"), "word/footnotes.xml")
    assert found["각주"] == ("234", "atLeast")  # Footnote Text: 9pt × 130%
