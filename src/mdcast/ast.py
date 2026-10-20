from __future__ import annotations

import io
import tempfile
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path

import panflute as pf
import pypandoc

MD_READER_FORMAT = "markdown-markdown_in_html_blocks"
# pandoc warnings (an unused note key, TeX it cannot draw) are noise on the read and import paths;
# errors still fail the call
QUIET = ["--quiet"]


def json_to_doc(text: str) -> pf.Doc:
    return pf.load(io.StringIO(text))


def doc_to_json(doc: pf.Doc) -> str:
    buffer = io.StringIO()
    pf.dump(doc, buffer)
    return buffer.getvalue()


def clone(doc: pf.Doc) -> pf.Doc:
    return json_to_doc(doc_to_json(doc))


def copy_element(elem: pf.Element) -> pf.Element:
    """Deep copy of one element and its content, not of its ancestors.

    A plain ``deepcopy`` follows ``.parent`` and copies the whole document every time.
    """
    parent = elem.parent
    return deepcopy(elem, {id(parent): parent} if parent is not None else None)


def md_to_doc(text: str) -> pf.Doc:
    return json_to_doc(pypandoc.convert_text(text, "json", format=MD_READER_FORMAT, extra_args=QUIET))


def html_to_blocks(html: str) -> list[pf.Element]:
    return list(json_to_doc(pypandoc.convert_text(html, "json", format="html", extra_args=QUIET)).content)


def convert_doc(
    doc: pf.Doc,
    to: str,
    *,
    outputfile: Path | None = None,
    extra_args: Sequence[str] = (),
) -> str:
    return pypandoc.convert_text(
        doc_to_json(doc),
        to,
        format="json",
        outputfile=str(outputfile) if outputfile else None,
        extra_args=list(extra_args),
    )


def pandoc_version() -> str:
    return pypandoc.get_pandoc_version()


def docx_to_doc(data: bytes) -> pf.Doc:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "in.docx"
        path.write_bytes(data)
        return json_to_doc(pypandoc.convert_file(str(path), "json", format="docx", extra_args=QUIET))
