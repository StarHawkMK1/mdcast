"""Read PDFs into an ImportedDocument."""

from __future__ import annotations

import panflute as pf

from mdcast.readers.imported import ImportedDocument
from mdcast.readers.media import Assets
from mdcast.readers.pdf.body import read_body
from mdcast.readers.pdf.package import open_pdf
from mdcast.report import Report
from mdcast.types import Source


def read_pdf(source: Source, report: Report, assets_dir: str) -> ImportedDocument:
    """A broken or locked PDF raises :class:`~mdcast.readers.pdf.package.PdfError`."""
    pkg = open_pdf(source.data)
    assets = Assets(assets_dir, report)
    try:
        blocks, source_text = read_body(pkg, report, assets)
    finally:
        pkg.pdf.close()
    frontmatter = {k: v for k, v in (("title", pkg.title), ("author", pkg.author)) if v}
    return ImportedDocument(pf.Doc(*blocks), source_text, frontmatter, assets.media, pkg.generator)
