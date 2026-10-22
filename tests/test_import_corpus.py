"""Real-document import checks, local only (M3a §9, M3b §9, M3c §7).

The corpus holds personal data: assert numbers only and never print, save or snapshot its text.
Every count is computed into plain ints first so a failure message shows numbers, not content.
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import re
import sys
import tempfile
import warnings
import zipfile
from collections.abc import Iterator
from pathlib import Path

import panflute as pf
import pytest
from lxml import etree

from mdcast.ast import docx_to_doc
from mdcast.pipeline import convert
from mdcast.readers.hwpx import read_hwpx
from mdcast.readers.md import read_md
from mdcast.report import Codes, Level, Report
from mdcast.types import Format, Options, Source

pytestmark = pytest.mark.corpus

_TOP = re.compile(r"^\d+\. ")
_SUB = re.compile(r"^\d+\.\d+")


def _find(pattern: str) -> Path:
    root = os.environ.get("MDCAST_CORPUS_DIR")
    if not root:
        pytest.skip("MDCAST_CORPUS_DIR not set")
    found = sorted(Path(root).glob(pattern))
    if not found:
        pytest.skip(f"no {pattern} in MDCAST_CORPUS_DIR")
    return found[0]


def _corpus_file() -> Path:
    return _find("*시험합의서*.docx")


def _all(doc: pf.Doc, cls: type) -> list:
    found: list = []
    doc.walk(lambda e, _d: found.append(e) if isinstance(e, cls) else None)
    return found


def _spans(doc: pf.Doc) -> tuple[int, int]:
    cells = _all(doc, pf.TableCell)
    return sum(c.rowspan > 1 for c in cells), sum(c.colspan > 1 for c in cells)


def _dims(table: pf.Table) -> tuple[int, int]:
    rows = len(table.head.content) if table.head else 0
    rows += sum(len(body.head) + len(body.content) for body in table.content)
    return rows, len(table.colspec)


def _heading_counts(doc: pf.Doc) -> dict[str, int]:
    heads = [(h.level, pf.stringify(h).strip()) for h in _all(doc, pf.Header)]
    tops = [i for i, (_, text) in enumerate(heads) if _TOP.match(text)]
    top_levels = sorted({heads[i][0] for i in tops})
    sub_levels = sorted({level for level, text in heads if _SUB.match(text)})
    before = [level for level, _ in heads[: tops[0]]] if tops else []
    return {
        "top": len(tops),
        "top_level_kinds": len(top_levels),
        "sub": sum(1 for _, text in heads if _SUB.match(text)),
        "sub_one_below_top": int(len(top_levels) == 1 and sub_levels == [top_levels[0] + 1]),
        "before_top": len(before),
        "before_top_level1": int(before == [1]),
    }


def _measure(data: bytes) -> dict[str, int]:
    result = convert(Source(data, "x.docx", Format.DOCX), [Format.MD])
    out = result.outputs[0]
    events = result.report.events
    md = out.data
    back = read_md(Source(md, "x.md", Format.MD), Report("x.md", Format.MD)).doc
    original = docx_to_doc(data)
    rows_in, cols_in = _spans(original)
    rows_out, cols_out = _spans(back)
    counts = {
        "tables": len(_all(back, pf.Table)),
        "rowspan_diff": rows_out - rows_in,
        "colspan_diff": cols_out - cols_in,
        "notes": len(_all(back, pf.Note)),
        "png_assets": sum(1 for name in out.assets if name.lower().endswith(".png")),
        "convert_failed": sum(1 for e in events if e.code == Codes.IMAGE_CONVERT_FAILED),
        "image_text": sum(1 for e in events if e.code == Codes.IMPORT_IMAGE_TEXT),
        "text_missing": sum(1 for e in events if e.code == Codes.IMPORT_TEXT_MISSING),
        "coverage_permille": round((result.report.coverage or 0) * 1000),
        "unwrapped": sum(1 for e in events if e.code == Codes.IMPORT_TABLE_UNWRAPPED),
        "tables_11x2": sum(1 for t in _all(back, pf.Table) if _dims(t) == (11, 2)),
        **_heading_counts(back),
    }
    counts["reexport_ok"], counts["reexport_errors"] = _reexport(md, out.assets, Format.DOCX)
    return counts


def _reexport(md: bytes, assets: dict[str, bytes], target: Format) -> tuple[int, int]:
    """(1 if the MD exported to ``target``, number of error events)."""
    with tempfile.TemporaryDirectory() as tmp:  # the pictures may hold form text: never keep them
        base = Path(tmp)
        for name, blob in assets.items():
            (base / name).parent.mkdir(parents=True, exist_ok=True)
            (base / name).write_bytes(blob)
        again = convert(
            Source(md, "x.md", Format.MD, base_dir=base),
            [target],
            options=Options(offline=True, cwd=base, home=base / "home"),
        )
        return int(again.outputs[0].data is not None), sum(1 for e in again.report.events if e.level is Level.ERROR)


@contextlib.contextmanager
def _quiet() -> Iterator[None]:
    """No log record or warning while the corpus is processed.

    pypandoc sends pandoc's stderr to its logger (a stderr handler, propagating to pytest's log
    capture), and pandoc warnings can quote source text ("Could not convert TeX math …").
    """
    pandoc_log = logging.getLogger("pypandoc")
    was_disabled, was_level = pandoc_log.disabled, logging.root.manager.disable
    pandoc_log.disabled = True
    logging.disable(logging.CRITICAL)  # any other logger on the path (Pillow, …)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            yield
    finally:
        logging.disable(was_level)
        pandoc_log.disabled = was_disabled


def test_corpus_document_numbers():
    data = _corpus_file().read_bytes()
    try:
        with _quiet():
            counts = _measure(data)
    except Exception as exc:  # noqa: BLE001 - keep document text out of the failure message
        raise AssertionError(f"corpus import raised {type(exc).__name__}") from None
    windows = sys.platform == "win32"
    # body pictures: 10 placements of 8 distinct WMF files (the package's 9th picture is the header's PNG,
    # which is not imported); one PNG per file, one IMPORT_IMAGE_TEXT per placement
    expected = {
        "tables": 9,
        "rowspan_diff": 0,
        "colspan_diff": 0,
        "png_assets": 8 if windows else 0,  # without a WMF renderer the files stay WMF
        "convert_failed": 0 if windows else 8,
        "image_text": 10,
        "text_missing": 0,
        "coverage_permille": 1000,
        # the 2×11 table (11 rows, 2 columns) is not a label | content form: it stays a table (D18)
        "unwrapped": 0,
        "tables_11x2": 1,
        "top": 14,
        "top_level_kinds": 1,
        "sub_one_below_top": 1,
        "before_top": 1,
        "before_top_level1": 1,
        "reexport_ok": 1,
        "reexport_errors": 0,
    }
    assert {k: counts[k] for k in expected} == expected
    assert counts["notes"] >= 1
    assert counts["sub"] >= 1


# --- hwpx (M3b §9) -------------------------------------------------------------------------------

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_SECTION = re.compile(r"Contents/section\d+\.xml")
_NUMBER = re.compile(r"\d+")


def _source_tables(data: bytes) -> dict[str, int]:
    """``hp:tbl`` and merged ``hp:cellSpan`` counts (cells, and the span sizes summed) of the package."""
    counts = dict.fromkeys(("src_tables", "src_rowspan", "src_colspan", "src_rowspan_sum", "src_colspan_sum"), 0)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            if not _SECTION.fullmatch(name):
                continue
            root = etree.fromstring(archive.read(name))
            counts["src_tables"] += sum(1 for _ in root.iter(f"{_HP}tbl"))
            for span in root.iter(f"{_HP}cellSpan"):
                rows, cols = int(span.get("rowSpan", "1")), int(span.get("colSpan", "1"))
                counts["src_rowspan"] += rows > 1
                counts["src_colspan"] += cols > 1
                counts["src_rowspan_sum"] += rows if rows > 1 else 0
                counts["src_colspan_sum"] += cols if cols > 1 else 0
    return counts


def _in_cell(elem: pf.Element) -> bool:
    return any(isinstance(a, pf.TableCell) for a in _ancestors(elem))


def _ancestors(elem: pf.Element) -> Iterator[pf.Element]:
    while elem.parent is not None:
        elem = elem.parent
        yield elem


def _starting(texts: list[str], mark: str) -> int:
    return sum(1 for t in texts if t.lstrip().startswith(mark))


def _event_number(events: list, code: str) -> int:
    """The count an info event states in its own (mdcast) wording, e.g. 「… 16개를 …」; 0 without the event."""
    found = [int(n) for e in events if e.code == code for n in _NUMBER.findall(e.message)[:1]]
    return sum(found)


def _hwpx_measure(data: bytes) -> dict[str, int]:
    source = Source(data, "x.hwpx", Format.HWPX)
    result = convert(source, [Format.MD])
    out, events = result.outputs[0], result.report.events
    md = out.data
    back = read_md(Source(md, "x.md", Format.MD), Report("x.md", Format.MD)).doc
    read = read_hwpx(source, Report("x.hwpx", Format.HWPX), "x_assets")
    cells = _all(back, pf.TableCell)
    images = _all(back, pf.Image)
    bullets = [item for lst in _all(back, pf.BulletList) if _in_cell(lst) for item in lst.content]
    loose = [pf.stringify(b) for b in _all(back, (pf.Para, pf.Plain)) if not isinstance(b.parent, pf.ListItem)]
    counts = {
        "coverage_permille": round((result.report.coverage or 0) * 1000),
        "errors": sum(1 for e in events if e.level is Level.ERROR),
        "text_missing": sum(1 for e in events if e.code == Codes.IMPORT_TEXT_MISSING),
        "unwrapped": sum(1 for e in events if e.code == Codes.IMPORT_TABLE_UNWRAPPED),
        "symbol_events": sum(1 for e in events if e.code == Codes.IMPORT_SYMBOL_MAPPED),
        "symbols_mapped": _event_number(events, Codes.IMPORT_SYMBOL_MAPPED),
        "lists_inferred": _event_number(events, Codes.IMPORT_LIST_INFERRED),
        "top_headers": sum(1 for b in back.content if isinstance(b, pf.Header)),
        "headers": len(_all(back, pf.Header)),
        "top_tables": sum(1 for b in back.content if isinstance(b, pf.Table)),
        "tables": len(_all(back, pf.Table)),
        "tables_11x3": sum(1 for t in _all(back, pf.Table) if _dims(t) == (11, 3)),
        "rowspan": sum(c.rowspan > 1 for c in cells),
        "colspan": sum(c.colspan > 1 for c in cells),
        "rowspan_sum": sum(c.rowspan for c in cells if c.rowspan > 1),
        "colspan_sum": sum(c.colspan for c in cells if c.colspan > 1),
        "images": len(images),
        "alt_not_default": sum(1 for i in images if pf.stringify(i) != "그림"),
        "definition_lists": len(_all(back, pf.DefinitionList)),
        "native_list_items": len(_all(read.doc, pf.ListItem)),
        "list_items": len(_all(back, pf.ListItem)),
        "cell_bullet_items": len(bullets),
        "source_square": _starting(read.source_text, "▪"),
        "source_dash": _starting(read.source_text, "-"),
        "left_square": _starting(loose, "▪"),
        "left_dash": _starting(loose, "-"),
        **_source_tables(data),
    }
    counts["docx_ok"], counts["docx_errors"] = _reexport(md, out.assets, Format.DOCX)
    counts["hwpx_ok"], counts["hwpx_errors"] = _reexport(md, out.assets, Format.HWPX)
    return counts


def _hwpx_counts(pattern: str) -> dict[str, int]:
    data = _find(pattern).read_bytes()
    try:
        with _quiet():
            return _hwpx_measure(data)
    except Exception as exc:  # noqa: BLE001 - keep document text out of the failure message
        raise AssertionError(f"corpus import raised {type(exc).__name__}") from None


_EVERY_HWPX = {
    "coverage_permille": 1000,
    "errors": 0,
    "text_missing": 0,
    "definition_lists": 0,
    "docx_ok": 1,
    "docx_errors": 0,
    "hwpx_ok": 1,
    "hwpx_errors": 0,
}


def _same_tables_as_source(counts: dict[str, int]) -> dict[str, int]:
    """Tables and merged cells as the package has them (R5: the grid squeeze changes none in the corpus)."""
    return {
        "unwrapped": 0,
        "tables": counts["src_tables"],
        "rowspan": counts["src_rowspan"],
        "colspan": counts["src_colspan"],
        "rowspan_sum": counts["src_rowspan_sum"],
        "colspan_sum": counts["src_colspan_sum"],
    }


def _check(counts: dict[str, int], expected: dict[str, int]) -> None:
    assert {k: counts[k] for k in expected} == expected


def test_hwpx_product_description_numbers():
    """02: the 27×2 form table unwraps into 14 label headings, its 10 content tables and 2 pictures."""
    counts = _hwpx_counts("02_*.hwpx")
    _check(counts, {
        **_EVERY_HWPX,
        "unwrapped": 1,
        "top_headers": 14,
        "headers": 14,
        "top_tables": 11,  # the first 2×2 table + 10 tables from content rows
        "images": 2,
        "alt_not_default": 0,
    })


def test_hwpx_evaluation_items_numbers():
    """평가항목: the 11×3 table stays; 10 symbol-font bullets become ▪, 7 of them list items.

    The 16 bullet items in cells are those 7 plus 9 hand-typed ``-`` paragraphs (spec §9 measured).
    """
    counts = _hwpx_counts("*평가항목*.hwpx")
    _check(counts, {
        **_EVERY_HWPX,
        **_same_tables_as_source(counts),
        "src_tables": 1,
        "tables_11x3": 1,
        "symbol_events": 1,
        "symbols_mapped": 10,
        "source_square": 10,
        "left_square": 3,
        "source_dash": 9,
        "left_dash": 0,
        "lists_inferred": 16,
        "cell_bullet_items": 16,
    })


def test_hwpx_self_check_numbers():
    counts = _hwpx_counts("06-01*.hwpx")
    _check(counts, {**_EVERY_HWPX, **_same_tables_as_source(counts), "src_tables": 4})


def test_hwpx_review_opinion_numbers():
    counts = _hwpx_counts("06-02*.hwpx")
    _check(counts, {**_EVERY_HWPX, **_same_tables_as_source(counts), "src_tables": 2})


def test_hwpx_product_spec_numbers():
    """06-03: 33 native numbered paragraphs (+15 hand-typed ones) are list items; 13 pictures."""
    counts = _hwpx_counts("06-03*.hwpx")
    _check(counts, {
        **_EVERY_HWPX,
        **_same_tables_as_source(counts),
        "src_tables": 15,
        "native_list_items": 33,
        "lists_inferred": 15,
        "list_items": 48,
        "headers": 50,
        "images": 13,
        "alt_not_default": 0,
    })


# --- pdf (M3c §7) --------------------------------------------------------------------------------

_PAGE_NUMBER = re.compile(r"-\s*\d+\s*-")
_PAGE_NUMBER_LINE = re.compile(r"\s*\\?-\s*\d+\s*-\s*")  # as the MD has it, escaped or not


def _pdf_measure(data: bytes) -> dict[str, int]:
    result = convert(Source(data, "x.pdf", Format.PDF), [Format.MD])
    out, events = result.outputs[0], result.report.events
    md = out.data
    back = read_md(Source(md, "x.md", Format.MD), Report("x.md", Format.MD)).doc
    cells = _all(back, pf.TableCell)
    images = _all(back, pf.Image)
    levels = [h.level for h in _all(back, pf.Header)]
    texts = [pf.stringify(b).strip() for b in _all(back, (pf.Para, pf.Plain))]
    counts = {
        "coverage_permille": round((result.report.coverage or 0) * 1000),
        "errors": sum(1 for e in events if e.level is Level.ERROR),
        "warnings": sum(1 for e in events if e.level is Level.WARN),
        "multicolumn": sum(1 for e in events if e.code == Codes.PDF_MULTICOLUMN_SUSPECTED),
        "scanned": sum(1 for e in events if e.code == Codes.PDF_SCANNED_SUSPECTED),
        # the vector-drawing warning; the same code at info level counts dropped decorations
        "vector": sum(1 for e in events if e.code == Codes.IMPORT_OBJECT_SKIPPED and e.level is Level.WARN),
        "header_skipped": sum(1 for e in events if e.code == Codes.IMPORT_HEADER_SKIPPED),
        "header_lines_skipped": _event_number(events, Codes.IMPORT_HEADER_SKIPPED),
        "page_number_paras": sum(1 for t in texts if _PAGE_NUMBER.fullmatch(t)),
        "page_number_lines": sum(1 for ln in md.decode("utf-8").splitlines() if _PAGE_NUMBER_LINE.fullmatch(ln)),
        "tables": len(_all(back, pf.Table)),
        "rowspan": sum(c.rowspan > 1 for c in cells),
        "colspan": sum(c.colspan > 1 for c in cells),
        "rowspan_sum": sum(c.rowspan for c in cells if c.rowspan > 1),
        "colspan_sum": sum(c.colspan for c in cells if c.colspan > 1),
        "images": len(images),
        "image_files": len({i.url for i in images}),
        "assets": len(out.assets),
        "headers": len(levels),
        **{f"h{n}": levels.count(n) for n in range(1, 7)},
        "headings_inferred": _event_number(events, Codes.IMPORT_HEADING_INFERRED),
        "list_items": len(_all(back, pf.ListItem)),
        "lists_inferred": _event_number(events, Codes.IMPORT_LIST_INFERRED),
    }
    counts["docx_ok"], counts["docx_errors"] = _reexport(md, out.assets, Format.DOCX)
    counts["hwpx_ok"], counts["hwpx_errors"] = _reexport(md, out.assets, Format.HWPX)
    return counts


def _pdf_counts(pattern: str) -> dict[str, int]:
    data = _find(pattern).read_bytes()
    try:
        with _quiet():
            return _pdf_measure(data)
    except Exception as exc:  # noqa: BLE001 - keep document text out of the failure message
        raise AssertionError(f"corpus import raised {type(exc).__name__}") from None


_EVERY_PDF = {
    "coverage_permille": 1000,
    "errors": 0,
    "warnings": 0,
    "multicolumn": 0,
    "scanned": 0,
    "vector": 0,
    "page_number_paras": 0,
    "page_number_lines": 0,
    "docx_ok": 1,
    "docx_errors": 0,
    "hwpx_ok": 1,
    "hwpx_errors": 0,
}


def test_pdf_notice_corpus():
    """공고문 (11 pages): the ``- n -`` page number goes from all 11 pages; 28 ruled tables, no pictures.

    The tables are those pdfplumber finds per page (1, 2, 2, 6, 2, 1, 3, 4, 5, 1, 1; the 2×1 boxes
    of pages 4, 8 and 9 among them), colspans on pages 2, 5, 6 and 10. Nine tables on pages 3, 5, 7,
    10 and 11 have no outer left/right rules: their body rows' outer cells are not found, so their
    text follows the table as body text and the 5 visible rowspans of pages 5 and 10 are not counted.
    """
    counts = _pdf_counts("*공고문*.pdf")
    _check(counts, {
        **_EVERY_PDF,
        "header_skipped": 1,
        "header_lines_skipped": 11,
        "tables": 28,
        "rowspan": 0,
        "colspan": 4,
        "rowspan_sum": 0,
        "colspan_sum": 8,
        "images": 0,
        "image_files": 0,
        "assets": 0,
        "headers": 3,
        "h1": 1,  # the title, page 1
        "h2": 2,  # pages 5 and 10, from number shape
        "h3": 0,
        "h4": 0,
        "h5": 0,
        "h6": 0,
        "headings_inferred": 2,
        "list_items": 46,
        "lists_inferred": 46,
    })


def test_pdf_guide_corpus():
    """규격서 가이드 (11 pages): 26 ruled tables, 3 pictures on page 6 (two the same icon: 2 files).

    Tables per page 1, 1, 2, 3, 6, 3, 1, 2, 2, 2, 3; rowspans on pages 1, 2, 4, 5 and 10 and
    colspans on pages 4 and 10 as the pages show them.
    """
    counts = _pdf_counts("*규격서 가이드*.pdf")
    _check(counts, {
        **_EVERY_PDF,
        "header_skipped": 0,
        "tables": 26,
        "rowspan": 14,
        "colspan": 2,
        "rowspan_sum": 37,
        "colspan_sum": 6,
        "images": 3,
        "image_files": 2,
        "assets": 2,
        "headers": 5,
        "h1": 1,  # the title, page 1
        "h2": 2,  # h2, h3 and h4: large cover lines, all on page 3
        "h3": 1,
        "h4": 1,
        "h5": 0,
        "h6": 0,
        "headings_inferred": 0,
        "list_items": 64,
        "lists_inferred": 64,
    })
