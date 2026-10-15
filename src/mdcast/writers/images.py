from __future__ import annotations

import http.client
import itertools
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import panflute as pf

from mdcast.report import Codes
from mdcast.writers.context import WriterContext

MAX_IMAGE_BYTES = 20 * 1024 * 1024
_CHUNK = 64 * 1024


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
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("http", "https"):
        if ctx.options.offline:
            raise _ImageError("오프라인 모드")
        data = _fetch(url, ctx.options.url_timeout_s)
        return data, Path(parsed.path).suffix.lower() or ".png"
    if parsed.scheme and len(parsed.scheme) > 1:
        raise _ImageError(f"지원하지 않는 주소 형식: {parsed.scheme}")
    path = Path(urllib.parse.unquote(url))
    if not path.is_absolute():
        path = (ctx.base_dir or Path.cwd()) / path
    if not path.is_file():
        raise _ImageError("파일이 없습니다")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise _ImageError(str(exc)) from exc
    return data, path.suffix.lower() or ".png"


def localize_images(doc: pf.Doc, ctx: WriterContext) -> pf.Doc:
    assets = ctx.work_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    counter = itertools.count(1)

    def action(elem: pf.Element, _doc: pf.Doc):
        if not isinstance(elem, pf.Image):
            return None
        try:
            data, ext = _load(elem.url, ctx)
        except _ImageError as exc:
            alt = pf.stringify(elem).strip() or elem.url
            ctx.report.warn(
                Codes.IMAGE_FETCH_FAILED,
                f"이미지를 가져오지 못해 자리표시로 대체했습니다: {elem.url} ({exc})",
                format=ctx.target.value,
                url=elem.url,
            )
            return pf.Emph(pf.Str(f"[이미지: {alt}]"))
        name = f"img{next(counter)}{ext}"
        (assets / name).write_bytes(data)
        elem.url = f"assets/{name}"
        return None

    return doc.walk(action)
