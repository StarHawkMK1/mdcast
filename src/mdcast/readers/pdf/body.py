"""The body of a PDF: its pages' text lines as blocks."""

from __future__ import annotations

import panflute as pf

from mdcast.readers.media import Assets
from mdcast.readers.pdf.lines import page_lines
from mdcast.readers.pdf.package import PdfPackage
from mdcast.report import Report


def read_body(pkg: PdfPackage, report: Report, assets: Assets) -> tuple[list[pf.Block], list[str]]:
    """The blocks of every page and the source text the coverage check compares with.

    For now each line is a paragraph of its own.
    """
    blocks: list[pf.Block] = []
    source_text: list[str] = []
    for number, page in enumerate(pkg.pdf.pages):
        for line in page_lines(number, page.chars):
            blocks.append(pf.Para(*_inlines(line.text)))
            source_text.append(line.text)
    return blocks, source_text


def _inlines(text: str) -> list[pf.Inline]:
    out: list[pf.Inline] = []
    for index, word in enumerate(text.split(" ")):
        if index:
            out.append(pf.Space())
        out.append(pf.Str(word))
    return out
