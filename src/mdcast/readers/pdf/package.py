"""Open a PDF with pdfplumber and read its document information."""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect

_LOCKED = "열람 암호가 걸린 PDF 는 읽을 수 없습니다. 암호를 푼 PDF 로 다시 저장해 넣어 주십시오."
_BROKEN = "PDF 파일로 열 수 없습니다. 파일이 깨졌을 수 있습니다."

# Keywords token name → generator key, as writers/generator.py names them
_KEYWORDS = {
    "pandoc": "mdcast.pandoc",
    "typst": "mdcast.typst",
    "template": "mdcast.template.name",
    "template-version": "mdcast.template.version",
    "template-source": "mdcast.template.source",
}


class PdfError(Exception):
    """A broken or locked PDF. The message is shown to the user."""


@dataclass
class PdfPackage:
    pdf: pdfplumber.PDF
    title: str | None
    author: str | None
    generator: dict[str, str]  # from Keywords when mdcast made the PDF


def open_pdf(data: bytes) -> PdfPackage:
    """A PDF that only forbids copying or printing opens as it is: pdfplumber ignores permissions."""
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # whatever pdfminer raises, the file cannot be read
        raise PdfError(_LOCKED if _is_locked(exc) else _BROKEN) from exc
    try:
        len(pdf.pages)  # some damage only shows once the page tree is read
    except Exception as exc:
        with contextlib.suppress(Exception):  # close() walks the same broken pages
            pdf.close()
        raise PdfError(_BROKEN) from exc
    try:
        info = pdf.metadata
        title, author = _text(info.get("Title")), _text(info.get("Author"))
        generator = generator_from_keywords(info.get("Keywords"))
    except Exception:  # noqa: BLE001 - unreadable document information leaves only it out
        title, author, generator = None, None, {}
    return PdfPackage(pdf, title, author, generator)


def _is_locked(exc: BaseException) -> bool:
    """``exc`` or what it wraps (pdfplumber re-raises pdfminer's errors) is a wrong password."""
    seen: set[int] = set()
    todo: list[object] = [exc]
    while todo:
        e = todo.pop()
        if not isinstance(e, BaseException) or id(e) in seen:
            continue
        if isinstance(e, PDFPasswordIncorrect):
            return True
        seen.add(id(e))
        todo += [*e.args, e.__cause__, e.__context__]
    return False


def _text(value: object) -> str | None:
    """A document information value as text; anything empty or not a string is None."""
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            value = value.decode("latin-1")
    if not isinstance(value, str):
        return None
    return value.strip() or None


def generator_from_keywords(keywords: object) -> dict[str, str]:
    """The generator facts in the Keywords the mdcast pdf writer sets (``mdcast, template:…``).

    Keywords without the exact token ``mdcast`` were not written by mdcast and give nothing.
    """
    text = _text(keywords)
    if text is None:
        return {}
    tokens = [t.strip() for t in text.split(",")]
    if "mdcast" not in tokens:
        return {}
    out: dict[str, str] = {}
    for token in tokens:
        name, sep, value = token.partition(":")
        value = value.strip()
        if not sep or not value:
            continue
        name = name.strip()
        if name == "mdcast":
            out["mdcast.generator"] = f"mdcast {value}"
        elif name in _KEYWORDS:
            out[_KEYWORDS[name]] = value
    return out
