"""Unwrap ``label | content`` form tables into a heading per label and its content as body (D17-D19).

The judgement is per table: every row must be a side-by-side ``label | content`` row or a full-width
label row followed by a full-width content row, else the table stays a table. Labels are short;
at least half of the non-empty contents must be long (paragraphs, lists, tables, pictures), so a
``name | short value`` table also stays, as does a table whose first row is bold column names.
"""

from __future__ import annotations

import panflute as pf

from mdcast.filters.importing.context import ImportContext
from mdcast.filters.importing.markers import list_marker
from mdcast.report import Codes

LABEL_MAX_CHARS = 40  # label: characters without whitespace
LONG_CHARS = 100  # long content: characters without whitespace
_MAX_LEVEL = 6
_RICH = (pf.Table, pf.Image, pf.BulletList, pf.OrderedList)
_OBJECTS = (pf.Table, pf.Image)
_BREAKS = (pf.LineBreak, pf.SoftBreak)

Row = tuple[str, pf.TableCell, "pf.TableCell | None"]


def _chars(elem: pf.Element) -> int:
    return len("".join(pf.stringify(elem).split()))


def _contains(elem: pf.Element, kinds: tuple[type, ...]) -> bool:
    found: list[pf.Element] = []
    elem.walk(lambda e, _d: found.append(e) if isinstance(e, kinds) else None)
    return bool(found)


def _all_strong(inlines: list[pf.Inline]) -> bool:
    """Every inline is bold; bold split over runs (``Strong Space Strong``) counts."""
    return any(isinstance(i, pf.Strong) for i in inlines) and all(
        isinstance(i, (pf.Strong, pf.Space)) for i in inlines
    )


def _is_label(cell: pf.TableCell, *, bold: bool) -> bool:
    blocks = list(cell.content)
    if (
        len(blocks) != 1
        or not isinstance(blocks[0], (pf.Plain, pf.Para))
        or _contains(cell, _OBJECTS)
    ):
        return False  # a picture's alt text ("그림") is not a label
    if not 1 <= _chars(cell) <= LABEL_MAX_CHARS:
        return False
    if list_marker(pf.stringify(cell).strip()) is not None:
        return False
    return not bold or _all_strong(list(blocks[0].content))


def _is_empty(cell: pf.TableCell) -> bool:
    return _chars(cell) == 0 and not _contains(cell, _OBJECTS)


def _is_long(cell: pf.TableCell) -> bool:
    return len(cell.content) >= 2 or _contains(cell, _RICH) or _chars(cell) >= LONG_CHARS


def _rows(table: pf.Table) -> list[pf.TableRow]:
    rows = list(table.head.content) if table.head else []
    for body in table.content:
        rows += list(body.head) + list(body.content)
    if table.foot:
        rows += list(table.foot.content)
    return rows


def _wide(row: pf.TableRow) -> pf.TableCell | None:
    cells = list(row.content)
    return cells[0] if len(cells) == 1 and cells[0].colspan == 2 else None


def classify(table: pf.Table) -> list[Row] | None:
    """Rows top to bottom as ("pair", label, content) or ("stack", label, content | None); None if not a form."""
    if len(table.colspec) != 2:
        return None
    rows = _rows(table)
    if any(c.rowspan > 1 for row in rows for c in row.content):
        return None
    plan: list[Row] = []
    i = 0
    while i < len(rows):
        cells = list(rows[i].content)
        label = _wide(rows[i])
        if (
            len(cells) == 2
            and all(c.colspan == 1 for c in cells)
            and _is_label(cells[0], bold=False)
        ):
            plan.append(("pair", cells[0], cells[1]))
            i += 1
        elif label is not None and _is_label(label, bold=True):
            if i + 1 == len(rows):
                plan.append(("stack", label, None))
                i += 1
            elif (content := _wide(rows[i + 1])) is not None:
                plan.append(("stack", label, content))
                i += 2
            else:
                return None
        else:
            return None
    if not plan:
        return None  # no rows
    kind, first_label, first_content = plan[0]
    if kind == "pair" and _is_label(first_label, bold=True) and _is_label(first_content, bold=True):
        return None  # column names over both columns: a grid with a header row (§5.1)
    contents = [c for _, _, c in plan if c is not None and not _is_empty(c)]
    if len(plan) < 2 or not contents:
        return None
    if 2 * sum(_is_long(c) for c in contents) < len(contents):
        return None
    return plan


def _heading(label: pf.TableCell, level: int) -> pf.Header:
    """The label as a heading: its bold dropped (it is a heading now), line breaks as spaces."""
    inlines = list(label.content[0].content)
    if _all_strong(inlines):
        inlines = [sub for i in inlines for sub in (i.content if isinstance(i, pf.Strong) else [i])]
    return pf.Header(*(pf.Space() if isinstance(i, _BREAKS) else i for i in inlines), level=level)


class _Unwrapper:
    def __init__(self) -> None:
        self.count = 0

    def expand(self, table: pf.Table, plan: list[Row], level: int) -> list[pf.Block]:
        self.count += 1
        out: list[pf.Block] = [
            pf.Para(*b.content) if isinstance(b, pf.Plain) else b for b in table.caption.content
        ]
        for _, label, content in plan:
            out.append(_heading(label, level))
            if content is not None:
                out.extend(self.content(list(content.content), level))
        return out

    def content(self, blocks: list[pf.Block], level: int) -> list[pf.Block]:
        out: list[pf.Block] = []
        below = min(level + 1, _MAX_LEVEL)
        for block in blocks:
            if isinstance(block, pf.Table) and (plan := classify(block)) is not None:
                out.extend(self.expand(block, plan, below))
                continue
            if (
                isinstance(block, (pf.Plain, pf.Para))
                and _chars(block) == 0
                and not _contains(block, _OBJECTS)
            ):
                continue  # an empty paragraph of an empty cell holds no text
            if isinstance(block, pf.Plain):
                block = pf.Para(*block.content)
            elif isinstance(block, pf.Header):
                block.level = min(max(block.level, below), _MAX_LEVEL)
            out.append(block)
        return out


def apply(doc: pf.Doc, ctx: ImportContext) -> pf.Doc:
    if ctx.generator:
        # an mdcast document's tables were written from MD tables, never forms; its header row's bold
        # is already gone (mdcast_doc), so the column-name guard could not see it (R21, D11)
        return doc
    unwrapper = _Unwrapper()
    out: list[pf.Block] = []
    above = 0  # level of the nearest heading the document had before this filter
    for block in doc.content:
        if isinstance(block, pf.Header):
            above = block.level
        if isinstance(block, pf.Table) and (plan := classify(block)) is not None:
            out.extend(unwrapper.expand(block, plan, min(above + 1, _MAX_LEVEL)))
        else:
            out.append(block)
    if unwrapper.count:
        doc.content = out
        ctx.report.info(
            Codes.IMPORT_TABLE_UNWRAPPED,
            f"서식 표 {unwrapper.count}개를 제목과 본문으로 풀었습니다",
        )
    return doc
