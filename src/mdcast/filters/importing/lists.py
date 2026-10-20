from __future__ import annotations

import re
from dataclasses import dataclass, field

import panflute as pf

from mdcast.filters.importing.context import ImportContext
from mdcast.filters.importing.markers import match_list_marker
from mdcast.report import Codes

_CONTAINERS = (pf.Doc, pf.Div, pf.BlockQuote, pf.TableCell, pf.Note)


@dataclass
class _Marker:
    key: str
    kind: str
    number: int | None
    pattern: re.Pattern[str]


@dataclass
class _Chunk:
    container: pf.Element
    start: int
    end: int
    merge: pf.OrderedList | None = None
    markers: list[_Marker] = field(default_factory=list)


def _marker(block: pf.Element) -> _Marker | None:
    if not isinstance(block, (pf.Para, pf.Plain)) or len(block.content) < 3:
        return None
    first, second = block.content[0], block.content[1]
    if not isinstance(first, pf.Str) or not isinstance(second, pf.Space):
        return None
    found = match_list_marker(first.text + " ")
    return _Marker(*found) if found else None


def _plan(container: pf.Element) -> list[_Chunk]:
    blocks = list(container.content)
    marks = [_marker(b) for b in blocks]
    chunks: list[_Chunk] = []
    i = 0
    while i < len(blocks):
        if marks[i] is None:
            i += 1
            continue
        run_end = i
        while run_end + 1 < len(blocks) and marks[run_end + 1] is not None:
            run_end += 1
        prev = blocks[i - 1] if i else None
        first = marks[i]
        if (
            isinstance(prev, pf.OrderedList)
            and first.kind == "ordered"
            and first.number == prev.start + len(prev.content)
        ):
            end = max(j for j in range(i, run_end + 1) if marks[j].key == first.key)
            chunks.append(_Chunk(container, i, end, merge=prev))
        elif run_end > i:
            end = run_end
            chunks.append(_Chunk(container, i, end))
        else:
            i += 1
            continue
        chunks[-1].markers = [marks[j] for j in range(i, end + 1)]
        i = end + 1
    return chunks


def _containers(elem: pf.Element):
    if isinstance(elem, pf.ListItem):
        return
    if isinstance(elem, _CONTAINERS):
        yield elem
    for name in elem._children:
        child = getattr(elem, name)
        if isinstance(child, pf.Element):
            yield from _containers(child)
        elif child is not None:
            for sub in child:
                yield from _containers(sub)


def _levels(chunk: _Chunk, ranks: dict[str, int]) -> list[int]:
    rs = [ranks[m.key] for m in chunk.markers]
    base = rs[0] if chunk.merge is not None else min(rs)
    levels: list[int] = []
    for m, r in zip(chunk.markers, rs):
        if not levels:
            levels.append(1)
            continue
        floor = 2 if chunk.merge is not None and m.key != chunk.markers[0].key else 1
        levels.append(min(max(r - base + 1, floor), levels[-1] + 1))
    return levels


class _Frame:
    def __init__(self, marker: _Marker) -> None:
        self.kind = marker.kind
        self.start = marker.number or 1
        self.items: list[pf.ListItem] = []

    def to_list(self) -> pf.Element:
        if self.kind == "ordered":
            return pf.OrderedList(*self.items, start=self.start)
        return pf.BulletList(*self.items)


def _build(chunk: _Chunk, blocks: list[pf.Element], levels: list[int]) -> list[pf.ListItem] | pf.Element:
    stack: list[_Frame] = []

    def close() -> None:
        done = stack.pop().to_list()
        stack[-1].items[-1].content.append(done)

    block_type = pf.Plain
    if chunk.merge is not None:
        head = chunk.merge.content[0].content
        block_type = type(head[0]) if head and isinstance(head[0], (pf.Para, pf.Plain)) else pf.Plain
    for marker, block, level in zip(chunk.markers, blocks, levels):
        while len(stack) > level:
            close()
        if len(stack) < level:
            stack.append(_Frame(marker))
        inlines = list(block.content)[2:]
        stack[-1].items.append(pf.ListItem(block_type(*inlines)))
    while len(stack) > 1:
        close()
    top = stack[0]
    return top.items if chunk.merge is not None else top.to_list()


def apply(doc: pf.Doc, ctx: ImportContext) -> pf.Doc:
    plans = [(c, _plan(c)) for c in _containers(doc)]
    ranks: dict[str, int] = {}
    for _, chunks in plans:
        for chunk in chunks:
            for m in chunk.markers:
                ranks.setdefault(m.key, len(ranks))
    converted = 0
    for container, chunks in plans:
        if not chunks:
            continue
        blocks = list(container.content)
        out: list[pf.Element] = []
        pos = 0
        for chunk in chunks:
            out.extend(blocks[pos:chunk.start])
            built = _build(chunk, blocks[chunk.start:chunk.end + 1], _levels(chunk, ranks))
            if chunk.merge is not None:
                chunk.merge.content.extend(built)
            else:
                out.append(built)
            for m in chunk.markers:
                if m.pattern not in ctx.prefixes:
                    ctx.prefixes.append(m.pattern)
            converted += len(chunk.markers)
            pos = chunk.end + 1
        out.extend(blocks[pos:])
        container.content = out
    if converted:
        ctx.report.info(Codes.IMPORT_LIST_INFERRED, f"목록 문단 {converted}개를 목록으로 추정했습니다")
    return doc
