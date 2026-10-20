"""Convert picture formats that markdown viewers can't show into PNG."""

from __future__ import annotations

import io
from pathlib import PurePosixPath

PASS_THROUGH = {"png", "jpg", "jpeg", "gif", "svg", "webp"}
VECTOR = {"wmf", "emf"}
RASTER = {"tif", "tiff", "bmp"}


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
