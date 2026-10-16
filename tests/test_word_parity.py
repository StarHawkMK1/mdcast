import sys

import pytest
from helpers import build, line_pitch

from mdcast.types import Format
from mdcast.writers.docx import write_docx
from mdcast.writers.pdf import write_pdf

pytestmark = [pytest.mark.word, pytest.mark.skipif(sys.platform != "win32", reason="needs Microsoft Word")]

LONG = "줄 간격을 보기 위해 충분히 긴 문장을 씁니다. " * 6
MD = f"본문{LONG}\n\n- 목록 하나\n- 목록 둘\n\n# 제목{LONG}\n\n| 칸 |\n|---|\n| 셀{LONG} |\n"


def _word_pdf(docx_path, pdf_path) -> bytes:
    win32 = pytest.importorskip("win32com.client")
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    try:
        document = word.Documents.Open(str(docx_path), ReadOnly=True)
        document.ExportAsFixedFormat(str(pdf_path), 17)  # wdExportFormatPDF
        document.Close(False)
    finally:
        word.Quit()
    return pdf_path.read_bytes()


@pytest.fixture(scope="module")
def pdfs(tmp_path_factory):
    root = tmp_path_factory.mktemp("parity")
    doc, ctx = build(root, MD, Format.DOCX)
    docx_path = root / "out.docx"
    docx_path.write_bytes(write_docx(doc, ctx))
    word = _word_pdf(docx_path, root / "word.pdf")
    doc, ctx = build(root, MD, Format.PDF)
    return word, write_pdf(doc, ctx)


@pytest.mark.parametrize("needle", ["본문", "목록 하나", "제목", "셀"])
def test_word_and_pdf_line_pitch_match(pdfs, needle):
    word, typst = pdfs
    assert line_pitch(word, needle) == pytest.approx(line_pitch(typst, needle), rel=0.05)
