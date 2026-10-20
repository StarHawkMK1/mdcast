from __future__ import annotations

from pathlib import Path

import panflute as pf

from mdcast.filters.importing import ImportContext, run_import_filters
from mdcast.readers.docx_package import PAGEBREAK_SENTINEL
from mdcast.report import Report
from mdcast.types import Format


def make_ctx() -> ImportContext:
    return ImportContext(Report("a.docx", Format.DOCX), {}, {}, Path("."), Path("."))


def test_sentinel_paragraph_becomes_pagebreak_marker():
    doc = pf.Doc(pf.Para(pf.Str("앞")), pf.Para(pf.Str(PAGEBREAK_SENTINEL)), pf.Para(pf.Str("뒤")))
    out = run_import_filters(doc, make_ctx())
    assert [type(b).__name__ for b in out.content] == ["Para", "RawBlock", "Para"]
    marker = out.content[1]
    assert (marker.text, marker.format) == ("<!-- pagebreak -->", "html")


def test_sentinel_inside_text_is_left_alone():
    doc = pf.Doc(pf.Para(pf.Str("글 " + PAGEBREAK_SENTINEL)))
    out = run_import_filters(doc, make_ctx())
    assert isinstance(out.content[0], pf.Para)
