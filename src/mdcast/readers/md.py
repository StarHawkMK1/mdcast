from __future__ import annotations

import re
import urllib.parse
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import panflute as pf

from mdcast.ast import grid_cells, html_to_blocks, md_to_doc
from mdcast.report import Codes, Report
from mdcast.types import Source

_TABLE_START = re.compile(r"^\s*<table[\s>]", re.IGNORECASE)
_NOTE_DEF = re.compile(r"^\[\^([^\]\s]+)\]:[ \t]*(.*)$")
_NOTE_REF = re.compile(r"\[\^([^\]\s]+)\]")
_FENCE = re.compile(r"^\s*(```|~~~)")
_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(?:.*?\r?\n)??(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.DOTALL)


@dataclass
class MdDocument:
    doc: pf.Doc
    frontmatter: dict[str, Any] = field(default_factory=dict)


def decode_text(data: bytes, report: Report) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("cp949")
    except UnicodeDecodeError:
        report.warn(Codes.INPUT_ENCODING_FALLBACK, "입력 인코딩을 알 수 없어 깨진 글자를 대체 문자로 바꿨습니다")
        return data.decode("utf-8", errors="replace")
    report.info(Codes.INPUT_ENCODING_FALLBACK, "입력이 UTF-8 이 아니어서 CP949(EUC-KR)로 읽었습니다")
    return text


def collect_note_definitions(text: str) -> dict[str, str]:
    """`[^label]: …` definitions (with 4-space-indented continuation lines) from raw text, outside fenced code."""
    notes: dict[str, list[str]] = {}
    current: list[str] | None = None
    fence: str | None = None
    for line in text.splitlines():
        if current is not None and fence is None and line.startswith(("    ", "\t")):
            # indented under a note: its own text, a fenced code block in it included
            current.append(line[4:] if line.startswith("    ") else line[1:])
            continue
        marker = _FENCE.match(line)
        if marker and fence in (None, marker.group(1)):
            fence = None if fence else marker.group(1)
            current = None
            continue
        if fence:
            continue
        definition = _NOTE_DEF.match(line)
        if definition:
            current = notes.setdefault(definition.group(1), [])
            current.append(definition.group(2))
        elif current is not None and not line.strip():
            current.append("")
        elif current and current[-1]:
            current.append(line)  # lazy continuation of the open paragraph
        else:
            current = None
    # blank lines go, but not the indentation of the first block (a code block when the label
    # stands on its own line)
    return {label: "\n".join(lines).lstrip("\n").rstrip() for label, lines in notes.items()}


def _note_blocks(definitions: dict[str, str], labels: set[str]) -> dict[str, list[pf.Block]]:
    wanted = [label for label in definitions if label in labels and definitions[label]]
    if not wanted:
        return {}
    # One pandoc call for all needed definitions: each body in its own fenced div.
    text = "\n".join(f"::: {{#n{i}}}\n{definitions[label]}\n:::\n" for i, label in enumerate(wanted))
    by_id = {d.identifier: list(d.content) for d in md_to_doc(text).content if isinstance(d, pf.Div)}
    return {label: by_id[f"n{i}"] for i, label in enumerate(wanted) if f"n{i}" in by_id}


def _link_notes(elem: pf.Element, notes: dict[str, list[pf.Block]]):
    if not isinstance(elem, pf.Str) or "[^" not in elem.text:
        return None
    out: list[pf.Inline] = []
    pos = 0
    for m in _NOTE_REF.finditer(elem.text):
        blocks = notes.get(m.group(1))
        if blocks is None:
            continue
        if m.start() > pos:
            out.append(pf.Str(elem.text[pos:m.start()]))
        out.append(pf.Note(*deepcopy(blocks)))
        pos = m.end()
    if not out:
        return None
    if pos < len(elem.text):
        out.append(pf.Str(elem.text[pos:]))
    return out


_MATH_SPAN = {"inline": (r"\(", r"\)", "InlineMath"), "display": (r"\[", r"\]", "DisplayMath")}


def _span_math(elem: pf.Element, _doc: pf.Doc):
    r"""``<span class="math inline">\(…\)</span>`` (``display``: ``\[…\]``) back to math."""
    if not isinstance(elem, pf.Span) or "math" not in elem.classes:
        return None
    kinds = [k for k in _MATH_SPAN if k in elem.classes]
    if len(kinds) != 1:
        return None
    start, end, fmt = _MATH_SPAN[kinds[0]]
    text = pf.stringify(elem)
    if len(text) < len(start + end) or not (text.startswith(start) and text.endswith(end)):
        return None
    return pf.Math(text[len(start):-len(end)], format=fmt)


def _column_alignment(elem: pf.Element, _doc: pf.Doc) -> None:
    """Column alignment from the body cells, not pandoc's first body row (a spanning cell there aligns
    every column it covers); a cell keeps only an alignment its columns do not already give it."""
    if not isinstance(elem, pf.Table):
        return
    rows = [r for body in elem.content for r in (*body.head, *body.content)]
    rows += list(elem.foot.content) if elem.foot else []
    cells = grid_cells(rows)
    colspec = list(elem.colspec)
    for col, (_, width) in enumerate(colspec):
        seen = [cell.alignment for cell, at in cells if at == col and cell.colspan == 1]
        if seen:
            colspec[col] = (Counter(seen).most_common(1)[0][0], width)
    elem.colspec = colspec
    for cell, at in cells:
        if {align for align, _ in colspec[at:at + max(1, cell.colspan)]} == {cell.alignment}:
            cell.alignment = "AlignDefault"


def expand_html_tables(doc: pf.Doc, definitions: dict[str, str] | None = None) -> pf.Doc:
    def is_table(elem: pf.Element) -> bool:
        return isinstance(elem, pf.RawBlock) and elem.format == "html" and bool(_TABLE_START.match(elem.text))

    labels: set[str] = set()
    if definitions:
        doc.walk(lambda e, d: labels.update(_NOTE_REF.findall(e.text)) if is_table(e) else None)
    notes = _note_blocks(definitions, labels) if labels else {}

    def action(elem: pf.Element, _doc: pf.Doc):
        if is_table(elem):
            blocks = [b.walk(_span_math).walk(_column_alignment) for b in html_to_blocks(elem.text)]
            if blocks and notes:
                blocks = [b.walk(lambda e, d: _link_notes(e, notes)) for b in blocks]
            if blocks:
                return blocks
        return None

    return doc.walk(action)


_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]+:")


def _decode_image_paths(doc: pf.Doc) -> pf.Doc:
    """A local image path is a file name: percent-decoded once here (``a%20b`` → ``a b``).

    pandoc percent-encodes spaces and ``<>`` in link destinations, and write_md encodes what
    would break the link. URLs with a scheme keep their encoding.
    """

    def action(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.Image) and "%" in elem.url and not _SCHEME.match(elem.url):
            elem.url = urllib.parse.unquote(elem.url)

    return doc.walk(action)


def _yaml_error_detail(exc: RuntimeError) -> str:
    lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
    return next((line for line in lines if "YAML" in line), lines[0] if lines else "")


def read_md(source: Source, report: Report) -> MdDocument:
    text = decode_text(source.data, report)
    try:
        doc = md_to_doc(text)
    except RuntimeError as exc:
        # Malformed frontmatter must not reject the document: drop the block and keep the body.
        block = _FRONTMATTER.match(text)
        if block is None:
            raise
        body = _decode_image_paths(
            expand_html_tables(md_to_doc(text[block.end():]), collect_note_definitions(text[block.end():]))
        )
        report.warn(
            Codes.FRONTMATTER_INVALID,
            f"frontmatter(YAML)를 해석할 수 없어 무시합니다: {_yaml_error_detail(exc)}",
        )
        return MdDocument(body, {})
    doc = _decode_image_paths(expand_html_tables(doc, collect_note_definitions(text)))
    meta = doc.get_metadata()
    return MdDocument(doc, dict(meta) if isinstance(meta, dict) else {})
