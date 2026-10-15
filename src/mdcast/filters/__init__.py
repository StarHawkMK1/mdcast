from __future__ import annotations

import panflute as pf

from mdcast.filters import pagebreak
from mdcast.filters.context import FilterContext

PIPELINE = (pagebreak.apply,)


def run_filters(doc: pf.Doc, ctx: FilterContext) -> pf.Doc:
    for step in PIPELINE:
        doc = step(doc, ctx)
    return doc


__all__ = ["FilterContext", "run_filters"]
