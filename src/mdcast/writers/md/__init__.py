from __future__ import annotations

import re
from typing import Any

import panflute as pf
import yaml

from mdcast.ast import QUIET, clone, convert_doc, copy_element
from mdcast.writers.md.tables import (
    html_batch,
    is_simple_table,
    pipe_batch,
    table_to_html,
    table_to_pipe,
)

GFM_FORMAT = "gfm+footnotes+tex_math_dollars-tex_math_gfm"
FRONTMATTER_KEYS = ("title", "author", "template")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]+:")  # as read_md: a drive letter is not a scheme
# characters that end or break a link destination; % first so the codes are not encoded again
_PATH_CODES = (("%", "%25"), (" ", "%20"), ("(", "%28"), (")", "%29"), ("<", "%3C"), (">", "%3E"))


def _convert(doc: pf.Doc) -> str:
    return convert_doc(doc, GFM_FORMAT, extra_args=["--wrap=none", *QUIET]).replace("\r\n", "\n")


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


def _caption_inlines(figure: pf.Figure) -> list[pf.Inline]:
    out: list[pf.Inline] = []
    for block in figure.caption.content if figure.caption else []:
        if isinstance(block, (pf.Plain, pf.Para)):
            out += list(block.content)
    return out


def _figure_blocks(figure: pf.Figure) -> list[pf.Block]:
    """A captioned figure becomes `![caption](path)`; extra content is kept as-is."""
    caption = _caption_inlines(figure)
    blocks = [copy_element(b) for b in figure.content]
    images: list[pf.Image] = []
    for block in blocks:
        block.walk(lambda e, d: images.append(e) if isinstance(e, pf.Image) else None)
    if caption and len(images) == 1:
        images[0].content = [copy_element(i) for i in caption]
    elif caption:
        blocks.append(pf.Para(*caption))
    return [pf.Para(*b.content) if isinstance(b, pf.Plain) else b for b in blocks]


def _prepare(elem: pf.Element, _doc: pf.Doc):
    if isinstance(elem, pf.Figure):
        return _figure_blocks(elem)
    if isinstance(elem, pf.Image):
        if _SCHEME.match(elem.url):
            elem.url = elem.url.replace(" ", "%20")
        else:
            # a local path (e.g. 붙임1)계획_assets/…): read_md percent-decodes it back
            for char, code in _PATH_CODES:
                elem.url = elem.url.replace(char, code)
    return None


def write_md(doc: pf.Doc, frontmatter: dict[str, Any]) -> str:
    doc = clone(doc)
    cell_notes: list[pf.Note] = []

    def note_label(note: pf.Note) -> str:
        cell_notes.append(note)
        return f"t{len(cell_notes)}"

    # every table cell of the document is rendered in one pandoc call per format, not one per cell
    html_cells, pipe_cells = html_batch(), pipe_batch()

    def action(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.Table):
            if is_simple_table(elem):
                return pf.RawBlock(table_to_pipe(elem, pipe_cells), "gfm")
            return pf.RawBlock(table_to_html(elem, note_label, html_cells), "html")
        return None

    def fill(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.RawBlock):
            elem.text = pipe_cells.fill(html_cells.fill(elem.text))

    doc = doc.walk(_prepare)
    doc = doc.walk(action, stop_if=lambda e: isinstance(e, pf.Table))
    html_cells.render()
    pipe_cells.render()
    doc = doc.walk(fill)
    body = _convert(doc).rstrip("\n")
    definitions = [_note_definition(f"t{i}", n) for i, n in enumerate(cell_notes, 1)]
    if definitions:
        body += "\n\n" + "\n\n".join(definitions)
    return _frontmatter(frontmatter) + body + "\n"
