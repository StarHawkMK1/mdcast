"""The body of a PDF: each page's flow of text lines, tables and pictures, top to bottom, read into blocks."""

from __future__ import annotations

import dataclasses
import functools
import heapq
from collections import defaultdict
from collections.abc import Sequence

import panflute as pf
import pdfplumber

from mdcast.readers.media import Assets
from mdcast.readers.pdf.headings import heading_level, heading_sizes
from mdcast.readers.pdf.images import image_boxes, is_small, render
from mdcast.readers.pdf.lines import Char, centre, page_lines
from mdcast.readers.pdf.model import Box, Line
from mdcast.readers.pdf.package import PdfPackage
from mdcast.readers.pdf.paragraphs import Layout, group_paragraphs, measure_layout, to_inlines
from mdcast.readers.pdf.repeats import (
    BandKey,
    band_key,
    digitless,
    isolated,
    repeated,
    skipped_message,
)
from mdcast.readers.pdf.tables import PageTable, build_table, find_tables
from mdcast.report import Codes, Report


@dataclasses.dataclass(frozen=True)
class Picture:
    box: Box  # cut down to the page


Item = Line | PageTable | Picture  # what a page's flow holds


@dataclasses.dataclass
class Page:
    number: int  # from 0
    height: float
    lines: list[Line]  # the text lines outside tables
    tables: list[PageTable]
    cells: dict[Box, list[Line]]  # every table cell's text lines, by the cell's box
    pictures: list[Picture] = dataclasses.field(default_factory=list)  # outside table cells
    cell_pictures: dict[Box, list[Picture]] = dataclasses.field(default_factory=dict)
    small: int = 0  # pictures dropped as decoration

    def flow(self) -> list[Item]:
        """Lines, tables and pictures in reading order: top to bottom, left to right at the same height."""
        items = [*self.lines, *self.tables, *self.pictures]
        return sorted(items, key=lambda item: (item.box.top, item.box.x0))


def read_page(number: int, page: pdfplumber.page.Page) -> Page:
    """A character or picture is in the first table cell holding its centre, else in the body.

    Cells rather than table outlines decide, so a character inside a table's outline but in no
    cell stays body text instead of being lost. A picture smaller than ``SMALL_PT`` both ways is
    decoration: counted, not kept.
    """
    tables = find_tables(page)

    def cell_at(x: float, y: float) -> Box | None:
        return next(
            (
                s.item
                for t in tables
                if t.box.contains(x, y)
                for s in t.slots
                if s.item is not None and s.item.contains(x, y)
            ),
            None,
        )

    cells: dict[Box, list[Char]] = {s.item: [] for t in tables for s in t.slots if s.item is not None}
    outside: list[Char] = []
    for c in page.chars:
        cell = cell_at(*centre(c))
        (outside if cell is None else cells[cell]).append(c)
    lines = page_lines(number, outside)
    cell_lines = {box: page_lines(number, chars) for box, chars in cells.items()}

    boxes = image_boxes(page)
    pictures: list[Picture] = []
    cell_pictures: dict[Box, list[Picture]] = defaultdict(list)
    for box in boxes:
        if not is_small(box):
            cell = cell_at((box.x0 + box.x1) / 2, (box.top + box.bottom) / 2)
            (pictures if cell is None else cell_pictures[cell]).append(Picture(box))
    small = sum(is_small(box) for box in boxes)
    return Page(number, page.height, lines, tables, cell_lines, pictures, dict(cell_pictures), small)


class Drawings:
    """The pictures kept, drawn into the assets as ``image1.png``, ``image2.png``… in the order the
    MD shows them. The same drawing twice (a logo on two pages) is one file.
    """

    def __init__(self, pdf_pages: Sequence[pdfplumber.page.Page], report: Report, assets: Assets) -> None:
        self.pdf_pages = pdf_pages
        self.report = report
        self.assets = assets
        self.paths: dict[bytes, str] = {}  # PNG → its MD path

    def image(self, page: Page, picture: Picture) -> pf.Image | None:
        """The picture as ``pf.Image``, or None (warn ``IMPORT_OBJECT_SKIPPED``) when it cannot be drawn."""
        try:
            png = render(self.pdf_pages[page.number], picture.box)
        except Exception as exc:  # noqa: BLE001 - one undrawable picture is skipped, never a failure
            self.report.warn(
                Codes.IMPORT_OBJECT_SKIPPED, f"그림을 PNG로 그리지 못해 건너뜁니다: {exc}", page=page.number + 1
            )
            return None
        if png not in self.paths:
            self.paths[png] = self.assets.add(f"image{len(self.paths) + 1}.png", png)
        return pf.Image(pf.Str("그림"), url=self.paths[png])


def read_body(pkg: PdfPackage, report: Report, assets: Assets) -> tuple[list[pf.Block], list[str]]:
    """The blocks of every page and the source text the coverage check compares with.

    Running headers and footers are dropped first, so they are neither body text nor source text.
    The layout (body size, line gap, right edge) is measured once over the lines outside tables of
    the whole document, so a paragraph may run on from one page to the next; a table or a picture
    ends the paragraph before it. Table cells are grouped with the same layout.
    """
    pages = [read_page(number, page) for number, page in enumerate(pkg.pdf.pages)]
    if small := sum(page.small for page in pages):
        report.info(Codes.IMPORT_OBJECT_SKIPPED, f"장식으로 보이는 작은 그림 {small}개를 가져오지 않습니다")
    drop_repeats(pages, report)
    layout = measure_layout([ln for page in pages for ln in page.lines])
    flow: list[list[Line] | tuple[Page, PageTable | Picture]] = []  # paragraphs, tables, pictures
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
            if isinstance(item, PageTable):
                source += [ln.text for s in item.slots if s.item is not None for ln in page.cells[s.item]]
    flow += group_paragraphs(run, layout)

    drawings = Drawings(pkg.pdf.pages, report, assets)
    paragraphs = iter(body_blocks([p for p in flow if isinstance(p, list)], layout.body_size))
    blocks: list[pf.Block] = []
    for piece in flow:
        if isinstance(piece, list):
            blocks.append(next(paragraphs))
            continue
        page, item = piece
        if isinstance(item, PageTable):
            blocks += build_table(item, functools.partial(cell_blocks, page, layout=layout, drawings=drawings))
        elif (image := drawings.image(page, item)) is not None:
            blocks.append(pf.Para(image))
    return blocks, source


def drop_repeats(pages: Sequence[Page], report: Report) -> None:
    """Take the lines and pictures outside tables that repeat in a page's top or bottom band out of
    the pages.

    Each page's band is measured with its own height; table cells are never dropped. A repeated
    picture (a logo) goes on repetition alone, as does a repeat whose lines all say the same. One
    whose lines differ in their digits (page numbers, but also "제1장", "제2장" opening each page)
    goes only where a line stands apart from the page's body: no other line, table or picture
    within ``GAP`` of it. Pictures repeat apart from lines: a picture keys with no text, as a bare
    page number does, yet the two never make one repeat.
    """
    picture_keys = [[band_key(p.box, page.height) or frozenset() for p in page.pictures] for page in pages]
    drop_pictures = repeated([set().union(*page_keys) for page_keys in picture_keys])
    pictures = 0
    for page, page_keys in zip(pages, picture_keys, strict=True):
        kept_pictures = [p for p, k in zip(page.pictures, page_keys, strict=True) if not k & drop_pictures]
        pictures += len(page.pictures) - len(kept_pictures)
        page.pictures = kept_pictures

    keys = [
        [band_key(ln.box, page.height, ln.text) or frozenset() for ln in page.lines] for page in pages
    ]
    drop = repeated([set().union(*page_keys) for page_keys in keys])
    texts: dict[BandKey, set[str]] = defaultdict(set)  # what the lines of each repeat say
    for page, page_keys in zip(pages, keys, strict=True):
        for line, line_keys in zip(page.lines, page_keys, strict=True):
            for key in line_keys & drop:
                texts[key].add(line.text)
    examples: dict[str, str] = {}  # the first line dropped for each text without digits
    dropped = 0
    for page, page_keys in zip(pages, keys, strict=True):
        body = [ln.box for ln, k in zip(page.lines, page_keys, strict=True) if not k & drop]
        body += [table.box for table in page.tables] + [p.box for p in page.pictures]
        kept = []
        for line, line_keys in zip(page.lines, page_keys, strict=True):
            hits = line_keys & drop
            same = any(len(texts[key]) == 1 for key in hits)
            if hits and (same or isolated(line.box, line.size, body)):
                examples.setdefault(digitless(line.text), line.text)
                dropped += 1
            else:
                kept.append(line)
        page.lines = kept
    if dropped or pictures:
        report.info(Codes.IMPORT_HEADER_SKIPPED, skipped_message(dropped, list(examples.values()), pictures))


def cell_blocks(page: Page, box: Box, layout: Layout, drawings: Drawings) -> list[pf.Block]:
    """A table cell's paragraphs and pictures: one is Plain, several are Para (M3b D1). A cell holds
    no headings.

    The document's body size and line gap apply, but a line ends short against the cell's own right
    edge, so a sentence wrapping in a narrow cell stays one paragraph. A picture ends the paragraph
    before it.
    """
    cell_layout = dataclasses.replace(layout, right=box.x1)
    pieces: list[list[pf.Inline]] = []
    run: list[Line] = []
    items = heapq.merge(page.cells[box], page.cell_pictures.get(box, []), key=lambda i: (i.box.top, i.box.x0))
    for item in items:
        if isinstance(item, Line):
            run.append(item)
            continue
        pieces += [to_inlines(p) for p in group_paragraphs(run, cell_layout)]
        run = []
        if (image := drawings.image(page, item)) is not None:
            pieces.append([image])
    pieces += [to_inlines(p) for p in group_paragraphs(run, cell_layout)]
    if len(pieces) == 1:
        return [pf.Plain(*pieces[0])]
    return [pf.Para(*p) for p in pieces]


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
