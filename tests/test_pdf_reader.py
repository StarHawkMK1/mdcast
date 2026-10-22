from __future__ import annotations

import io

import panflute as pf
import pdfplumber
import pytest
from click.testing import CliRunner
from helpers import tiny_png
from pdf_builder import typst_pdf
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException

from mdcast.cli import main
from mdcast.pipeline import convert
from mdcast.readers.pdf import read_pdf
from mdcast.readers.pdf.lines import is_bold, page_lines
from mdcast.readers.pdf.model import Box
from mdcast.readers.pdf.package import generator_from_keywords
from mdcast.report import Codes, Level, Report
from mdcast.types import Format, Source

MDCAST_KEYWORDS = (
    "mdcast, mdcast:0.1.0, pandoc:3.9, typst:0.15.0, "
    "template:default, template-version:1.0.0, template-source:builtin"
)


def pdf_source(data: bytes, name: str = "a.pdf") -> Source:
    return Source(data, name, Format.PDF)


def imported(data: bytes):
    return read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets")


def char(text: str, x0: float, top: float, *, size: float = 10.0, font: str = "Body-Regular", upright: bool = True):
    """A pdfplumber-like char dict, as wide as it is tall."""
    width = size if text.strip() else size / 4
    return {"text": text, "fontname": font, "size": size, "upright": upright,
            "x0": x0, "x1": x0 + width, "top": top, "bottom": top + size}


def word(text: str, x0: float, top: float, **kw) -> list[dict]:
    size = kw.get("size", 10.0)
    return [char(c, x0 + i * size, top, **kw) for i, c in enumerate(text)]


def test_text_pdf_imports_to_md():
    result = convert(pdf_source(typst_pdf("첫 줄 글\n\n둘째 문단 글")), [Format.MD])
    md = result.outputs[0].data.decode("utf-8")
    assert "첫 줄 글" in md and "둘째 문단 글" in md
    assert not [e for e in result.report.events if e.level is Level.ERROR]
    assert result.report.coverage == 1.0


def test_broken_pdf_is_input_corrupt():
    result = convert(pdf_source(b"%PDF-1.7 garbage"), [Format.MD])
    errors = [e for e in result.report.events if e.level is Level.ERROR]
    assert [e.code for e in errors] == [Codes.INPUT_CORRUPT]
    assert "PDF 파일로 열 수 없습니다" in errors[0].message and "Traceback" not in errors[0].message
    assert result.outputs[0].data is None


def test_unreadable_page_tree_is_input_corrupt(monkeypatch):
    def broken(self):
        raise ValueError("bad page tree")

    monkeypatch.setattr(pdfplumber.PDF, "pages", property(broken))
    result = convert(pdf_source(typst_pdf("본문")), [Format.MD])
    errors = [e for e in result.report.events if e.level is Level.ERROR]
    assert [e.code for e in errors] == [Codes.INPUT_CORRUPT]
    assert "PDF 파일로 열 수 없습니다" in errors[0].message


@pytest.mark.parametrize(
    "exc",
    # pdfplumber wraps what pdfminer raises; a bare one stands for any other caller
    [PDFPasswordIncorrect(), PdfminerException(PDFPasswordIncorrect())],
    ids=["bare", "wrapped"],
)
def test_password_pdf_message(monkeypatch, exc):
    def locked(*args, **kwargs):
        raise exc

    monkeypatch.setattr(pdfplumber, "open", locked)
    result = convert(pdf_source(typst_pdf("본문")), [Format.MD])
    errors = [e for e in result.report.events if e.level is Level.ERROR]
    assert [e.code for e in errors] == [Codes.INPUT_CORRUPT]
    assert "암호" in errors[0].message and "다시 저장" in errors[0].message


def test_metadata_frontmatter():
    data = typst_pdf('#set document(title: "제목", author: "가나")\n본문')
    imp = imported(data)
    assert imp.frontmatter == {"title": "제목", "author": "가나"}
    assert imp.generator == {}


def test_mdcast_keywords_reach_generator():
    keywords = ", ".join(f'"{k.strip()}"' for k in MDCAST_KEYWORDS.split(","))
    imp = imported(typst_pdf(f"#set document(keywords: ({keywords}))\n본문"))
    assert imp.generator["mdcast.template.name"] == "default"
    assert imp.generator["mdcast.generator"] == "mdcast 0.1.0"


def _with_metadata(monkeypatch, metadata):
    real_open = pdfplumber.open

    def opened(*args, **kwargs):
        pdf = real_open(*args, **kwargs)
        pdf.metadata = metadata
        return pdf

    monkeypatch.setattr(pdfplumber, "open", opened)


class _BrokenMetadata(dict):
    def get(self, *args, **kwargs):
        raise ValueError("unreadable")

    def __getitem__(self, key):
        raise ValueError("unreadable")


def test_unreadable_metadata_keeps_body(monkeypatch):
    data = typst_pdf(
        '#set document(title: "제목", author: "가나", keywords: ("mdcast", "template:x"))\n본문 글'
    )
    assert imported(data).frontmatter  # the document does carry metadata
    _with_metadata(monkeypatch, _BrokenMetadata())
    imp = imported(data)
    assert imp.frontmatter == {} and imp.generator == {}
    assert [pf.stringify(b).strip() for b in imp.doc.content] == ["본문 글"]


def test_bytes_or_odd_metadata_is_read_or_left_out(monkeypatch):
    _with_metadata(monkeypatch, {
        "Title": "제목".encode(),
        "Author": b"caf\xe9",  # not UTF-8 → latin-1
        "Keywords": b"mdcast, template:x",
    })
    imp = imported(typst_pdf("본문"))
    assert imp.frontmatter == {"title": "제목", "author": "café"}
    assert imp.generator == {"mdcast.template.name": "x"}

    _with_metadata(monkeypatch, {"Title": ["not", "text"], "Author": "  ", "Keywords": 7})
    imp = imported(typst_pdf("본문"))
    assert imp.frontmatter == {} and imp.generator == {}


def test_generator_from_mdcast_keywords():
    assert generator_from_keywords(MDCAST_KEYWORDS) == {
        "mdcast.generator": "mdcast 0.1.0", "mdcast.pandoc": "3.9", "mdcast.typst": "0.15.0",
        "mdcast.template.name": "default", "mdcast.template.version": "1.0.0", "mdcast.template.source": "builtin",
    }
    assert generator_from_keywords("report, draft") == {}
    assert generator_from_keywords(None) == {}
    assert generator_from_keywords(b"mdcast, template:x") == {"mdcast.template.name": "x"}
    assert generator_from_keywords("mdcast-like, template:x") == {}  # only the exact token counts


def test_cli_pdf_defaults_to_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.pdf").write_bytes(typst_pdf("본문 글"))
    r = CliRunner().invoke(main, ["convert", str(tmp_path / "x.pdf")])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "x.md").read_text(encoding="utf-8").strip() == "본문 글"


def test_lines_read_top_to_bottom_then_left_to_right():
    chars = word("아래", 10, 50) + word("오른", 80, 10) + word("왼", 10, 11)
    lines = page_lines(2, chars)
    assert [ln.text for ln in lines] == ["왼 오른", "아래"]
    assert [ln.page for ln in lines] == [2, 2]
    assert lines[0].box == Box(10, 10, 100, 21)


def test_spaces_come_from_gaps_or_space_chars_never_doubled():
    gap = word("가나", 0, 0) + word("다", 25, 0)  # 5pt gap > X_TOLERANCE
    tight = word("가나", 0, 0) + word("다", 22, 0)  # 2pt gap: one word
    spaced = word("가나", 0, 0) + [char(" ", 20, 0), char(" ", 22.5, 0)] + word("다", 30, 0)
    edges = [char(" ", 0, 0)] + word("가", 5, 0) + [char(" ", 15, 0)]
    assert page_lines(0, gap)[0].text == "가나 다"
    assert page_lines(0, tight)[0].text == "가나다"
    assert page_lines(0, spaced)[0].text == "가나 다"
    assert page_lines(0, edges)[0].text == "가"
    assert page_lines(0, [char(" ", 0, 0)]) == []


def test_runs_follow_boldness_and_size_is_the_commonest():
    chars = (
        word("ab", 0, 0, font="X+Serif-Bold", size=12)
        + word("cde", 30, 0, font="X+Serif-Regular")
        + word("f", 70, 0, font="X+Serif-Regular")
    )
    (line,) = page_lines(0, chars)
    assert [(r.text, r.bold) for r in line.runs] == [("ab", True), (" cde f", False)]
    assert line.size == 10.0 and line.text == "ab cde f" and not line.bold
    (bold,) = page_lines(0, word("ab", 0, 0, font="LibertinusSerif-Bold"))
    assert bold.bold


def test_is_bold():
    assert is_bold("ABCDEF+LibertinusSerif-Bold") and is_bold("Malgun-BOLD") and is_bold("x-SemiBold")
    assert not is_bold("NotoSansKR-Thin") and not is_bold("Times-Roman")


def test_skip_boxes_drop_chars_by_their_centre():
    chars = word("머리", 0, 0) + word("표칸", 0, 30) + word("끝", 0, 60)
    lines = page_lines(0, chars, skip=[Box(0, 25, 100, 45)])
    assert [ln.text for ln in lines] == ["머리", "끝"]
    # a box that only clips a char's edge leaves it in
    assert [ln.text for ln in page_lines(0, chars, skip=[Box(0, 38, 100, 45)])] == ["머리", "표칸", "끝"]


def test_rotated_chars_are_kept():
    side = [char(c, 200, 10 + i * 10, upright=False) for i, c in enumerate("세로글")]
    lines = page_lines(0, word("본문", 0, 12) + side)
    assert sorted("".join(ln.text for ln in lines).replace(" ", "")) == sorted("본문세로글")


def test_box_geometry():
    box = Box(10, 20, 40, 30)
    assert (box.width, box.height) == (30, 10)
    assert box.contains(10, 20) and box.contains(25, 25) and not box.contains(41, 25)


def test_builder_places_files_beside_the_source():
    data = typst_pdf('#image("img/a.png", width: 2cm)', files={"img/a.png": tiny_png()})
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        assert len(pdf.pages[0].images) == 1
