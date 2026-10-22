"""Build small PDFs for reader tests with typst and the bundled fonts only.

The bundled Noto Sans KR is a variable font: bold Hangul is still named ``NotoSansKR-Thin``.
A test that asserts bold writes Latin text (Libertinus Serif, ``LibertinusSerif-Bold`` when bold).
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping, Sequence
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


def raw_pdf(objects: Sequence[bytes]) -> bytes:
    """A PDF of ``objects`` (object 1, the catalog, first) with a correct cross-reference table.

    For what typst never writes: a page box away from the origin, a broken page tree.
    """
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


Placed = tuple[float, float, str]  # x, y (PDF user space: y grows upwards), Latin text


def helvetica_pdf(pages: Sequence[Sequence[Placed]], media_box: tuple[int, int, int, int] = (0, 0, 612, 792)) -> bytes:
    """Pages of 11 pt Helvetica lines, each placed where it says, on ``media_box``."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        content = b"".join(b"BT /F1 11 Tf %.2f %.2f Td (%s) Tj ET\n" % (x, y, t.encode("ascii")) for x, y, t in lines)
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [%d %d %d %d] " % media_box
            + b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (len(objects))
        )
        kids.append(len(objects))
    refs = b" ".join(b"%d 0 R" % kid for kid in kids)
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (refs, len(kids))
    return raw_pdf(objects)
