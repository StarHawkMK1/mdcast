from __future__ import annotations

import io

from pdf_builder import typst_pdf
from PIL import Image

from mdcast.pipeline import convert
from mdcast.readers.pdf.checks import MIN_SIDE_LINES, VECTOR_CURVES, multicolumn, vector_heavy
from mdcast.readers.pdf.model import Box, Line, Run
from mdcast.report import Codes, Level
from mdcast.types import Format, Source

MULTICOLUMN = "여러 단으로 짠 쪽이 있어 읽기 순서가 섞였을 수 있습니다. 순서가 중요하면 다른 도구로 바꾸는 편이 낫습니다"
SCANNED = "글자 없이 그림만 있는 쪽이 있습니다(스캔본으로 보임). 글자 인식(OCR)은 하지 않습니다"
ALL_SCANNED = "모든 쪽이 그림뿐입니다(스캔본으로 보임). 글자 인식(OCR)은 하지 않습니다"
VECTOR = "선과 도형으로 그린 그림이 있어 보입니다. 그림으로 가져오지 못하고 그 안의 글자만 옮깁니다"

_BODY = "본문 글은 여러 줄에 걸쳐 이어지는 한 문단입니다. " * 8 + "끝."


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (200, 280), (200, 30, 30)).save(out, format="PNG")
    return out.getvalue()


def converted(body: str, *, page: str = 'paper: "a4"'):
    data = typst_pdf(body, page=page, files={"a.png": png()})
    return convert(Source(data, "x.pdf", Format.PDF), [Format.MD])


def warnings(result, code: str) -> list:
    return [e for e in result.report.events if e.code == code and e.level is Level.WARN]


def test_two_columns_warned():
    result = converted("#lorem(600)", page='paper: "a4", columns: 2')
    [event] = warnings(result, Codes.PDF_MULTICOLUMN_SUSPECTED)
    assert event.message == MULTICOLUMN
    assert event.where == {"pages": [1]}
    assert result.outputs[0].data is not None


def test_one_column_not_warned():
    result = converted("#lorem(600)")
    assert not warnings(result, Codes.PDF_MULTICOLUMN_SUSPECTED)


def test_landscape_two_columns():
    """Review Focus 2: each page is judged with its own width. An A3 landscape page's gutter lies
    outside the middle of an A4 portrait page, so judging it with page 1's width would miss it."""
    body = '#lorem(300)\n#set page(paper: "a3", flipped: true, columns: 2)\n#lorem(1000)'
    result = converted(body)
    [event] = warnings(result, Codes.PDF_MULTICOLUMN_SUSPECTED)
    assert event.where == {"pages": [2]}


def test_scanned_page_warned():
    body = '#image("a.png", width: 100%, height: 100%)\n#pagebreak()\n' + _BODY
    result = converted(body, page='paper: "a4", margin: 0pt')
    [event] = warnings(result, Codes.PDF_SCANNED_SUSPECTED)
    assert event.message == SCANNED
    assert event.where == {"pages": [1]}
    out = result.outputs[0]
    assert list(out.assets) == ["x_assets/image1.png"]
    assert "![그림](x_assets/image1.png)" in out.data.decode("utf-8")


def test_all_pages_scanned_message():
    body = "\n#pagebreak()\n".join(['#image("a.png", width: 100%, height: 100%)'] * 3)
    result = converted(body, page='paper: "a4", margin: 0pt')
    [event] = warnings(result, Codes.PDF_SCANNED_SUSPECTED)
    assert event.message == ALL_SCANNED and "모든 쪽" in event.message
    assert event.where == {"pages": [1, 2, 3]}


def test_vector_drawing_warned():
    curve = "#curve(curve.move((0pt, 0pt)), curve.cubic(none, (20pt, 40pt), (40pt, 0pt)))"
    shapes = "\n".join(["#circle(radius: 5pt)"] * 6 + [curve] * 6)
    result = converted(f"{_BODY}\n\n{shapes}\n#pagebreak()\n{_BODY}")
    [event] = warnings(result, Codes.IMPORT_OBJECT_SKIPPED)
    assert event.message == VECTOR
    assert event.where == {"pages": [1]}


def test_table_borders_not_vector():
    cells = ", ".join(f"[칸 {i}]" for i in range(120))
    result = converted(f"#table(columns: 6, stroke: 1pt, {cells})")
    assert not warnings(result, Codes.IMPORT_OBJECT_SKIPPED)


def test_curves_inside_tables_not_counted():
    """A border drawn as curves may poke a little past the table's box; it is still the table's."""
    table = Box(100, 100, 300, 300)
    border = [{"x0": 99.5, "top": 99.5, "x1": 300.5, "bottom": 140.0}] * 2 * VECTOR_CURVES
    drawing = {"x0": 400, "top": 100, "x1": 420, "bottom": 120}
    assert not vector_heavy(border, [table])
    assert not vector_heavy([*border, *[drawing] * (VECTOR_CURVES - 1)], [table])
    assert vector_heavy([*border, *[drawing] * VECTOR_CURVES], [table])


def test_lines_off_to_the_right_are_not_a_column():
    """Short lines down the left and, at other heights, a display formula and a page number off to
    the right (as in mdcast's own PDF of kitchen-sink.md): no line stands beside another."""

    def line(x0: float, x1: float, top: float) -> Line:
        return Line(0, Box(x0, top, x1, top + 10), 10.0, [Run("x", False)])

    left = [line(57, 150, 60 + 20 * i) for i in range(20)]
    apart = [line(270, 330, 500 + 20 * i) for i in range(MIN_SIDE_LINES)]
    beside = [line(320, 520, 60 + 20 * i) for i in range(MIN_SIDE_LINES)]
    assert not multicolumn(left + apart, 595)
    assert multicolumn(left + beside, 595)
