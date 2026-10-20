"""Hancom Office checks (spec §8.3): run with --run-hangul on Windows with Hangul installed.

Without the security module registered (README), Hangul asks to allow file access on each run.
"""

import re
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from helpers import char_origin, line_pitch, line_starts

from mdcast import pipeline
from mdcast.types import Format, Options, Source

pytestmark = pytest.mark.hangul
FIXTURES = Path(__file__).parent / "fixtures" / "md"
LONG = "줄 간격을 보기 위해 충분히 긴 문장을 씁니다. " * 6


@pytest.fixture(scope="module")
def hangul():
    win32 = pytest.importorskip("win32com.client")
    try:
        hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    except Exception as exc:  # noqa: BLE001 - COM errors are pywintypes.com_error
        pytest.skip(f"한글을 실행할 수 없습니다: {exc}")
    hwp.XHwpWindows.Item(0).Visible = True
    if not hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule"):
        print("한글 보안 모듈이 등록되지 않아 '접근 허용' 대화상자가 뜹니다 (README 참고)")
    yield hwp
    hwp.Clear(1)
    hwp.Quit()


def convert(tmp_path: Path, md: str, name: str = "doc", base_dir: Path | None = None) -> tuple[Path, bytes]:
    source = Source(md.encode("utf-8"), f"{name}.md", Format.MD, base_dir=base_dir or tmp_path)
    result = pipeline.convert(source, [Format.HWPX, Format.PDF],
                              options=Options(offline=True, cwd=tmp_path, home=tmp_path / "home"))
    outputs = {o.format: o.data for o in result.outputs}
    path = tmp_path / f"{name}.hwpx"
    path.write_bytes(outputs[Format.HWPX])
    return path, outputs[Format.PDF]


def through_hangul(hwp, path: Path) -> tuple[str, bytes]:
    assert hwp.Open(str(path.resolve()), "HWPX", ""), f"한글이 {path.name} 을(를) 열지 못했습니다"
    text = hwp.GetTextFile("UNICODE", "")
    pdf = path.with_suffix(".hangul.pdf")
    assert hwp.SaveAs(str(pdf.resolve()), "PDF", "")
    hwp.Clear(1)
    return text, pdf.read_bytes()


@pytest.mark.parametrize("name", ["kitchen-sink", "edge-cases", "korean-report", "tables-images"])
def test_hangul_opens_fixture(hangul, tmp_path, name):
    md = (FIXTURES / f"{name}.md").read_text(encoding="utf-8")
    path, _ = convert(tmp_path, md, name, base_dir=FIXTURES)
    text, pdf = through_hangul(hangul, path)
    body = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.DOTALL)  # front matter is not body text
    words = re.findall(r"[가-힣]{2,}", body)
    assert text.strip() and words and words[0] in text
    assert pdf.startswith(b"%PDF")


def test_line_pitch_matches_the_pdf(hangul, tmp_path):
    md = f"# 제목{LONG}\n\n본문{LONG}\n\n- 목록{LONG}\n\n```\n코드 첫째 줄\n코드 둘째 줄\n```\n"
    path, mdcast_pdf = convert(tmp_path, md)
    _, hangul_pdf = through_hangul(hangul, path)
    # code: 12.24pt in a two-line block against 12.35 (12.36 in a three-line one), spec appendix A-18
    for needle, rel in (("제목", 0.005), ("본문", 0.005), ("목록", 0.005), ("코드 첫째", 0.01)):
        assert line_pitch(hangul_pdf, needle) == pytest.approx(line_pitch(mdcast_pdf, needle), rel=rel), needle


def test_text_columns(hangul, tmp_path):
    md = f"# 제목\n\n본문 문단\n\n- 목록{LONG}\n"
    path, mdcast_pdf = convert(tmp_path, md)
    _, hangul_pdf = through_hangul(hangul, path)
    for needle in ("제목", "본문"):
        assert char_origin(hangul_pdf, needle)[0] == pytest.approx(char_origin(mdcast_pdf, needle)[0], abs=0.5)
    first_text = char_origin(hangul_pdf, "목록")[0]
    wrapped = line_starts(hangul_pdf, "목록")[1][0]
    assert first_text == pytest.approx(wrapped, abs=0.5)


def test_header_footer_and_first_line_positions(hangul, tmp_path):
    md = "---\ntitle: 머리말제목\n---\n\n본문첫줄\n"
    path, mdcast_pdf = convert(tmp_path, md)
    _, hangul_pdf = through_hangul(hangul, path)
    header = char_origin(hangul_pdf, "머리말제목")[1]
    assert header == pytest.approx(char_origin(mdcast_pdf, "머리말제목")[1], abs=1.0)
    assert char_origin(hangul_pdf, "/")[1] == pytest.approx(char_origin(mdcast_pdf, "/")[1], abs=1.0)
    # known difference (spec §6.1): Hangul puts a line's extra height below the text
    expected = -((1.8 - 1) / 2 - 0.05) * 11 * 25.4 / 72
    shift = char_origin(hangul_pdf, "본문첫줄")[1] - char_origin(mdcast_pdf, "본문첫줄")[1]
    assert shift == pytest.approx(expected, abs=0.5)


def top_controls(hwp) -> list[str]:
    ids, ctrl = [], hwp.HeadCtrl
    while ctrl is not None:
        ids.append(ctrl.CtrlID)
        ctrl = ctrl.Next
    return ids


def test_tables_pictures_footnotes_open_as_objects(hangul, tmp_path):
    md = (FIXTURES / "tables-images.md").read_text(encoding="utf-8")
    path, _ = convert(tmp_path, md, "tables-images", base_dir=FIXTURES)
    assert hangul.Open(str(path.resolve()), "HWPX", "")
    ids = top_controls(hangul)
    text = hangul.GetTextFile("UNICODE", "")
    pages = hangul.PageCount
    hangul.Clear(1)
    # Hangul lists every control, those inside table cells too
    assert ids.count("tbl") == 4
    assert ids.count("gso") == 5  # inline icon, wide figure, 40% figure, two cell pictures
    assert ids.count("fn") == 3  # two body notes and the cell note
    for needle in ("성능 기준", "로그인 화면", "첫 각주 내용", "칸 안 각주", "항목 60"):
        assert needle in text
    assert pages >= 2


def test_long_table_splits_across_pages(hangul, tmp_path):
    """The last row must be laid out, not cut at the page bottom (a table treated as a character never splits)."""
    rows = "".join(f"| {n} | 항목 {n} |\n" for n in range(1, 81))
    path, _ = convert(tmp_path, f"# 긴 표\n\n앞 문단\n\n| 번호 | 항목 |\n|---|---|\n{rows}\n뒤 문단\n")
    _, pdf = through_hangul(hangul, path)
    document = pdfium.PdfDocument(pdf)
    pages = [document[i].get_textpage().get_text_range() for i in range(len(document))]
    assert len(pages) >= 2
    assert "항목 80" in pages[-1] and "뒤 문단" in pages[-1]
    assert "번호" in pages[-1]  # the header row repeats on the next page
