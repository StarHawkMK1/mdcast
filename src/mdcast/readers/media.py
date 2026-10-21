"""Pictures of an imported document: file names in the assets folder, PNG conversion, image-text warnings."""

from __future__ import annotations

import io
import re
from collections.abc import Callable, Iterator
from pathlib import PurePosixPath
from typing import Any

import panflute as pf

from mdcast.report import Codes, Report

PASS_THROUGH = {"png", "jpg", "jpeg", "gif", "svg", "webp"}
VECTOR = {"wmf", "emf"}
RASTER = {"tif", "tiff", "bmp"}
SMALL_IMAGE_INCHES = 0.5
_UNSAFE_NAME = re.compile(r'[:*?"<>|]')


def to_png(data: bytes, name: str) -> tuple[bytes, str] | None:
    path = PurePosixPath(name)
    ext = path.suffix.lstrip(".").lower()
    if ext in PASS_THROUGH:
        return data, name
    if ext not in VECTOR | RASTER:
        return None
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            if ext in VECTOR:
                im.load(dpi=192)
            else:
                im.load()
            out = io.BytesIO()
            im.convert("RGBA").save(out, format="PNG")
    except Exception:  # noqa: BLE001 - any undrawable picture is kept as-is, never a failure
        return None
    return out.getvalue(), path.with_suffix(".png").name


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


class Assets:
    """The picture files an import writes into its assets folder (M3a D12)."""

    def __init__(self, assets_dir: str, report: Report) -> None:
        self.assets_dir = assets_dir
        self.report = report
        self.media: dict[str, bytes] = {}  # output file name → bytes
        self._paths: dict[tuple[str, bytes], str] = {}

    def add(self, name: str, blob: bytes) -> str:
        """The MD path of picture ``name`` (a package path or file name) holding ``blob``.

        The name loses any folder and the characters Windows forbids; a picture MD viewers cannot
        show becomes PNG (warn ``IMAGE_CONVERT_FAILED`` and kept as it is when that fails); a
        different picture of the same name gets ``-2``, ``-3``… The same (name, bytes) gives the
        same path.
        """
        key = (name, blob)
        if key in self._paths:
            return self._paths[key]
        safe = _media_name(name, len(self.media) + 1)
        converted = to_png(blob, safe)
        if converted is None:
            self.report.warn(Codes.IMAGE_CONVERT_FAILED, "그림 형식을 PNG로 바꾸지 못해 원본 그대로 가져옵니다", name=safe)
            converted = (blob, safe)
        out_name = _unique_name(converted[1], converted[0], self.media)
        self.media[out_name] = converted[0]
        self._paths[key] = f"{self.assets_dir}/{out_name}"
        return self._paths[key]


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


def warn_image_text(doc: pf.Doc, report: Report, small: Callable[[pf.Image], bool]) -> None:
    """Warn ``IMPORT_IMAGE_TEXT`` for each picture in a table cell that ``small`` picks.

    A small picture with no description in a cell may have been text (a check mark, a symbol);
    the reader decides what is small, this names the place.
    """
    for img, place in _images_in_cells(doc):
        if small(img):
            report.warn(
                Codes.IMPORT_IMAGE_TEXT,
                "표 칸 안의 작은 그림은 글자였는지 알 수 없어 그림으로 가져옵니다",
                **place,
            )
