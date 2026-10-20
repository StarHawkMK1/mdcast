from __future__ import annotations

import http.client
import itertools
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections.abc import Callable
from pathlib import Path

import panflute as pf

from mdcast.report import Codes
from mdcast.units import parse_length_mm, parse_ratio
from mdcast.writers.context import WriterContext

MAX_IMAGE_BYTES = 20 * 1024 * 1024
_CHUNK = 64 * 1024
# the root element must be <svg> (after an optional BOM, XML declaration, comments and doctype),
# so an HTML error page that merely contains an inline <svg> icon is not taken for an image
_SVG_START = re.compile(
    rb"(?:\xef\xbb\xbf)?\s*(?:<\?xml[^>]*\?>\s*)?(?:(?:<!--.*?-->|<!DOCTYPE\s+svg[^>]*>)\s*)*<svg[\s>/]",
    re.IGNORECASE | re.DOTALL,
)


class _ImageError(Exception):
    pass


class _HttpOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme not in ("http", "https"):
            raise urllib.error.URLError(f"허용되지 않는 리다이렉트: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url: str, timeout: float) -> bytes:
    opener = urllib.request.build_opener(_HttpOnlyRedirect)
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    total = 0
    expected = None
    try:
        with opener.open(url, timeout=timeout) as response:
            expected = response.headers.get("Content-Length")
            while True:
                if time.monotonic() > deadline:
                    raise _ImageError(f"{timeout:g}초 안에 내려받지 못했습니다")
                chunk = response.read(_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    raise _ImageError(f"이미지가 너무 큽니다(최대 {MAX_IMAGE_BYTES // (1024 * 1024)}MB)")
                chunks.append(chunk)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise _ImageError(str(exc)) from exc
    if expected is not None and expected.isdigit() and total != int(expected):
        raise _ImageError("응답이 중간에 끊겼습니다")
    return b"".join(chunks)


def _load(url: str, ctx: WriterContext) -> tuple[bytes, str]:
    """The image bytes and the extension its name suggests (may be empty)."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("http", "https"):
        if ctx.options.offline:
            raise _ImageError("오프라인 모드")
        return _fetch(url, ctx.options.url_timeout_s), Path(parsed.path).suffix.lower()
    if parsed.scheme and len(parsed.scheme) > 1:
        raise _ImageError(f"지원하지 않는 주소 형식: {parsed.scheme}")
    path = Path(urllib.parse.unquote(url))
    if not path.is_absolute():
        path = (ctx.base_dir or Path.cwd()) / path
    if not path.is_file():
        raise _ImageError("파일이 없습니다")
    try:
        return path.read_bytes(), path.suffix.lower()
    except OSError as exc:
        raise _ImageError(str(exc)) from exc


def _png_complete(data: bytes) -> bool:
    """Every chunk is whole with a matching CRC, up to IEND (catches truncated or damaged files)."""
    pos = 8
    while pos + 12 <= len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        end = pos + 12 + length
        if end > len(data):
            return False
        if zlib.crc32(data[pos + 4 : end - 4]) != int.from_bytes(data[end - 4 : end], "big"):
            return False
        if data[pos + 4 : pos + 8] == b"IEND":
            return True
        pos = end
    return False


def _extension(data: bytes, named: str, strict: bool) -> str:
    """The file extension for the image bytes; the renderers pick their decoder by extension.

    Unrecognised or damaged data keeps the extension of its name (``.png`` when it has none),
    unless ``strict``, which rejects it instead.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if strict and not _png_complete(data):
            raise _ImageError("이미지 파일이 손상되었습니다")
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if _SVG_START.match(data[:4096]):
        return ".svg"
    if _is_bmp(data) and not strict:
        return ".bmp"
    if strict:
        raise _ImageError("지원하지 않는 이미지 형식입니다 (PNG, JPEG, GIF, WebP, SVG 만 지원)")
    return named or ".png"


MAX_IMAGE_PX = 65535  # larger sides are not real pictures and overflow Hangul's sizes
_BMP_HEADERS = (12, 40, 52, 56, 108, 124)  # DIB header sizes


def _is_bmp(data: bytes) -> bool:
    """``BM``, a known DIB header size and one colour plane, so text that starts with BM is not taken."""
    return (
        data[:2] == b"BM" and len(data) >= 30
        and int.from_bytes(data[14:18], "little") in _BMP_HEADERS
        and int.from_bytes(data[26:28] if data[14] != 12 else data[22:24], "little") == 1
    )


_SVG_UNITS = {"": 1.0, "px": 1.0, "pt": 96 / 72, "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0}
_SVG_LENGTH = re.compile(r"\s*([0-9]*\.?[0-9]+)\s*(px|pt|mm|cm|in)?\s*$")
_SVG_ROOT = re.compile(rb"<svg\b([^>]*)>", re.IGNORECASE | re.DOTALL)


def _svg_attr(attrs: str, name: str) -> str | None:
    match = re.search(rf"""(?:^|\s){name}\s*=\s*(["'])(.*?)\1""", attrs, re.DOTALL)
    return match.group(2) if match else None


def _svg_size(data: bytes) -> tuple[int, int]:
    """Root ``width``/``height`` (px at 96 dpi), else the ``viewBox`` size, else 300x150."""
    root = _SVG_ROOT.search(data[:65536])
    attrs = root.group(1).decode("utf-8", "replace") if root else ""

    def length(name: str) -> float | None:
        value = _svg_attr(attrs, name)
        match = _SVG_LENGTH.match(value) if value else None
        return float(match.group(1)) * _SVG_UNITS[match.group(2) or ""] if match else None

    width, height = length("width"), length("height")
    if width and height:
        return round(width), round(height)
    box = (_svg_attr(attrs, "viewBox") or "").replace(",", " ").split()
    try:
        if len(box) == 4 and float(box[2]) > 0 and float(box[3]) > 0:
            return round(float(box[2])), round(float(box[3]))
    except ValueError:
        pass
    return 300, 150


def _jpeg_info(data: bytes) -> tuple[int, int, float]:
    dpi = 0.0
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        length = int.from_bytes(data[pos + 2 : pos + 4], "big")
        segment = data[pos + 4 : pos + 2 + length]
        if marker == 0xE0 and segment[:5] == b"JFIF\x00" and len(segment) >= 12:
            unit, density = segment[7], int.from_bytes(segment[8:10], "big")
            dpi = density if unit == 1 else density * 2.54 if unit == 2 else 0.0
        elif 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC) and len(segment) >= 5:
            height, width = int.from_bytes(segment[1:3], "big"), int.from_bytes(segment[3:5], "big")
            return width, height, dpi
        pos += 2 + length
    raise ValueError("JPEG 크기를 찾지 못했습니다")


def _png_dpi(data: bytes) -> float:
    pos = 8
    while pos + 12 <= len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        if kind == b"pHYs" and length >= 9:
            ppm = int.from_bytes(data[pos + 8 : pos + 12], "big")
            return round(ppm * 0.0254) if data[pos + 16] == 1 else 0.0
        if kind in (b"IDAT", b"IEND"):
            break
        pos += 12 + length
    return 0.0


def _webp_size(data: bytes) -> tuple[int, int]:
    chunk = data[12:16]
    if chunk == b"VP8X":
        return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    if chunk == b"VP8L":
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 ":
        return int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(data[28:30], "little") & 0x3FFF
    raise ValueError("WebP 크기를 찾지 못했습니다")


def image_info(data: bytes, default_dpi: float = 96.0) -> tuple[str, int, int, float]:
    """(format, width px, height px, dpi) of PNG, JPEG, GIF, BMP, WebP or SVG bytes.

    A raster image that does not say gets ``default_dpi``; SVG px are CSS px, 96 to the inch.

    Raises ``ValueError`` for anything else or a header too short to read.
    """
    try:
        if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
            kind, width, height = "png", int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
            dpi = _png_dpi(data)
        elif data.startswith(b"\xff\xd8\xff"):
            kind, (width, height, dpi) = "jpg", _jpeg_info(data)
        elif data[:6] in (b"GIF87a", b"GIF89a"):
            kind, width, height, dpi = "gif", int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little"), 0.0
        elif _is_bmp(data):
            kind, width = "bmp", int.from_bytes(data[18:22], "little", signed=True)
            height = abs(int.from_bytes(data[22:26], "little", signed=True))
            ppm = int.from_bytes(data[38:42], "little") if len(data) >= 42 else 0
            dpi = round(ppm * 0.0254)
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            kind, (width, height), dpi = "webp", _webp_size(data), 0.0
        elif _SVG_START.match(data[:4096]):
            kind, (width, height), dpi = "svg", _svg_size(data), 96.0
        else:
            raise ValueError("알 수 없는 이미지 형식입니다")
    except IndexError as exc:
        raise ValueError("이미지 머리가 잘렸습니다") from exc
    if not (0 < width <= MAX_IMAGE_PX and 0 < height <= MAX_IMAGE_PX):
        raise ValueError("이미지 크기가 0 입니다")
    return kind, width, height, float(dpi) if dpi and dpi > 0 else default_dpi


def _png_with_dpi(data: bytes, dpi: float) -> bytes:
    ppm = round(dpi / 0.0254).to_bytes(4, "big")
    body = b"pHYs" + ppm + ppm + b"\x01"
    chunk = (9).to_bytes(4, "big") + body + zlib.crc32(body).to_bytes(4, "big")
    pos = 8
    while pos + 12 <= len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        if kind == b"pHYs":  # only one is allowed: replace it
            return data[:pos] + chunk + data[pos + 12 + length :]
        if kind in (b"IDAT", b"IEND"):
            break
        pos += 12 + length
    after_ihdr = 8 + 12 + 13
    return data[:after_ihdr] + chunk + data[after_ihdr:]


def _jpeg_with_dpi(data: bytes, dpi: float) -> bytes:
    density = round(dpi).to_bytes(2, "big")
    if data[2:4] == b"\xff\xe0" and data[6:11] == b"JFIF\x00":  # JFIF: units 1 (dpi), x and y density
        return data[:13] + b"\x01" + density + density + data[18:]
    app0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x01" + density + density + b"\x00\x00"
    return data[:2] + app0 + data[2:]


def with_dpi(data: bytes, dpi: float) -> bytes:
    """PNG or JPEG bytes that state ``dpi`` (Typst sizes a picture by it); other formats unchanged."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
        return _png_with_dpi(data, dpi)
    if data.startswith(b"\xff\xd8\xff"):
        return _jpeg_with_dpi(data, dpi)
    return data


def figure_limit(value: object) -> tuple[float | None, float | None]:
    """``figures.max_width`` as (ratio of the available width, length in mm); one of them is set."""
    if value is None:
        return 1.0, None
    if str(value).strip().endswith("%"):
        return parse_ratio(value), None
    return None, parse_length_mm(value)


def image_complete(kind: str, data: bytes) -> bool:
    """Whether the file runs to its end marker (a cut download or copy otherwise shows half a picture)."""
    if kind == "png":
        return _png_complete(data)
    if kind == "jpg":
        return b"\xff\xd9" in data[-1024:]
    if kind == "gif":
        return data.rstrip(b"\x00").endswith(b";")
    if kind == "bmp":
        return int.from_bytes(data[2:6], "little") <= len(data)
    return True


def raster_to_png(data: bytes, kind: str, width_px: int, work_dir: Path) -> bytes:
    """A WebP or GIF as a PNG of the same pixels, drawn by Typst.

    Hangul cannot place WebP (appendix B-11); WebP and GIF hold no dpi for Typst to size them by.
    """
    import typst

    folder = work_dir / "to-png"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{len(list(folder.glob('*.typ'))) + 1}.{kind}"
    (folder / name).write_bytes(data)
    main = folder / f"{name}.typ"
    main.write_text(
        f'#set page(width: auto, height: auto, margin: 0pt, fill: none)\n'
        f'#image("{name}", width: {width_px * 0.75}pt)\n',
        encoding="utf-8",
    )
    return typst.compile(str(main), root=str(folder), format="png", ppi=96.0, ignore_system_fonts=True)


def _caption_inlines(figure: pf.Figure) -> list[pf.Inline]:
    inlines: list[pf.Inline] = []
    for block in figure.caption.content if figure.caption else []:
        if isinstance(block, (pf.Plain, pf.Para)):
            if inlines:
                inlines.append(pf.Space())
            inlines.extend(block.content)
    return inlines


def localize_images(
    doc: pf.Doc,
    ctx: WriterContext,
    *,
    strict_types: bool = False,
    check: Callable[[str], str | None] | None = None,
    prepare: Callable[[bytes], bytes] | None = None,
) -> pf.Doc:
    """Copy every image into ``work_dir/assets`` under a name whose extension matches its bytes.

    ``prepare`` may rewrite the bytes first (a GIF may become a PNG and is then named so).

    An image that cannot be loaded, or that is rejected by ``check`` (given the ``assets/...``
    path, returns a reason or ``None``) becomes a placeholder with an IMAGE_FETCH_FAILED
    warning. With ``strict_types`` (PDF: Typst only reads PNG, JPEG, GIF, WebP and SVG) an
    unrecognised or damaged image does too; otherwise (docx: Word shows BMP, TIFF, EMF, ...) it
    is kept under its own extension. A figure that lost an image becomes a plain paragraph that
    keeps its caption text, so the writers do not turn it into a layout table.
    """
    assets = ctx.work_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    counter = itertools.count(1)
    placeholders: set[int] = set()

    def localize(elem: pf.Image) -> pf.Element | None:
        try:
            data, named = _load(elem.url, ctx)
            if prepare is not None:
                data = prepare(data)
            name = f"img{next(counter)}{_extension(data, named, strict_types)}"
            (assets / name).write_bytes(data)
            reason = check(f"assets/{name}") if check is not None else None
            if reason is not None:
                raise _ImageError(reason)
        except _ImageError as exc:
            alt = pf.stringify(elem).strip() or elem.url
            ctx.report.warn(
                Codes.IMAGE_FETCH_FAILED,
                f"이미지를 쓸 수 없어 자리표시로 대체했습니다: {elem.url} ({exc})",
                format=ctx.target.value,
                url=elem.url,
            )
            placeholder = pf.Emph(pf.Str(f"[이미지: {alt}]"))
            placeholders.add(id(placeholder))
            # keep the image's id, or links to it break (Typst: missing label)
            return pf.Span(placeholder, identifier=elem.identifier) if elem.identifier else placeholder
        elem.url = f"assets/{name}"
        return None

    def unwrap(figure: pf.Figure) -> pf.Element | None:
        lost: list[bool] = []
        figure.content.walk(lambda e, _d: lost.append(True) if id(e) in placeholders else None)
        if not lost:
            return None
        inlines: list[pf.Inline] = []
        for block in figure.content:
            if isinstance(block, (pf.Plain, pf.Para)):
                if inlines:
                    inlines.append(pf.LineBreak())
                inlines.extend(block.content)
        caption = _caption_inlines(figure)
        if caption:
            inlines += [pf.LineBreak(), *caption]
        para = pf.Para(*inlines)
        # keep the figure's id, or links/cross-references to it break (Typst: missing label)
        return pf.Div(para, identifier=figure.identifier) if figure.identifier else para

    def action(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.Image):
            return localize(elem)
        if isinstance(elem, pf.Figure):
            return unwrap(elem)
        return None

    return doc.walk(action)
