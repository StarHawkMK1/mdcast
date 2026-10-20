"""Real-document import checks, local only (M3a §9).

The corpus holds personal data: assert numbers only and never print, save or snapshot its text.
Every count is computed into plain ints first so a failure message shows numbers, not content.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import sys
import tempfile
import warnings
from collections.abc import Iterator
from pathlib import Path

import panflute as pf
import pytest

from mdcast.ast import docx_to_doc
from mdcast.pipeline import convert
from mdcast.readers.md import read_md
from mdcast.report import Codes, Level, Report
from mdcast.types import Format, Options, Source

pytestmark = pytest.mark.corpus

_TOP = re.compile(r"^\d+\. ")
_SUB = re.compile(r"^\d+\.\d+")


def _corpus_file() -> Path:
    root = os.environ.get("MDCAST_CORPUS_DIR")
    if not root:
        pytest.skip("MDCAST_CORPUS_DIR not set")
    found = sorted(Path(root).glob("*시험합의서*.docx"))
    if not found:
        pytest.skip("no 시험합의서 docx in MDCAST_CORPUS_DIR")
    return found[0]


def _all(doc: pf.Doc, cls: type) -> list:
    found: list = []
    doc.walk(lambda e, _d: found.append(e) if isinstance(e, cls) else None)
    return found


def _spans(doc: pf.Doc) -> tuple[int, int]:
    cells = _all(doc, pf.TableCell)
    return sum(c.rowspan > 1 for c in cells), sum(c.colspan > 1 for c in cells)


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
        **_heading_counts(back),
    }
    with tempfile.TemporaryDirectory() as tmp:  # the pictures may hold form text: never keep them
        base = Path(tmp)
        for name, blob in out.assets.items():
            (base / name).parent.mkdir(parents=True, exist_ok=True)
            (base / name).write_bytes(blob)
        again = convert(
            Source(md, "x.md", Format.MD, base_dir=base),
            [Format.DOCX],
            options=Options(offline=True, cwd=base, home=base / "home"),
        )
        counts["reexport_ok"] = int(again.outputs[0].data is not None)
        counts["reexport_errors"] = sum(1 for e in again.report.events if e.level is Level.ERROR)
    return counts


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
