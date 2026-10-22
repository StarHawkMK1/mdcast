"""The body of a PDF: its pages' text lines grouped into paragraphs and headings."""

from __future__ import annotations

from collections.abc import Sequence

import panflute as pf

from mdcast.readers.media import Assets
from mdcast.readers.pdf.headings import heading_level, heading_sizes
from mdcast.readers.pdf.lines import page_lines
from mdcast.readers.pdf.model import Line
from mdcast.readers.pdf.package import PdfPackage
from mdcast.readers.pdf.paragraphs import group_paragraphs, measure_layout, to_inlines
from mdcast.report import Report


def read_body(pkg: PdfPackage, report: Report, assets: Assets) -> tuple[list[pf.Block], list[str]]:
    """The blocks of every page and the source text the coverage check compares with.

    The layout (body size, line gap, right edge) is measured once over the whole document, so a
    paragraph may run on from one page to the next.
    """
    pages: list[list[Line]] = [page_lines(number, page.chars) for number, page in enumerate(pkg.pdf.pages)]
    lines = [ln for page in pages for ln in page]
    layout = measure_layout(lines)
    blocks = body_blocks(group_paragraphs(lines, layout), layout.body_size)
    return blocks, [ln.text for ln in lines]


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
