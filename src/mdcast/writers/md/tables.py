from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy

import panflute as pf

from mdcast.ast import convert_doc

_TAG = re.compile(r"<[A-Za-z][^<>]*>")
_NOISE_ATTR = re.compile(r'\s(?:style|class|width|height|id)="[^"]*"')


def _has_line_break(cell: pf.TableCell) -> bool:
    found: list[bool] = []
    cell.walk(lambda e, d: found.append(True) if isinstance(e, pf.LineBreak) else None)
    return bool(found)


def _has_note(cell: pf.TableCell) -> bool:
    found: list[bool] = []
    cell.walk(lambda e, d: found.append(True) if isinstance(e, pf.Note) else None)
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
            if _has_line_break(cell) or _has_note(cell):
                return False
    return True


def _clean(html: str) -> str:
    return _TAG.sub(lambda m: _NOISE_ATTR.sub("", m.group(0)), html.replace("\r\n", "\n")).strip()


def _blocks_html(blocks: list[pf.Block], note_label: Callable[[pf.Note], str]) -> str:
    blocks = [deepcopy(b) for b in blocks]

    def action(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.Table):
            return pf.RawBlock(table_to_html(elem, note_label), "html")
        if isinstance(elem, pf.Note):
            return pf.Str(f"[^{note_label(elem)}]")
        return None

    walked = [b.walk(action, stop_if=lambda e: isinstance(e, pf.Table)) for b in blocks]
    html = convert_doc(pf.Doc(*walked), "html", extra_args=["--wrap=none"])
    return _clean(html)


def _cell_html(cell: pf.TableCell, tag: str, note_label: Callable[[pf.Note], str]) -> str:
    attrs = ""
    if cell.rowspan > 1:
        attrs += f' rowspan="{cell.rowspan}"'
    if cell.colspan > 1:
        attrs += f' colspan="{cell.colspan}"'
    return f"<{tag}{attrs}>{_blocks_html(list(cell.content), note_label)}</{tag}>"


def _row_html(row: pf.TableRow, tag: str, note_label: Callable[[pf.Note], str]) -> str:
    cells = "".join(_cell_html(c, tag, note_label) for c in row.content)
    return f"<tr>{cells}</tr>"


def table_to_html(table: pf.Table, note_label: Callable[[pf.Note], str]) -> str:
    out = ["<table>"]
    if table.caption and table.caption.content:
        out.append(f"<caption>{_blocks_html(list(table.caption.content), note_label)}</caption>")
    if table.head and table.head.content:
        out.append("<thead>")
        out += [_row_html(r, "th", note_label) for r in table.head.content]
        out.append("</thead>")
    body_rows = _rows(table)[len(table.head.content) if table.head else 0:]
    if body_rows:
        out.append("<tbody>")
        out += [_row_html(r, "td", note_label) for r in body_rows]
        out.append("</tbody>")
    out.append("</table>")
    return "\n".join(out)


_PIPE_RULE = {
    "AlignLeft": ":---",
    "AlignCenter": ":---:",
    "AlignRight": "---:",
    "AlignDefault": "---",
}


def _pipe_cell(cell: pf.TableCell) -> str:
    if not cell.content:
        return ""
    text = convert_doc(pf.Doc(deepcopy(cell.content[0])), "gfm+tex_math_dollars-tex_math_gfm", extra_args=["--wrap=none"])
    return " ".join(text.split()).replace("|", "\\|")


def table_to_pipe(table: pf.Table) -> str:
    head = list(table.head.content[0].content)
    rule = [_PIPE_RULE.get(spec[0], "---") for spec in table.colspec]
    rule += ["---"] * (len(head) - len(rule))
    lines = ["| " + " | ".join(_pipe_cell(c) for c in head) + " |", "| " + " | ".join(rule) + " |"]
    for row in _rows(table)[1:]:
        lines.append("| " + " | ".join(_pipe_cell(c) for c in row.content) + " |")
    return "\n".join(lines)
