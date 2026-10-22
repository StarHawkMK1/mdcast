"""Build small PDFs for reader tests with typst and the bundled fonts only.

The bundled Noto Sans KR is a variable font: bold Hangul is still named ``NotoSansKR-Thin``.
A test that asserts bold writes Latin text (Libertinus Serif, ``LibertinusSerif-Bold`` when bold).
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path

import typst

from mdcast.fonts import BUNDLED_FONT_DIR


def typst_pdf(body: str, *, page: str = 'paper: "a4"', files: Mapping[str, bytes] | None = None) -> bytes:
    """The PDF typst makes of ``body``; ``files`` (path → bytes) sit beside it for ``#image``."""
    source = (
        f"#set page({page})\n"
        '#set text(font: ("Libertinus Serif", "Noto Sans KR"), size: 11pt)\n'
        f"{body}\n"
    )
    with tempfile.TemporaryDirectory(prefix="mdcast-pdf-") as tmp:
        root = Path(tmp)
        for name, data in (files or {}).items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        main = root / "main.typ"
        main.write_text(source, encoding="utf-8")
        return typst.compile(
            str(main), root=str(root), ignore_system_fonts=True, font_paths=[str(BUNDLED_FONT_DIR)]
        )
