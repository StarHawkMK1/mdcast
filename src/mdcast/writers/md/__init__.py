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
# a line starting with ``:`` or ``~`` and a space is a definition in pandoc's markdown (read_md):
# the line before it would become the term
_DEFINITION_MARK = re.compile(r"[:~](?=\s|$)")


def _convert(doc: pf.Doc) -> str:
    return convert_doc(doc, GFM_FORMAT, extra_args=["--wrap=none", *QUIET]).replace("\r\n", "\n")


def _frontmatter(data: dict[str, Any]) -> str:
    picked = {k: data[k] for k in FRONTMATTER_KEYS if data.get(k) not in (None, "", [], {})}
    if not picked:
        return ""
    return "---\n" + yaml.safe_dump(picked, allow_unicode=True, sort_keys=False) + "---\n\n"


def _note_definition(label: str, note: pf.Note) -> str:
    """A cell note's ``[^label]:`` definition, written after the body (M3a D9).

    A note that starts with text has it on the label line. One that starts with anything else (a
    code block, a list, a table) has the label on a line of its own and every block indented under
    it: on the label line, a code block's indentation would be lost and it would read back as text.
    """
    blocks = [_convert(pf.Doc(deepcopy_block)).strip("\n") for deepcopy_block in note.content]
    first_text = not note.content or isinstance(note.content[0], (pf.Para, pf.Plain))
    lines: list[str] = [] if first_text else [f"[^{label}]:"]
    for i, text in enumerate(blocks):
        body = text.split("\n")
        if i == 0 and first_text:
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


_EDGE_BREAKS = (pf.LineBreak, pf.SoftBreak, pf.Space)
# inlines written between delimiter runs (``**``, ``*``, ``~~``): a run next to a break is not a delimiter
_DELIMITED = (pf.Emph, pf.Strong, pf.Strikeout)


def _breaks_outside(inlines: pf.ListContainer) -> None:
    """Move the breaks and spaces at either edge of emphasis to just before / after it.

    A run written as ``**a`` + hard break + ``**`` cannot close: pandoc reads the asterisks back as
    text and loses the emphasis and the break (a line starting ``: `` after it even becomes a
    definition).
    """
    out: list[pf.Inline] = []
    for elem in inlines:
        if not isinstance(elem, _DELIMITED):
            out.append(elem)
            continue
        content = list(elem.content)
        lead: list[pf.Inline] = []
        trail: list[pf.Inline] = []
        while content and isinstance(content[0], _EDGE_BREAKS):
            lead.append(content.pop(0))
        while content and isinstance(content[-1], _EDGE_BREAKS):
            trail.insert(0, content.pop())
        if lead or trail:
            elem.content = content
        out += [*lead, elem, *trail] if content else [*lead, *trail]
    inlines[:] = out


def _prepare(elem: pf.Element, _doc: pf.Doc):
    if isinstance(elem, pf.Figure):
        return _figure_blocks(elem)
    content = getattr(elem, "content", None)
    if isinstance(content, pf.ListContainer) and any(isinstance(e, _DELIMITED) for e in content):
        _breaks_outside(content)  # bottom-up: inner emphasis already gave its breaks to this one
    if isinstance(elem, pf.Image):
        if _SCHEME.match(elem.url):
            elem.url = elem.url.replace(" ", "%20")
        else:
            # a local path (e.g. 붙임1)계획_assets/…): read_md percent-decodes it back
            for char, code in _PATH_CODES:
                elem.url = elem.url.replace(char, code)
    return None


def _escape_line_starts(inlines: pf.ListContainer, at_start: bool) -> bool:
    """Escape a definition mark a line starts with; returns whether the next inline starts a line.

    Text in an inline that opens with a mark of its own (``**``, ``[``, ``<sup>``, …) is not at the
    start of a line; a Span without attributes is written as its bare content. A note's paragraphs
    are blocks of their own (walked by :func:`_line_starts`).
    """
    out: list[pf.Inline] = []
    for elem in inlines:
        if isinstance(elem, pf.LineBreak):
            at_start = True
        elif isinstance(elem, (pf.Space, pf.SoftBreak)):
            pass
        elif isinstance(elem, pf.Str) and at_start and _DEFINITION_MARK.match(elem.text):
            out.append(pf.RawInline("\\" + elem.text[0], "gfm"))
            elem.text = elem.text[1:]
            at_start = False
            if not elem.text:
                continue
        elif isinstance(elem, pf.Span):
            at_start = _escape_line_starts(elem.content, at_start)
        else:
            at_start = False
            if not isinstance(elem, pf.Note) and isinstance(getattr(elem, "content", None), pf.ListContainer):
                # a break at its end puts the next inline at the start of a line
                at_start = _escape_line_starts(elem.content, False)
        out.append(elem)
    inlines[:] = out
    return at_start


_SCRIPT_MARKS = "~^"  # ``~a~`` / ``^a^`` read back as subscript / superscript (pandoc's markdown)
_PAIR_ENDS = " \t\n"  # only these end such a pair: a no-break space does not
_RUN_ENDS = (pf.Space, pf.SoftBreak, pf.LineBreak)
_LITERAL = (pf.Code, pf.Math, pf.RawInline, pf.Note)  # no marks of their own to read; a note's blocks are walked apart


def _escape_pairs(inlines: pf.ListContainer) -> None:
    """Escape every ``~`` / ``^`` that a later one in the same unbroken run would pair with.

    A run is what lies between spaces and breaks; inlines inside it (bold, links, note marks) do
    not end it, as they do not end a pair. The last mark of a run is left as it is, so a lone
    ``~`` (``2026.1~2026.12``, ``10~20 %``) is written bare.
    """
    for elem in inlines:
        if not isinstance(elem, _LITERAL) and isinstance(getattr(elem, "content", None), pf.ListContainer):
            _escape_pairs(elem.content)
    marks: list[tuple[int, int, str]] = []  # (inline, character, mark) of the run so far
    escape: set[tuple[int, int]] = set()

    def end_run() -> None:
        for mark in _SCRIPT_MARKS:
            found = [(i, j) for i, j, m in marks if m == mark]
            escape.update(found[:-1])
        marks.clear()

    for i, elem in enumerate(inlines):
        if isinstance(elem, _RUN_ENDS):
            end_run()
        elif isinstance(elem, pf.Str):
            for j, char in enumerate(elem.text):
                if char in _PAIR_ENDS:
                    end_run()
                elif char in _SCRIPT_MARKS:
                    marks.append((i, j, char))
    end_run()
    if not escape:
        return
    out: list[pf.Inline] = []
    for i, elem in enumerate(inlines):
        cuts = sorted(j for k, j in escape if k == i)
        if not cuts:
            out.append(elem)
            continue
        start = 0
        for j in cuts:
            if j > start:
                out.append(pf.Str(elem.text[start:j]))
            out.append(pf.RawInline("\\" + elem.text[j], "gfm"))
            start = j + 1
        if start < len(elem.text):
            out.append(pf.Str(elem.text[start:]))
    inlines[:] = out


def _escape_block_pairs(elem: pf.Element, _doc: pf.Doc):
    if isinstance(elem, (pf.Para, pf.Plain, pf.Header)):
        _escape_pairs(elem.content)


def _line_starts(elem: pf.Element, _doc: pf.Doc):
    """Keep every block's lines what they are when read back (R7).

    A heading is one ATX line, so a hard break in it is written as a space; a paragraph line that
    starts with a definition mark gets the mark escaped. ``~`` / ``^`` pairs are escaped in both.
    """
    if isinstance(elem, pf.Header):
        elem.walk(lambda e, d: pf.Space() if isinstance(e, pf.LineBreak) else None)
        _escape_pairs(elem.content)
    elif isinstance(elem, (pf.Para, pf.Plain)):
        _escape_pairs(elem.content)
        _escape_line_starts(elem.content, True)


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
                # a pipe cell is markdown too, and its text is taken now: escape its pairs first
                elem.walk(_escape_block_pairs)
                return pf.RawBlock(table_to_pipe(elem, pipe_cells), "gfm")
            return pf.RawBlock(table_to_html(elem, note_label, html_cells), "html")
        return None

    def fill(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.RawBlock):
            elem.text = pipe_cells.fill(html_cells.fill(elem.text))

    doc = doc.walk(_prepare)
    doc = doc.walk(action, stop_if=lambda e: isinstance(e, pf.Table))
    # after the tables became raw HTML: a raw gfm escape inside an HTML cell would be dropped
    doc = doc.walk(_line_starts)
    for note in cell_notes:  # written as markdown after the body
        note.walk(_line_starts)
    html_cells.render()
    pipe_cells.render()
    doc = doc.walk(fill)
    for note in cell_notes:  # a table inside a cell note was written with placeholders too
        note.walk(fill)
    body = _convert(doc).rstrip("\n")
    definitions = [_note_definition(f"t{i}", n) for i, n in enumerate(cell_notes, 1)]
    if definitions:
        body += "\n\n" + "\n\n".join(definitions)
    return _frontmatter(frontmatter) + body + "\n"
