from __future__ import annotations

import panflute as pf

from mdcast.filters.importing import headings, lists, pagebreak
from mdcast.filters.importing.context import ImportContext

# Task 8 inserts mdcast_doc.apply between the two; Task 7 appended lists.apply.
PIPELINE = (pagebreak.apply, headings.apply, lists.apply)


def run_import_filters(doc: pf.Doc, ctx: ImportContext) -> pf.Doc:
    for step in PIPELINE:
        doc = step(doc, ctx)
    return doc


__all__ = ["ImportContext", "run_import_filters"]
