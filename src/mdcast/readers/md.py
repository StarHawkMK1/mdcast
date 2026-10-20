from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import panflute as pf

from mdcast.ast import html_to_blocks, md_to_doc
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
        elif current is not None and (line.startswith("    ") or line.startswith("\t")):
            current.append(line[4:] if line.startswith("    ") else line[1:])
        elif current is not None and not line.strip():
            current.append("")
        else:
            current = None
    return {label: "\n".join(lines).strip() for label, lines in notes.items()}


def _note_blocks(text: str) -> dict[str, list[pf.Block]]:
    return {label: list(md_to_doc(body).content) for label, body in collect_note_definitions(text).items() if body}


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


def expand_html_tables(doc: pf.Doc, notes: dict[str, list[pf.Block]] | None = None) -> pf.Doc:
    def action(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.RawBlock) and elem.format == "html" and _TABLE_START.match(elem.text):
            blocks = html_to_blocks(elem.text)
            if blocks and notes:
                blocks = [b.walk(lambda e, d: _link_notes(e, notes)) for b in blocks]
            if blocks:
                return blocks
        return None

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
        body = expand_html_tables(md_to_doc(text[block.end():]), _note_blocks(text[block.end():]))
        report.warn(
            Codes.FRONTMATTER_INVALID,
            f"frontmatter(YAML)를 해석할 수 없어 무시합니다: {_yaml_error_detail(exc)}",
        )
        return MdDocument(body, {})
    doc = expand_html_tables(doc, _note_blocks(text))
    meta = doc.get_metadata()
    return MdDocument(doc, dict(meta) if isinstance(meta, dict) else {})
