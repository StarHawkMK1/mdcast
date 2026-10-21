"""Read hwpx (OWPML) packages into an ImportedDocument."""

from __future__ import annotations

import panflute as pf

from mdcast.readers.hwpx.body import BodyReader
from mdcast.readers.hwpx.package import open_hwpx
from mdcast.readers.imported import ImportedDocument
from mdcast.report import Report
from mdcast.types import Source


def read_hwpx(source: Source, report: Report, assets_dir: str) -> ImportedDocument:
    """A broken or secured package raises :class:`~mdcast.readers.hwpx.package.HwpxError`."""
    pkg = open_hwpx(source.data)
    reader = BodyReader(pkg, report, None)
    doc = pf.Doc(*reader.blocks())
    frontmatter = {k: v for k, v in (("title", pkg.title), ("author", pkg.creator)) if v}
    return ImportedDocument(doc, reader.source_text, frontmatter, {}, pkg.generator)
