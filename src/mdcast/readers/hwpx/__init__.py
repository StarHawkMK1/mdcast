"""Read hwpx (OWPML) packages into an ImportedDocument."""

from __future__ import annotations

import panflute as pf

from mdcast.readers.hwpx.body import BodyReader
from mdcast.readers.hwpx.package import open_hwpx
from mdcast.readers.imported import ImportedDocument
from mdcast.readers.media import Assets, warn_image_text
from mdcast.report import Report
from mdcast.types import Source


def read_hwpx(source: Source, report: Report, assets_dir: str) -> ImportedDocument:
    """A broken or secured package raises :class:`~mdcast.readers.hwpx.package.HwpxError`."""
    pkg = open_hwpx(source.data)
    assets = Assets(assets_dir, report)
    reader = BodyReader(pkg, report, assets)
    doc = pf.Doc(*reader.blocks())
    warn_image_text(doc, report, reader.is_small)
    reader.report_skipped()
    frontmatter = {k: v for k, v in (("title", pkg.title), ("author", pkg.creator)) if v}
    return ImportedDocument(doc, reader.source_text, frontmatter, assets.media, pkg.generator)
