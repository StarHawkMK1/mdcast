from __future__ import annotations

import itertools
import urllib.parse
import urllib.request
from pathlib import Path

import panflute as pf

from mdcast.report import Codes
from mdcast.writers.context import WriterContext


class _ImageError(Exception):
    pass


def _load(url: str, ctx: WriterContext) -> tuple[bytes, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("http", "https"):
        if ctx.options.offline:
            raise _ImageError("오프라인 모드")
        try:
            with urllib.request.urlopen(url, timeout=ctx.options.url_timeout_s) as response:
                data = response.read()
        except (OSError, ValueError) as exc:
            raise _ImageError(str(exc)) from exc
        return data, Path(parsed.path).suffix.lower() or ".png"
    if parsed.scheme and len(parsed.scheme) > 1:
        raise _ImageError(f"지원하지 않는 주소 형식: {parsed.scheme}")
    path = Path(urllib.parse.unquote(url))
    if not path.is_absolute():
        path = (ctx.base_dir or Path.cwd()) / path
    if not path.is_file():
        raise _ImageError("파일이 없습니다")
    return path.read_bytes(), path.suffix.lower() or ".png"


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
