from __future__ import annotations

import panflute as pf

from mdcast.filters._raw import raw_block
from mdcast.filters.importing.context import ImportContext
from mdcast.readers.docx_package import PAGEBREAK_SENTINEL


def apply(doc: pf.Doc, ctx: ImportContext) -> pf.Doc:
    def replace(elem: pf.Element, _doc: pf.Doc) -> pf.Element | None:
        if isinstance(elem, (pf.Para, pf.Plain)) and pf.stringify(elem).strip() == PAGEBREAK_SENTINEL:
            return raw_block("<!-- pagebreak -->", "html")
        return None

    return doc.walk(replace)
