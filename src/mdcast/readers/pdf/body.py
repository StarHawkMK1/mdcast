"""The body of a PDF: its pages' text lines grouped into paragraphs."""

from __future__ import annotations

import panflute as pf

from mdcast.readers.media import Assets
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
    blocks: list[pf.Block] = [pf.Para(*to_inlines(p)) for p in group_paragraphs(lines, layout)]
    return blocks, [ln.text for ln in lines]
