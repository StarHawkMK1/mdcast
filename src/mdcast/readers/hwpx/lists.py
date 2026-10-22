"""Group numbered and bulleted hwpx paragraphs into nested pandoc lists."""

from __future__ import annotations

from collections.abc import Iterable

import panflute as pf

from mdcast.readers.docx_package import PAGEBREAK_SENTINEL
from mdcast.readers.hwpx.package import ParaStyle

_LIST_KINDS = ("NUMBER", "BULLET")
_LISTS = (pf.OrderedList, pf.BulletList)


def is_sentinel(block: pf.Block) -> bool:
    return isinstance(block, pf.Para) and pf.stringify(block, newlines=False) == PAGEBREAK_SENTINEL


def _is_text(block: pf.Block) -> bool:
    """A Para or Plain the MD writer keeps as text (the page-break mark becomes a raw block)."""
    return isinstance(block, (pf.Para, pf.Plain)) and not is_sentinel(block)


class _Frame:
    """An open list while its paragraphs are grouped: its level and each item's blocks."""

    def __init__(self, level: int, start: int) -> None:
        self.level = level
        self.start = start
        self.items: list[list[pf.Block]] = []

    def to_list(self, kind: str) -> pf.Block:
        # pandoc writes a list tight only when every item starts with text and has no second block
        # besides its nested lists; tight items read back as Plain. Anything else (an item that is
        # a table or a page-break mark, or holds one after its text) makes it write the whole list
        # loose, which reads back as Para (ruling R6a)
        loose = any(
            not _is_text(item[0]) or sum(not isinstance(b, _LISTS) for b in item) > 1
            for item in self.items
        )
        text = pf.Para if loose else pf.Plain
        items = [
            pf.ListItem(
                *(text(*b.content) if isinstance(b, (pf.Para, pf.Plain)) else b for b in item)
            )
            for item in self.items
        ]
        if kind == "NUMBER":
            return pf.OrderedList(*items, start=self.start)
        return pf.BulletList(*items)


def _nest(kind: str, start: int, paras: list[tuple[int, list[pf.Block]]]) -> pf.Block:
    """One list from its paragraphs' (level, blocks): a deeper paragraph opens a list in the item before it.

    A level that skips one (0 → 2) nests one step only, and a later paragraph between the two
    levels joins that nested list; a paragraph shallower than the first one stays in the outer
    list. No paragraph moves or is dropped.
    """
    first = paras[0][0]
    stack = [_Frame(first, start if first == 0 else 1)]

    def close() -> None:
        done = stack.pop()
        stack[-1].items[-1].append(done.to_list(kind))

    for level, blocks in paras:
        while len(stack) > 1 and stack[-1].level > level:
            if stack[-2].level < level:
                stack[-1].level = level
                break
            close()
        if level > stack[-1].level:
            stack.append(_Frame(level, 1))
        elif level < stack[-1].level:  # only the outer list, shallower than where it began
            stack[-1].level = level
        stack[-1].items.append(blocks)
    while len(stack) > 1:
        close()
    return stack[0].to_list(kind)


def group_lists(
    paras: Iterable[tuple[ParaStyle, list[pf.Block]]], starts: dict[str, int]
) -> list[pf.Block]:
    """The blocks of sibling paragraphs, Hancom numbered and bulleted paragraphs grouped into lists.

    Paragraphs of one kind and ``list_id`` that follow each other are one list (spec §4.4); a
    paragraph without blocks is passed over, so an empty line does not split a list Hancom numbers
    on across. All of a paragraph's blocks go into its item, except a page break on a list's first
    paragraph, which goes before the list. A numbered list starts at its numbering's first number
    (``starts``); the number shape is dropped.
    """
    out: list[pf.Block] = []
    run: list[tuple[int, list[pf.Block]]] = []
    key: tuple[str, str | None] | None = None
    for style, blocks in paras:
        if not blocks:
            continue
        this = (style.kind, style.list_id) if style.kind in _LIST_KINDS else None
        if run and this != key:
            out.append(_nest(key[0], starts.get(key[1] or "", 1), run))
            run = []
        key = this
        if this is None:
            out.extend(blocks)
            continue
        if not run and is_sentinel(blocks[0]):
            out.append(blocks[0])
            blocks = blocks[1:]
        if blocks:
            run.append((style.level, blocks))
    if run:
        out.append(_nest(key[0], starts.get(key[1] or "", 1), run))
    return out
