from __future__ import annotations

import re

import panflute as pf

from mdcast.filters.importing.context import ImportContext
from mdcast.filters.importing.markers import heading_shape
from mdcast.report import Codes

_MAX_TEXT = 60
_MAX_TITLE = 40
_MAX_LEVEL = 6
_LEAD = re.compile(r"^(\d+)\.")
_DATE = re.compile(r"^\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?(?:\s|$)")  # 2026. 10. 21.


def _text(block: pf.Element) -> str:
    return pf.stringify(block).strip()


def _whole_strong(block: pf.Element) -> bool:
    return len(block.content) == 1 and isinstance(block.content[0], pf.Strong)


def _unwrap(header: pf.Header) -> None:
    if _whole_strong(header):
        header.content = list(header.content[0].content)


def _as_header(para: pf.Para, level: int) -> pf.Header:
    header = pf.Header(*para.content, level=level)
    _unwrap(header)
    return header


class _Levels:
    """Heading level per number shape; decimal is stored as the level of its one-dot form."""

    def __init__(self) -> None:
        self.bases: dict[str, int] = {}
        self.deepest = 0

    def seed(self, shape: tuple[str, int] | None, level: int) -> None:
        self.deepest = max(self.deepest, level)
        if shape is None:
            return
        key, dots = shape
        base = max(1, level - (dots - 1)) if key == "decimal" else level
        self.bases.setdefault(key, base)

    def level_for(self, shape: tuple[str, int]) -> int:
        key, dots = shape
        extra = dots - 1 if key == "decimal" else 0
        base = self.bases.get(key)
        if base is None:
            level = min(self.deepest + 1, _MAX_LEVEL)
            base = max(1, level - extra)
            self.bases[key] = base
        else:
            level = min(base + extra, _MAX_LEVEL)
        self.deepest = max(self.deepest, level)
        return level


def _lead(text: str) -> int | None:
    m = _LEAD.match(text)
    return int(m.group(1)) if m else None


def _is_candidate(block: pf.Element, section: int | None) -> tuple[str, int] | None:
    """Shape of a paragraph that reads as a heading: bold and numbered, or ``N.M …`` under ``N.``.

    ``section`` is the number of the ``N.`` heading the paragraph sits under. A number starting
    with 0 (``0.5 이하``) or shaped like a date (``2026. 10. 21.``) is never a heading.
    """
    if not isinstance(block, pf.Para):
        return None
    text = _text(block)
    shape = heading_shape(text)
    if shape is None or len(text) > _MAX_TEXT:
        return None
    if shape[0] == "decimal" and (text.startswith("0") or _DATE.match(text)):
        return None
    first_strong = bool(block.content) and isinstance(block.content[0], pf.Strong)
    if first_strong:
        return shape
    if shape[0] == "decimal" and shape[1] >= 2 and section is not None and _lead(text) == section:
        return shape
    return None


def _section(current: tuple[int, int] | None, header: pf.Header) -> tuple[int, int] | None:
    """(number, level) of the ``N.`` heading in force after ``header``."""
    text = _text(header)
    if heading_shape(text) == ("decimal", 1):
        number = _lead(text)
        return (number, header.level) if number is not None else None
    if current is not None and header.level <= current[1]:
        return None
    return current


def _promote_title(blocks: list[pf.Element], ctx: ImportContext) -> bool:
    first = next((i for i, b in enumerate(blocks) if isinstance(b, pf.Header)), None)
    if first is None:
        return False
    for i in range(first):
        block = blocks[i]
        if not isinstance(block, pf.Para) or not _whole_strong(block):
            continue
        text = _text(block)
        if len(text) > _MAX_TITLE or heading_shape(text) is not None:
            continue
        for other in blocks:
            if isinstance(other, pf.Header):
                other.level = min(other.level + 1, _MAX_LEVEL)
        blocks[i] = _as_header(block, 1)
        if not ctx.frontmatter.get("title"):
            ctx.frontmatter["title"] = text
        return True
    return False


def apply(doc: pf.Doc, ctx: ImportContext) -> pf.Doc:
    blocks = list(doc.content)
    levels = _Levels()
    for block in blocks:
        if isinstance(block, pf.Header):
            _unwrap(block)
            levels.seed(heading_shape(_text(block)), block.level)
    promoted = 0
    section: tuple[int, int] | None = None
    for i, block in enumerate(blocks):
        if isinstance(block, pf.Header):
            section = _section(section, block)
            continue
        shape = _is_candidate(block, section[0] if section else None)
        if shape:
            blocks[i] = _as_header(block, levels.level_for(shape))
            section = _section(section, blocks[i])
            promoted += 1
    if _promote_title(blocks, ctx):
        promoted += 1
    doc.content = blocks
    if promoted:
        ctx.report.info(Codes.IMPORT_HEADING_INFERRED, f"제목 {promoted}개를 번호 모양으로 추정했습니다")
    return doc
