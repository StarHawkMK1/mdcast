from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path

import panflute as pf
import pypandoc

MD_READER_FORMAT = "markdown-markdown_in_html_blocks"


def json_to_doc(text: str) -> pf.Doc:
    return pf.load(io.StringIO(text))


def doc_to_json(doc: pf.Doc) -> str:
    buffer = io.StringIO()
    pf.dump(doc, buffer)
    return buffer.getvalue()


def clone(doc: pf.Doc) -> pf.Doc:
    return json_to_doc(doc_to_json(doc))


def md_to_doc(text: str) -> pf.Doc:
    return json_to_doc(pypandoc.convert_text(text, "json", format=MD_READER_FORMAT))


def html_to_blocks(html: str) -> list[pf.Element]:
    return list(json_to_doc(pypandoc.convert_text(html, "json", format="html")).content)


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
