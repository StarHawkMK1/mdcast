from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator
from typing import Any

import panflute as pf

from mdcast.ast import docx_to_doc
from mdcast.readers.docx_package import prepare_docx
from mdcast.readers.imported import ImportedDocument
from mdcast.readers.media import to_png
from mdcast.report import Codes, Report
from mdcast.types import Source

SMALL_IMAGE_INCHES = 0.5
_LENGTH = re.compile(r"^\s*([0-9.]+(?:[eE][-+]?\d+)?)\s*(in|cm|mm|px|pt|pc)?\s*$")
_UNSAFE_NAME = re.compile(r'[:*?"<>|]')
_INCHES = {"in": 1.0, "cm": 1 / 2.54, "mm": 1 / 25.4, "px": 1 / 96, "pt": 1 / 72, "pc": 1 / 6, None: 1 / 96}


def _inches(value: str | None) -> float | None:
    match = _LENGTH.match(value or "")
    return float(match.group(1)) * _INCHES[match.group(2)] if match else None


def _rows(table: pf.Table) -> Iterator[pf.TableRow]:
    yield from table.head.content
    for body in table.content:
        yield from body.head
        yield from body.content
    yield from table.foot.content


def _images_in_cells(doc: pf.Doc) -> Iterator[tuple[pf.Image, dict[str, int]]]:
    """Images inside table cells with their (pre-order table, row, col) place."""
    counter = [0]

    def visit(elem: Any, place: dict[str, int] | None) -> Iterator[tuple[pf.Image, dict[str, int]]]:
        if isinstance(elem, pf.Table):
            counter[0] += 1
            number = counter[0]
            for r, row in enumerate(_rows(elem), 1):
                for c, cell in enumerate(row.content, 1):
                    for child in cell.content:
                        yield from visit(child, {"table": number, "row": r, "col": c})
            return
        if isinstance(elem, pf.Image):
            if place:
                yield elem, place
            return
        for child in getattr(elem, "content", ()):
            yield from visit(child, place)

    for block in doc.content:
        yield from visit(block, None)


def _has_description(img: pf.Image) -> bool:
    return bool(pf.stringify(img).strip())


def _media_name(url: str, n: int) -> str:
    """File name for an image of an untrusted package: never a path, never empty, ``.`` or ``..``.

    Characters Windows does not allow in a file name (``: * ? " < > |``) become ``_``.
    """
    name = _UNSAFE_NAME.sub("_", url.replace("\\", "/").rsplit("/", 1)[-1])
    return name if name not in ("", ".", "..") else f"image{n}.png"


def _unique_name(name: str, blob: bytes, taken: dict[str, bytes]) -> str:
    stem, dot, ext = name.rpartition(".")
    candidate, n = name, 1
    while taken.get(candidate, blob) != blob:
        n += 1
        candidate = f"{stem}-{n}{dot}{ext}"
    return candidate


def read_docx(source: Source, report: Report, assets_dir: str) -> ImportedDocument:
    prepared = prepare_docx(source.data)
    doc = docx_to_doc(prepared.data)

    for img, place in _images_in_cells(doc):
        height = _inches(img.attributes.get("height"))
        if not _has_description(img) and height is not None and height <= SMALL_IMAGE_INCHES:
            report.warn(
                Codes.IMPORT_IMAGE_TEXT,
                "표 칸 안의 작은 그림은 글자였는지 알 수 없어 그림으로 가져옵니다",
                **place,
            )

    with zipfile.ZipFile(io.BytesIO(prepared.data)) as package:
        names = set(package.namelist())
        blobs = {n: package.read(n) for n in names if n.startswith("word/media/")}
    media: dict[str, bytes] = {}
    urls: dict[str, str] = {}

    def convert(url: str) -> str:
        if url in urls:
            return urls[url]
        name = _media_name(url, len(media) + 1)
        blob = blobs[f"word/{url}"]
        converted = to_png(blob, name)
        if converted is None:
            report.warn(Codes.IMAGE_CONVERT_FAILED, "그림 형식을 PNG로 바꾸지 못해 원본 그대로 가져옵니다", name=name)
            converted = (blob, name)
        out_name = _unique_name(converted[1], converted[0], media)
        media[out_name] = converted[0]
        urls[url] = f"{assets_dir}/{out_name}"
        return urls[url]

    def finish(elem: pf.Element, _doc: pf.Doc) -> None:
        if not isinstance(elem, pf.Image):
            return
        if f"word/{elem.url}" in blobs:
            elem.url = convert(elem.url)
        if not _has_description(elem):
            elem.content = [pf.Str("그림")]
        elem.attributes.pop("width", None)
        elem.attributes.pop("height", None)

    doc.walk(finish)

    if prepared.has_header_footer or prepared.has_comments:
        report.info(Codes.IMPORT_HEADER_SKIPPED, "머리말·꼬리말·메모는 가져오지 않습니다")

    frontmatter = {k: v for k, v in (("title", prepared.title), ("author", prepared.author)) if v}
    return ImportedDocument(doc, prepared.source_text, frontmatter, media, prepared.generator, prepared.table_styles)
