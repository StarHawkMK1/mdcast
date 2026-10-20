from __future__ import annotations

import panflute as pf

from mdcast.filters.importing.context import ImportContext
from mdcast.filters.importing.markers import heading_shape
from mdcast.report import Codes

_MAX_TEXT = 60
_MAX_TITLE = 40
_MAX_LEVEL = 6


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

    def seed(self, shape: tuple[str, int], level: int) -> None:
        key, dots = shape
        base = max(1, level - (dots - 1)) if key == "decimal" else level
        self.bases.setdefault(key, base)
        self.deepest = max(self.deepest, level)

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


def _is_candidate(block: pf.Element) -> tuple[str, int] | None:
    if not isinstance(block, pf.Para):
        return None
    text = _text(block)
    shape = heading_shape(text)
    if shape is None or len(text) > _MAX_TEXT:
        return None
    first_strong = bool(block.content) and isinstance(block.content[0], pf.Strong)
    if first_strong or (shape[0] == "decimal" and shape[1] >= 2):
        return shape
    return None


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
            shape = heading_shape(_text(block))
            if shape:
                levels.seed(shape, block.level)
    promoted = 0
    for i, block in enumerate(blocks):
        shape = _is_candidate(block)
        if shape:
            blocks[i] = _as_header(block, levels.level_for(shape))
            promoted += 1
    if _promote_title(blocks, ctx):
        promoted += 1
    doc.content = blocks
    if promoted:
        ctx.report.info(Codes.IMPORT_HEADING_INFERRED, f"제목 {promoted}개를 번호 모양으로 추정했습니다")
    if not any(isinstance(b, pf.Header) for b in blocks):
        ctx.report.warn(Codes.IMPORT_HEADING_INFERRED, "제목을 찾지 못했습니다. 제목 단계 없이 가져옵니다", once=True)
    return doc
