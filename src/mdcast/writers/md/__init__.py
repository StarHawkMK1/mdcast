from __future__ import annotations

from typing import Any

import panflute as pf
import yaml

from mdcast.ast import clone, convert_doc
from mdcast.writers.md.tables import is_simple_table, table_to_html, table_to_pipe

GFM_FORMAT = "gfm+footnotes+tex_math_dollars-tex_math_gfm"
FRONTMATTER_KEYS = ("title", "author", "template")


def _convert(doc: pf.Doc) -> str:
    return convert_doc(doc, GFM_FORMAT, extra_args=["--wrap=none"]).replace("\r\n", "\n")


def _frontmatter(data: dict[str, Any]) -> str:
    picked = {k: data[k] for k in FRONTMATTER_KEYS if data.get(k) not in (None, "", [], {})}
    if not picked:
        return ""
    return "---\n" + yaml.safe_dump(picked, allow_unicode=True, sort_keys=False) + "---\n\n"


def _note_definition(label: str, note: pf.Note) -> str:
    blocks = [_convert(pf.Doc(deepcopy_block)).strip("\n") for deepcopy_block in note.content]
    lines: list[str] = []
    for i, text in enumerate(blocks):
        body = text.split("\n")
        if i == 0:
            lines.append(f"[^{label}]: {body[0]}")
            lines += [f"    {line}" if line else "" for line in body[1:]]
        else:
            lines.append("")
            lines += [f"    {line}" if line else "" for line in body]
    return "\n".join(lines)


def write_md(doc: pf.Doc, frontmatter: dict[str, Any]) -> str:
    doc = clone(doc)
    cell_notes: list[pf.Note] = []

    def note_label(note: pf.Note) -> str:
        cell_notes.append(note)
        return f"t{len(cell_notes)}"

    def action(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.Table):
            if is_simple_table(elem):
                return pf.RawBlock(table_to_pipe(elem), "gfm")
            return pf.RawBlock(table_to_html(elem, note_label), "html")
        if isinstance(elem, pf.Image) and " " in elem.url:
            elem.url = elem.url.replace(" ", "%20")  # read_md decodes %20 back to a space
        return None

    doc = doc.walk(action, stop_if=lambda e: isinstance(e, pf.Table))
    body = _convert(doc).rstrip("\n")
    definitions = [_note_definition(f"t{i}", n) for i, n in enumerate(cell_notes, 1)]
    if definitions:
        body += "\n\n" + "\n\n".join(definitions)
    return _frontmatter(frontmatter) + body + "\n"
