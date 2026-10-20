from __future__ import annotations

import panflute as pf

from mdcast.filters.importing import headings, lists, mdcast_doc, pagebreak
from mdcast.filters.importing.context import ImportContext

PIPELINE = (pagebreak.apply, mdcast_doc.apply, headings.apply, lists.apply)


def run_import_filters(doc: pf.Doc, ctx: ImportContext) -> pf.Doc:
    for step in PIPELINE:
        doc = step(doc, ctx)
    return doc


__all__ = ["ImportContext", "run_import_filters"]
