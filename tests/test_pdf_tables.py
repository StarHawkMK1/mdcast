from __future__ import annotations

import io
from dataclasses import dataclass

import panflute as pf
import pdfplumber
import pytest
from pdf_builder import typst_pdf

from mdcast.pipeline import convert
from mdcast.readers.grid import Slot
from mdcast.readers.md import read_md
from mdcast.readers.pdf import read_pdf
from mdcast.readers.pdf.body import read_page
from mdcast.readers.pdf.model import Box
from mdcast.readers.pdf.tables import PageTable, build_table
from mdcast.report import Report
from mdcast.types import Format, Source

# a paragraph wrapping over several lines, so the layout is measured on real body text
_BODY = "본문 글은 여러 줄에 걸쳐 이어지는 한 문단입니다. " * 8 + "끝."


@dataclass
class FakeTable:
    bbox: tuple[float, float, float, float]
    cells: list[tuple[float, float, float, float]]


@dataclass
class FakePage:
    chars: list[dict]
    tables: list[FakeTable]
    height: float = 842.0
    bbox: tuple[float, float, float, float] = (0, 0, 595, 842)
    images: tuple[dict, ...] = ()

    def find_tables(self) -> list[FakeTable]:
        return self.tables


def word(text: str, x0: float, top: float, size: float = 10.0) -> list[dict]:
    """pdfplumber-like chars, each as wide as it is tall."""
    return [{"text": c, "fontname": "Body-Regular", "size": size, "upright": True,
             "x0": x0 + i * size, "x1": x0 + (i + 1) * size, "top": top, "bottom": top + size}
            for i, c in enumerate(text)]


def pdf_source(data: bytes) -> Source:
    return Source(data, "a.pdf", Format.PDF)


def blocks(body: str) -> list[pf.Block]:
    return list(read_pdf(pdf_source(typst_pdf(body)), Report("a.pdf", Format.PDF), "a_assets").doc.content)


def tables(found: list[pf.Block]) -> list[pf.Table]:
    return [b for b in found if isinstance(b, pf.Table)]


def rows(table: pf.Table) -> list[pf.TableRow]:
    return [*table.head.content, *(r for body in table.content for r in body.content)]


def cell_texts(table: pf.Table) -> list[list[str]]:
    return [[pf.stringify(cell).strip() for cell in row.content] for row in rows(table)]


def spans(table: pf.Table) -> list[list[tuple[int, int]]]:
    return [[(cell.rowspan, cell.colspan) for cell in row.content] for row in rows(table)]


def texts(found: list[pf.Block]) -> list[str]:
    return [pf.stringify(b).strip() for b in found if not isinstance(b, pf.Table)]


def test_merged_cells_spans():
    found = blocks("#table(columns: 3, table.cell(colspan: 2)[a], [b], [c], [d], [e])")
    [table] = tables(found)
    assert cell_texts(table) == [["a", "b"], ["c", "d", "e"]]
    assert spans(table) == [[(1, 2), (1, 1)], [(1, 1), (1, 1), (1, 1)]]


def test_rowspan():
    found = blocks("#table(columns: 2, [h1], [h2], table.cell(rowspan: 2)[a], [b], [c])")
    [table] = tables(found)
    assert cell_texts(table) == [["h1", "h2"], ["a", "b"], ["c"]]
    assert spans(table) == [[(1, 1), (1, 1)], [(2, 1), (1, 1)], [(1, 1)]]


def test_first_row_is_head():
    [table] = tables(blocks("#table(columns: 2, [h1], [h2], [a], [b])"))
    assert [[pf.stringify(c).strip() for c in r.content] for r in table.head.content] == [["h1", "h2"]]
    assert len(table.content) == 1 and len(table.content[0].content) == 1
    assert pf.stringify(table.caption) == ""
    assert table.colspec == [("AlignDefault", "ColWidthDefault")] * 2


def test_table_text_not_in_body():
    found = blocks("위 문단 글입니다.\n\n#table(columns: 2, [칸가], [칸나], [칸다], [칸라])\n\n아래 문단 글입니다.")
    assert [type(b) for b in found] == [pf.Para, pf.Table, pf.Para]
    assert texts(found) == ["위 문단 글입니다.", "아래 문단 글입니다."]
    assert cell_texts(found[1]) == [["칸가", "칸나"], ["칸다", "칸라"]]


def test_cell_paragraphs():
    found = blocks(f"{_BODY}\n\n#table(columns: 2, [머리], [머리 둘], [첫 문단\n\n둘째 문단], [한 문단])")
    [table] = tables(found)
    two, one = table.content[0].content[0].content
    assert [type(b) for b in two.content] == [pf.Para, pf.Para]
    assert [pf.stringify(b).strip() for b in two.content] == ["첫 문단", "둘째 문단"]
    assert [type(b) for b in one.content] == [pf.Plain]


def test_wrapped_sentence_in_narrow_cell_is_one_paragraph():
    sentence = "이 칸의 글은 좁은 칸 안에서 여러 줄로 감겨 내려가는 한 문단입니다."
    data = typst_pdf(f"{_BODY}\n\n#table(columns: (4cm, 4cm), [머리], [둘], [{sentence}], [짧은 글])")
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page = read_page(0, pdf.pages[0])
    assert max(len(lines) for lines in page.cells.values()) > 2  # the sentence does wrap in its cell
    [table] = tables(list(read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").doc.content))
    cell = table.content[0].content[0].content[0]
    assert [type(b) for b in cell.content] == [pf.Plain]
    # Hangul may break inside a word, which joins with a space (spec §4.2, accepted loss)
    assert pf.stringify(cell).replace(" ", "").strip() == sentence.replace(" ", "")


def test_short_lines_in_wide_cell_stay_apart():
    found = blocks(f"{_BODY}\n\n#table(columns: (12cm, 2cm), [머리], [둘], [이름 \\ 주소], [값])")
    [table] = tables(found)
    cell = table.content[0].content[0].content[0]
    assert [type(b) for b in cell.content] == [pf.Para, pf.Para]
    assert [pf.stringify(b).strip() for b in cell.content] == ["이름", "주소"]


def test_char_in_table_outline_but_no_cell_stays_body_text():
    # an L-shaped table: its outline is 0..100 × 0..40 but no cell covers 50..100 × 20..40
    cells = [(0, 0, 50, 20), (50, 0, 100, 20), (0, 20, 50, 40)]
    chars = [*word("가", 10, 5), *word("나", 60, 5), *word("다", 10, 25), *word("밖", 70, 25)]
    page = read_page(0, FakePage(chars, [FakeTable((0, 0, 100, 40), cells)]))
    assert [ln.text for ln in page.lines] == ["밖"]
    assert sorted(ln.text for lines in page.cells.values() for ln in lines) == ["가", "나", "다"]


def test_cell_paragraphs_are_never_headings():
    found = blocks("#table(columns: 2, [#text(size: 20pt)[큰 글]], [b], [c], [d])\n\n" + _BODY)
    [table] = tables(found)
    assert [type(b) for b in table.head.content[0].content[0].content] == [pf.Plain]
    assert not [b for b in found if isinstance(b, pf.Header)]


def test_one_cell_box_unwraps():
    # pdfplumber does not report one-cell tables, so a ruled box's text stays body text in place
    found = blocks(f"{_BODY}\n\n#block(stroke: 1pt, inset: 6pt)[상자 안 글]")
    assert [type(b) for b in found] == [pf.Para, pf.Para]
    assert texts(found)[1] == "상자 안 글"


def test_one_cell_table_gives_its_blocks_as_paras():
    box = Box(0, 0, 100, 20)
    table = PageTable(box, [Slot(box, 0, 0)])
    out = build_table(table, lambda cell: [pf.Plain(pf.Str("상자"))])
    assert [type(b) for b in out] == [pf.Para]
    assert pf.stringify(out[0]).strip() == "상자"


def test_one_by_two_box_stays_table():
    [table] = tables(blocks("#table(columns: 2, [이름표], [긴 안내 글])"))
    assert cell_texts(table) == [["이름표", "긴 안내 글"]]


def test_borderless_table_is_text():
    data = typst_pdf("#table(stroke: none, columns: 2, [칸가], [칸나], [칸다], [칸라])")
    found = list(read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").doc.content)
    assert not tables(found)
    assert all(t in " ".join(texts(found)) for t in ["칸가", "칸나", "칸다", "칸라"])
    assert convert(pdf_source(data), [Format.MD]).report.coverage == 1.0


def test_cell_text_in_source_text():
    data = typst_pdf("위 글\n\n#table(columns: 2, [칸가], [칸나], [칸다], [칸라])\n\n아래 글")
    source = read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").source_text
    assert source == ["위 글", "칸가", "칸나", "칸다", "칸라", "아래 글"]


def test_merged_table_reads_back_from_md():
    result = convert(pdf_source(typst_pdf("#table(columns: 3, table.cell(colspan: 2)[a], [b], [c], [d], [e])")),
                     [Format.MD])
    assert result.report.coverage == 1.0
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc
    [table] = tables(list(back.content))
    assert cell_texts(table) == [["a", "b"], ["c", "d", "e"]]
    assert spans(table) == [[(1, 2), (1, 1)], [(1, 1), (1, 1), (1, 1)]]
    assert len(table.head.content) == 1


@pytest.mark.parametrize("inset", ["", "inset: (left: 0pt, rest: 5pt), "], ids=["inset", "flush-left"])
def test_nested_table_is_text_of_the_outer_cell(inset):
    # pdfplumber reports a table drawn inside a cell as a table of its own beside the outer one
    data = typst_pdf(f"#table(columns: 2, {inset}[바깥 가], [바깥 나], "
                     "[#table(columns: 2, [안 가], [안 나])], [바깥 라])")
    found = list(read_pdf(pdf_source(data), Report("a.pdf", Format.PDF), "a_assets").doc.content)
    [table] = tables(found)
    assert cell_texts(table) == [["바깥 가", "바깥 나"], ["안 가 안 나", "바깥 라"]]
    assert convert(pdf_source(data), [Format.MD]).report.coverage == 1.0
