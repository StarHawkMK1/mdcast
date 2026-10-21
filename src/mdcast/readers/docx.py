from __future__ import annotations

import io
import re
import zipfile

import panflute as pf

from mdcast.ast import docx_to_doc
from mdcast.readers.docx_package import prepare_docx
from mdcast.readers.imported import ImportedDocument
from mdcast.readers.media import (
    SMALL_IMAGE_INCHES,
    Assets,
    _media_name,  # noqa: F401 - tests check names through this reader
    warn_image_text,
)
from mdcast.report import Codes, Report
from mdcast.types import Source

_LENGTH = re.compile(r"^\s*([0-9.]+(?:[eE][-+]?\d+)?)\s*(in|cm|mm|px|pt|pc)?\s*$")
_INCHES = {"in": 1.0, "cm": 1 / 2.54, "mm": 1 / 25.4, "px": 1 / 96, "pt": 1 / 72, "pc": 1 / 6, None: 1 / 96}


def _inches(value: str | None) -> float | None:
    match = _LENGTH.match(value or "")
    return float(match.group(1)) * _INCHES[match.group(2)] if match else None


def _has_description(img: pf.Image) -> bool:
    return bool(pf.stringify(img).strip())


def _small(img: pf.Image) -> bool:
    height = _inches(img.attributes.get("height"))
    return not _has_description(img) and height is not None and height <= SMALL_IMAGE_INCHES


def read_docx(source: Source, report: Report, assets_dir: str) -> ImportedDocument:
    prepared = prepare_docx(source.data)
    doc = docx_to_doc(prepared.data)

    warn_image_text(doc, report, _small)

    with zipfile.ZipFile(io.BytesIO(prepared.data)) as package:
        names = set(package.namelist())
        blobs = {n: package.read(n) for n in names if n.startswith("word/media/")}
    assets = Assets(assets_dir, report)

    def finish(elem: pf.Element, _doc: pf.Doc) -> None:
        if not isinstance(elem, pf.Image):
            return
        if f"word/{elem.url}" in blobs:
            elem.url = assets.add(elem.url, blobs[f"word/{elem.url}"])
        if not _has_description(elem):
            elem.content = [pf.Str("그림")]
        elem.attributes.pop("width", None)
        elem.attributes.pop("height", None)

    doc.walk(finish)

    if prepared.has_header_footer or prepared.has_comments:
        report.info(Codes.IMPORT_HEADER_SKIPPED, "머리말·꼬리말·메모는 가져오지 않습니다")

    frontmatter = {k: v for k, v in (("title", prepared.title), ("author", prepared.author)) if v}
    return ImportedDocument(
        doc, prepared.source_text, frontmatter, assets.media, prepared.generator, prepared.table_styles
    )
