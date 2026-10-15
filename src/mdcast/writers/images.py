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
    if strict:
        raise _ImageError("지원하지 않는 이미지 형식입니다 (PNG, JPEG, GIF, WebP, SVG 만 지원)")
    return named or ".png"


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
) -> pf.Doc:
    """Copy every image into ``work_dir/assets`` under a name whose extension matches its bytes.

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
