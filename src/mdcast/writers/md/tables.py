from __future__ import annotations

import html
import re
import secrets
from collections.abc import Callable

import panflute as pf

from mdcast.ast import QUIET, convert_doc, copy_element, grid_cells

PIPE_CELL_FORMAT = "gfm+tex_math_dollars-tex_math_gfm"
_TAG = re.compile(r"<[A-Za-z][^<>]*>")
# the math class is kept: read_md turns <span class="math inline|display"> back into math
_NOISE_ATTR = re.compile(r'\s(?:style|width|height|id)="[^"]*"|\sclass="(?!math (?:inline|display)")[^"]*"')
_MATH_SPAN = {"InlineMath": ("inline", r"\(", r"\)"), "DisplayMath": ("display", r"\[", r"\]")}
# pandoc's HTML writer puts U+FE0E (text presentation) after these unless one already follows,
# so ``↔`` would come back as ``↔\ufe0e``: they are kept away from pandoc and put back afterwards
_HTML_VARIATION_CHARS = "\u2194\u21a9"  # ↔ ↩


def _has_line_break(cell: pf.TableCell) -> bool:
    found: list[bool] = []
    cell.walk(lambda e, d: found.append(True) if isinstance(e, pf.LineBreak) else None)
    return bool(found)


def _has_note(cell: pf.TableCell) -> bool:
    found: list[bool] = []
    cell.walk(lambda e, d: found.append(True) if isinstance(e, pf.Note) else None)
    return bool(found)


def _has_pipe(cell: pf.TableCell) -> bool:
    found: list[bool] = []

    def look(e: pf.Element, _d: pf.Doc) -> None:
        for attr in ("text", "url"):
            if "|" in (getattr(e, attr, "") or ""):
                found.append(True)

    cell.walk(look)
    return bool(found)


def _rows(table: pf.Table) -> list[pf.TableRow]:
    rows = list(table.head.content) if table.head else []
    for body in table.content:
        rows += list(body.head) + list(body.content)
    if table.foot:
        rows += list(table.foot.content)
    return rows


def is_simple_table(table: pf.Table) -> bool:
    if table.caption and table.caption.content:
        return False
    if table.head is None or not table.head.content:
        return False  # pipe tables need a header row
    if len(table.head.content) != 1:
        return False
    for row in _rows(table):
        for cell in row.content:
            if cell.rowspan != 1 or cell.colspan != 1 or len(cell.content) > 1:
                return False
            if any(not isinstance(b, (pf.Plain, pf.Para)) for b in cell.content):
                return False
            if _has_line_break(cell) or _has_note(cell) or _has_pipe(cell):
                return False
    return True


def _clean(html: str) -> str:
    return _TAG.sub(lambda m: _NOISE_ATTR.sub("", m.group(0)), html.replace("\r\n", "\n")).strip()


def _squeeze(text: str) -> str:
    return " ".join(text.split())


class CellBatch:
    """Cell contents queued for one pandoc call instead of one call per cell.

    ``add`` returns a placeholder (an HTML comment) to put where the cell's text goes; ``render``
    converts every queued cell at once (split apart again at separator comments) and ``fill``
    swaps the placeholders for the rendered text, also inside rendered cells (nested tables).
    """

    def __init__(self, to: str, finish: Callable[[str], str], shield: str = "") -> None:
        self._to = to
        self._finish = finish
        self._shield = shield  # characters pandoc must not see: each goes as a token and comes back
        self._jobs: list[list[pf.Block]] = []
        self._texts: list[str] = []
        self._mark = f"mdcast-cell-{secrets.token_hex(6)}"
        self._slot = re.compile(rf"<!--{self._mark}-(\d+)-->")

    def add(self, blocks: list[pf.Block]) -> str:
        self._jobs.append(blocks)
        return f"<!--{self._mark}-{len(self._jobs) - 1}-->"

    def render(self) -> None:
        if not self._jobs:
            return
        separator = f"<!--{self._mark}-->"
        content: list[pf.Block] = []
        for i, job in enumerate(self._jobs):
            if i:
                content.append(pf.RawBlock(separator, "html"))
            content += job
        if self._shield:
            for block in content:
                block.walk(self._hide)
        text = convert_doc(pf.Doc(*content), self._to, extra_args=["--wrap=none", *QUIET])
        if self._shield:
            text = re.sub(rf"{self._mark}x([0-9a-f]+)x", lambda m: chr(int(m.group(1), 16)), text)
        parts = text.split(separator)
        if len(parts) != len(self._jobs):
            raise RuntimeError(f"표 칸 {len(self._jobs)}개를 나누지 못했습니다 ({len(parts)}조각)")
        self._texts = [self._finish(part) for part in parts]

    def _hide(self, elem: pf.Element, _doc: pf.Doc) -> None:
        if isinstance(elem, (pf.Str, pf.Code, pf.CodeBlock)):
            for ch in self._shield:
                elem.text = elem.text.replace(ch, f"{self._mark}x{ord(ch):x}x")

    def fill(self, text: str) -> str:
        return self._slot.sub(lambda m: self.fill(self._texts[int(m.group(1))]), text)


def html_batch() -> CellBatch:
    return CellBatch("html", _clean, shield=_HTML_VARIATION_CHARS)


def pipe_batch() -> CellBatch:
    return CellBatch(PIPE_CELL_FORMAT, _squeeze)


def _math_html(elem: pf.Element, _doc: pf.Doc):
    """TeX kept as TeX: pandoc's HTML writer would draw it with tags that read back as plain text."""
    if isinstance(elem, pf.Math):
        kind, start, end = _MATH_SPAN.get(elem.format, _MATH_SPAN["InlineMath"])
        return pf.RawInline(f'<span class="math {kind}">{html.escape(start + elem.text + end, quote=False)}</span>', "html")
    return None


def _blocks_html(blocks: list[pf.Block], note_label: Callable[[pf.Note], str], batch: CellBatch) -> str:
    # math in a note stays math: the note is written as markdown after the table
    stop = (pf.Note, pf.Table)
    blocks = [copy_element(b).walk(_math_html, stop_if=lambda e: isinstance(e, stop)) for b in blocks]

    def action(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.Table):
            return pf.RawBlock(table_to_html(elem, note_label, batch), "html")
        if isinstance(elem, pf.Note):
            return pf.Str(f"[^{note_label(elem)}]")
        return None

    return batch.add([b.walk(action, stop_if=lambda e: isinstance(e, pf.Table)) for b in blocks])


def _cell_html(
    cell: pf.TableCell, tag: str, note_label: Callable[[pf.Note], str], batch: CellBatch, align: str | None = None
) -> str:
    attrs = ""
    if cell.rowspan > 1:
        attrs += f' rowspan="{cell.rowspan}"'
    if cell.colspan > 1:
        attrs += f' colspan="{cell.colspan}"'
    if align:
        attrs += f' align="{align}"'
    return f"<{tag}{attrs}>{_blocks_html(list(cell.content), note_label, batch)}</{tag}>"


def _row_html(row: pf.TableRow, tag: str, note_label: Callable[[pf.Note], str], batch: CellBatch) -> str:
    cells = "".join(_cell_html(c, tag, note_label, batch) for c in row.content)
    return f"<tr>{cells}</tr>"


_HTML_ALIGN = {"AlignLeft": "left", "AlignCenter": "center", "AlignRight": "right"}


def _column_align(table: pf.Table, col: int, span: int) -> str | None:
    """The alignment of the columns a cell covers, when they share one."""
    found = {align for align, _ in table.colspec[col:col + span]}
    return _HTML_ALIGN.get(found.pop()) if len(found) == 1 else None


def _body_html(table: pf.Table, rows: list[pf.TableRow], note_label: Callable[[pf.Note], str], batch: CellBatch) -> list[str]:
    """Body rows with the column alignment on every cell: pandoc's HTML reader reads it there, not from th or col."""
    starts = {id(cell): col for cell, col in grid_cells(rows)}
    out = []
    for row in rows:
        cells = "".join(
            _cell_html(c, "td", note_label, batch, _column_align(table, starts[id(c)], max(1, c.colspan)))
            for c in row.content
        )
        out.append(f"<tr>{cells}</tr>")
    return out


def table_to_html(table: pf.Table, note_label: Callable[[pf.Note], str], batch: CellBatch) -> str:
    """The table as clean HTML with a placeholder per cell: ``batch.fill`` it after ``batch.render``."""
    out = ["<table>"]
    if table.caption and table.caption.content:
        caption = list(table.caption.content)
        if len(caption) == 1 and isinstance(caption[0], pf.Para):
            # one paragraph is written bare, so it reads back as Plain like a `Table:` caption
            caption = [pf.Plain(*[copy_element(i) for i in caption[0].content])]
        out.append(f"<caption>{_blocks_html(caption, note_label, batch)}</caption>")
    if table.head and table.head.content:
        out.append("<thead>")
        out += [_row_html(r, "th", note_label, batch) for r in table.head.content]
        out.append("</thead>")
    body_rows = _rows(table)[len(table.head.content) if table.head else 0:]
    if body_rows:
        out.append("<tbody>")
        out += _body_html(table, body_rows, note_label, batch)
        out.append("</tbody>")
    out.append("</table>")
    return "\n".join(out)


_PIPE_RULE = {
    "AlignLeft": ":---",
    "AlignCenter": ":---:",
    "AlignRight": "---:",
    "AlignDefault": "---",
}


def _pipe_cell(cell: pf.TableCell, batch: CellBatch) -> str:
    if not cell.content:
        return ""
    return batch.add([copy_element(cell.content[0])])


def table_to_pipe(table: pf.Table, batch: CellBatch) -> str:
    """The table as a pipe table with a placeholder per cell: ``batch.fill`` it after ``batch.render``."""
    head = list(table.head.content[0].content)
    rule = [_PIPE_RULE.get(spec[0], "---") for spec in table.colspec]
    rule += ["---"] * (len(head) - len(rule))
    lines = ["| " + " | ".join(_pipe_cell(c, batch) for c in head) + " |", "| " + " | ".join(rule) + " |"]
    for row in _rows(table)[1:]:
        lines.append("| " + " | ".join(_pipe_cell(c, batch) for c in row.content) + " |")
    return "\n".join(lines)
