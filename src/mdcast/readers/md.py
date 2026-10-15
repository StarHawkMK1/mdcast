from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import panflute as pf

from mdcast.ast import html_to_blocks, md_to_doc
from mdcast.report import Codes, Report
from mdcast.types import Source

_TABLE_START = re.compile(r"^\s*<table[\s>]", re.IGNORECASE)


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


def expand_html_tables(doc: pf.Doc) -> pf.Doc:
    def action(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.RawBlock) and elem.format == "html" and _TABLE_START.match(elem.text):
            blocks = html_to_blocks(elem.text)
            if blocks:
                return blocks
        return None

    return doc.walk(action)


def read_md(source: Source, report: Report) -> MdDocument:
    text = decode_text(source.data, report)
    doc = expand_html_tables(md_to_doc(text))
    meta = doc.get_metadata()
    return MdDocument(doc, dict(meta) if isinstance(meta, dict) else {})
