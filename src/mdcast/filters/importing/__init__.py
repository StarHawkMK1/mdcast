from __future__ import annotations

import panflute as pf

from mdcast.filters.importing import forms, headings, lists, mdcast_doc, pagebreak
from mdcast.filters.importing.context import ImportContext
from mdcast.report import Codes

PIPELINE = (pagebreak.apply, mdcast_doc.apply, headings.apply, lists.apply, forms.apply)


def run_import_filters(doc: pf.Doc, ctx: ImportContext) -> pf.Doc:
    for step in PIPELINE:
        doc = step(doc, ctx)
    # after the form filter: headings it made from form labels count (M3b §5.1)
    if not any(isinstance(b, pf.Header) for b in doc.content):
        ctx.report.warn(Codes.IMPORT_HEADING_INFERRED, "제목을 찾지 못했습니다. 제목 단계 없이 가져옵니다", once=True)
    return doc


__all__ = ["ImportContext", "run_import_filters"]
