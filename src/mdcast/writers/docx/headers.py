from __future__ import annotations

import copy
from collections.abc import Iterator
from typing import Any

from docx.enum.text import WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu
from docx.text.run import Run

from mdcast.fields import FIELD_RE, PageField, ResolvedFields, Text
from mdcast.writers.docx.xml import PPR_ORDER, upsert

_INSTR = {"page": " PAGE ", "pages": " NUMPAGES "}


def _set_text(run_element, paragraph, text: str) -> None:
    Run(run_element, paragraph).text = text


def page_field(kind: str, template_run=None):
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), _INSTR[kind])
    run = copy.deepcopy(template_run) if template_run is not None else OxmlElement("w:r")
    for child in list(run):
        if child.tag != qn("w:rPr"):
            run.remove(child)
    text = OxmlElement("w:t")
    text.text = "1"
    run.append(text)
    field.append(run)
    return field


def fill_placeholders(paragraph, fields: ResolvedFields) -> None:
    runs = paragraph.runs
    full = "".join(r.text for r in runs)
    matches = list(FIELD_RE.finditer(full))
    if not matches:
        return
    bounds: list[tuple[int, int]] = []
    pos = 0
    for run in runs:
        bounds.append((pos, pos + len(run.text)))
        pos += len(run.text)
    for match in reversed(matches):
        start, end = match.span()
        first = next(i for i, (a, b) in enumerate(bounds) if a <= start < b)
        last = next(i for i, (a, b) in enumerate(bounds) if a < end <= b)
        head = runs[first].text[: start - bounds[first][0]]
        tail = runs[last].text[end - bounds[last][0] :]
        for i in range(first + 1, last):
            runs[i].text = ""
        if first != last:
            runs[last].text = tail
            tail_in_first = ""
        else:
            tail_in_first = tail
        segments = fields.render(match.group(0))
        if all(isinstance(s, Text) for s in segments):
            runs[first].text = head + "".join(s.value for s in segments) + tail_in_first
            continue
        runs[first].text = head
        template_run = runs[first]._r
        anchor = template_run
        pieces = [*segments, *([Text(tail_in_first)] if tail_in_first else [])]
        for seg in pieces:
            if isinstance(seg, PageField):
                new = page_field(seg.kind, template_run)
            else:
                new = copy.deepcopy(template_run)
                _set_text(new, paragraph, seg.value)
            anchor.addnext(new)
            anchor = new


def _paragraphs(container) -> Iterator[Any]:
    yield from container.paragraphs
    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from _paragraphs(cell)


def _write_slots(part, spec: dict[str, Any], fields: ResolvedFields, section) -> None:
    element = part._element
    for child in list(element):
        element.remove(child)
    paragraph = part.add_paragraph()
    width = (section.page_width or 0) - (section.left_margin or 0) - (section.right_margin or 0)
    tabs = paragraph.paragraph_format.tab_stops
    tabs.add_tab_stop(Emu(width // 2), WD_TAB_ALIGNMENT.CENTER)
    tabs.add_tab_stop(Emu(width), WD_TAB_ALIGNMENT.RIGHT)
    for index, slot in enumerate(("left", "center", "right")):
        if index:
            paragraph.add_run("\t")
        for seg in fields.render(spec.get(slot) or ""):
            if isinstance(seg, PageField):
                paragraph._p.append(page_field(seg.kind))
            else:
                paragraph.add_run(seg.value)
    line = spec.get("line")
    if line in ("below", "above"):
        ppr = paragraph._p.get_or_add_pPr()
        borders = upsert(ppr, "w:pBdr", PPR_ORDER)
        side = "bottom" if line == "below" else "top"
        upsert(borders, f"w:{side}", ["top", "left", "bottom", "right"], val="single", sz=4, space=1, color="auto")


def _parts(section, kind: str):
    if kind == "header":
        return (section.header, section.first_page_header, section.even_page_header)
    return (section.footer, section.first_page_footer, section.even_page_footer)


def apply_headers(d, config: dict[str, Any], fields: ResolvedFields) -> None:
    specs = {kind: config.get(kind) or {} for kind in ("header", "footer")}
    yaml_sourced = {kind: spec.get("source") != "reference" for kind, spec in specs.items()}
    # titlePg is section-wide: switch it off only when no reference part relies on a first-page variant
    all_yaml = all(yaml_sourced.values())
    even_odd = d.settings.odd_and_even_pages_header_footer
    for section in d.sections:
        if all_yaml:
            section.different_first_page_header_footer = False
        for kind, spec in specs.items():
            primary, first, even = _parts(section, kind)
            if not yaml_sourced[kind]:
                for part in (primary, first, even):
                    if part.is_linked_to_previous:
                        continue
                    for paragraph in _paragraphs(part):
                        fill_placeholders(paragraph, fields)
                continue
            targets = [primary]
            if section.different_first_page_header_footer:
                targets.append(first)  # titlePg stays on for a reference part: keep yaml on page 1 too
            if even_odd:
                targets.append(even)
            for part in targets:
                part.is_linked_to_previous = False
                _write_slots(part, spec, fields, section)
