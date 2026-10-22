"""The body of a PDF: each page's flow of text lines and tables, top to bottom, read into blocks."""

from __future__ import annotations

import functools
from collections.abc import Sequence
from dataclasses import dataclass

import panflute as pf
import pdfplumber

from mdcast.readers.media import Assets
from mdcast.readers.pdf.headings import heading_level, heading_sizes
from mdcast.readers.pdf.lines import Char, centre, page_lines
from mdcast.readers.pdf.model import Box, Line
from mdcast.readers.pdf.package import PdfPackage
from mdcast.readers.pdf.paragraphs import Layout, group_paragraphs, measure_layout, to_inlines
from mdcast.readers.pdf.tables import PageTable, build_table, find_tables
from mdcast.report import Report

Item = Line | PageTable  # what a page's flow holds


@dataclass
class Page:
    number: int  # from 0
    lines: list[Line]  # the text lines outside tables
    tables: list[PageTable]
    cells: dict[Box, list[Line]]  # every table cell's text lines, by the cell's box

    def flow(self) -> list[Item]:
        """Lines and tables in reading order: top to bottom, left to right at the same height."""
        return sorted([*self.lines, *self.tables], key=lambda item: (item.box.top, item.box.x0))


def read_page(number: int, page: pdfplumber.page.Page) -> Page:
    """A character is the text of the first table cell holding its centre, else a body character.

    Cells rather than table outlines decide, so a character inside a table's outline but in no
    cell stays body text instead of being lost.
    """
    tables = find_tables(page)
    cells: dict[Box, list[Char]] = {s.item: [] for t in tables for s in t.slots if s.item is not None}
    outside: list[Char] = []
    for c in page.chars:
        x, y = centre(c)
        cell = next(
            (
                s.item
                for t in tables
                if t.box.contains(x, y)
                for s in t.slots
                if s.item is not None and s.item.contains(x, y)
            ),
            None,
        )
        (outside if cell is None else cells[cell]).append(c)
    lines = page_lines(number, outside)
    return Page(number, lines, tables, {box: page_lines(number, chars) for box, chars in cells.items()})


def read_body(pkg: PdfPackage, report: Report, assets: Assets) -> tuple[list[pf.Block], list[str]]:
    """The blocks of every page and the source text the coverage check compares with.

    The layout (body size, line gap, right edge) is measured once over the lines outside tables of
    the whole document, so a paragraph may run on from one page to the next; a table ends the
    paragraph before it. Table cells are grouped with the same layout.
    """
    pages = [read_page(number, page) for number, page in enumerate(pkg.pdf.pages)]
    layout = measure_layout([ln for page in pages for ln in page.lines])
    flow: list[list[Line] | tuple[Page, PageTable]] = []  # body paragraphs and tables, in order
    source: list[str] = []
    run: list[Line] = []
    for page in pages:
        for item in page.flow():
            if isinstance(item, Line):
                run.append(item)
                source.append(item.text)
                continue
            flow += group_paragraphs(run, layout)
            run = []
            flow.append((page, item))
            source += [ln.text for s in item.slots if s.item is not None for ln in page.cells[s.item]]
    flow += group_paragraphs(run, layout)

    paragraphs = iter(body_blocks([p for p in flow if isinstance(p, list)], layout.body_size))
    blocks: list[pf.Block] = []
    for piece in flow:
        if isinstance(piece, list):
            blocks.append(next(paragraphs))
        else:
            page, table = piece
            blocks += build_table(table, functools.partial(cell_blocks, page, layout=layout))
    return blocks, source


def cell_blocks(page: Page, box: Box, layout: Layout) -> list[pf.Block]:
    """A table cell's paragraphs: one is Plain, several are Para (M3b D1). A cell holds no headings."""
    paragraphs = group_paragraphs(page.cells[box], layout)
    if len(paragraphs) == 1:
        return [pf.Plain(*to_inlines(paragraphs[0]))]
    return [pf.Para(*to_inlines(p)) for p in paragraphs]


def body_blocks(paragraphs: Sequence[Sequence[Line]], body_size: float) -> list[pf.Block]:
    """Paragraphs outside tables as Para or, when set large and short, Header.

    Heading sizes are ranked over these paragraphs only; table cells are never headings.
    """
    sizes = heading_sizes(paragraphs, body_size)
    return [_block(p, sizes, body_size) for p in paragraphs]


def _block(paragraph: Sequence[Line], sizes: dict[float, int], body_size: float) -> pf.Block:
    inlines = to_inlines(paragraph)
    level = heading_level(paragraph, sizes, body_size)
    if level is None:
        return pf.Para(*inlines)
    if len(inlines) == 1 and isinstance(inlines[0], pf.Strong):
        inlines = list(inlines[0].content)  # a heading need not also be bold (M3b §5.1)
    return pf.Header(*inlines, level=level)
