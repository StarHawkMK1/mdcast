"""Fixture MD → docx → import → MD, compared after removing only the spec's allowed losses (M3a §5.4 b)."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import panflute as pf
import pytest
from helpers import export, write_template

from mdcast.pipeline import convert
from mdcast.readers.md import read_md
from mdcast.report import Codes, Level, Report
from mdcast.templates import resolve_template
from mdcast.types import Format, Options, Source

FIXTURES = Path(__file__).parent / "fixtures" / "md"
# kinds, numbering and a page-break rule: the export-added state Task 8 must take back out
RULED = """
name: ruled
headings:
  numbering: ["Ⅰ.", "1."]
layout:
  page_break:
    before: [h1]
tables:
  variants:
    plain: {header: {background: null}}
"""
_PAGEBREAK = "<!-- pagebreak -->"
_KIND = re.compile(r"^<!--\s*table\s*:\s*(\S+)\s*-->$")
_TEX_NOISE = re.compile(r"[\s{}]")


def _levels(before: Any) -> set[int]:
    return {int(str(v).lower().lstrip("h")) for v in before or []}


def _is_pagebreak(block: Any) -> bool:
    return block.get("t") == "RawBlock" and block["c"][1].strip() == _PAGEBREAK


def _kind(block: Any) -> str | None:
    if block.get("t") != "RawBlock":
        return None
    match = _KIND.match(block["c"][1].strip())
    return match.group(1) if match else None


def _blocks(items: list[Any], rule_levels: set[int], known_kinds: set[str] | None) -> list[Any]:
    out: list[Any] = []
    for i, item in enumerate(items):
        following = items[i + 1] if i + 1 < len(items) else None
        if _is_pagebreak(item) and following and following.get("t") == "Header" and following["c"][0] in rule_levels:
            continue  # frontmatter override / explicit + rule overlap: only the rule's break survives
        kind = _kind(item)
        if kind is not None and known_kinds is not None and kind not in known_kinds:
            continue  # the template had no such kind: docx keeps no trace of it
        if item.get("t") == "CodeBlock" and out and out[-1].get("t") == "CodeBlock":
            out[-1]["c"][1] += "\n" + item["c"][1]  # adjacent code blocks merge
            continue
        out.append(item)
    return out


def _node(node: Any, rule_levels: set[int], known_kinds: set[str] | None) -> Any:
    if isinstance(node, list):
        items = [_node(n, rule_levels, known_kinds) for n in node]
        if items and all(isinstance(n, dict) and "t" in n for n in items):
            items = _blocks(items, rule_levels, known_kinds)
        return items
    if not isinstance(node, dict) or "t" not in node:
        return node
    kind, c = node["t"], node.get("c")
    if kind == "SoftBreak":
        return {"t": "Space"}  # a source line wrap: the docx keeps only the space
    if kind == "Header":
        c[1] = ["", c[1][1], c[1][2]]  # identifier
    elif kind == "CodeBlock":
        c[0] = ["", [], []]  # language
    elif kind == "OrderedList":
        c[0] = [c[0][0], None, None]  # number shape; start number stays
    elif kind == "Math":
        c[1] = _TEX_NOISE.sub("", c[1])  # TeX re-serialised
    elif kind == "Image":
        c[0] = ["", [], []]  # width/height
        c[2] = [None, c[2][1]]  # path
    elif kind == "Table":
        c[2] = [[{"t": "AlignLeft"} if s[0]["t"] == "AlignDefault" else s[0], None] for s in c[2]]
        for row in c[3][1]:  # header cells come back Center
            for cell in row[1]:
                cell[1] = None
    if c is not None:
        node["c"] = _node(c, rule_levels, known_kinds)
    return node


def _math_as_code(node: Any) -> Any:
    if isinstance(node, list):
        return [_math_as_code(n) for n in node]
    if not isinstance(node, dict) or "t" not in node:
        return node
    if node["t"] == "Math":  # M3b §5.3 (b): hwpx keeps an equation only as its TeX in the code font
        return {"t": "Code", "c": [["", [], []], node["c"][1]]}
    if "c" in node:
        node["c"] = _math_as_code(node["c"])
    return node


def _deepest_item(bullets: Any) -> list:
    item = bullets["c"][-1]
    while item and item[-1].get("t") in ("BulletList", "OrderedList"):
        item = item[-1]["c"][-1] if item[-1]["t"] == "BulletList" else item[-1]["c"][1][-1]
    return item


def _fold_lists(blocks: list) -> list:
    out: list = []
    for block in blocks:
        if block.get("t") == "OrderedList" and out and out[-1].get("t") == "BulletList":
            # D22: the shared list filter nests a hand-marked numbered list that follows a
            # hand-marked bullet list under the bullet list's last, deepest item
            _deepest_item(out[-1]).append(block)
            continue
        out.append(block)
    return out


def normalize(
    doc: pf.Doc, *, rule_levels: set[int], known_kinds: set[str] | None = None, hwpx: bool = False
) -> list:
    """Block structure and text, with only M3a §5.4 (b) taken out (and M3b §5.3's for ``hwpx``).

    ``known_kinds`` None keeps every table-kind marker (the side that must not lose one).
    ``hwpx`` is for the original's side only.
    """
    blocks = json.loads(json.dumps(doc.to_json()))["blocks"]
    if hwpx:
        blocks = _fold_lists(_math_as_code(blocks))
    return _node(blocks, rule_levels, known_kinds)


def _front(meta: dict[str, Any]) -> dict[str, Any]:
    return {k: meta[k] for k in ("title", "author") if k in meta}


def _read(text: str, base: Path):
    return read_md(Source(text.encode("utf-8"), "a.md", Format.MD, base_dir=base), Report("a.md", Format.MD))


@pytest.mark.parametrize("template", [None, "ruled"])
@pytest.mark.parametrize("name", ["kitchen-sink.md", "korean-report.md"])
def test_docx_roundtrip_keeps_body(tmp_path, name, template):
    shutil.copytree(FIXTURES / "assets", tmp_path / "assets")
    if template:
        write_template(tmp_path / ".mdcast" / "templates", template, RULED)
    md = (FIXTURES / name).read_text(encoding="utf-8")
    original = _read(md, tmp_path)
    data = export(tmp_path, md, Format.DOCX, template)
    result = convert(
        Source(data, "x.docx", Format.DOCX), [Format.MD], options=Options(cwd=tmp_path, home=tmp_path / "home")
    )
    out = result.outputs[0]
    back = _read(out.data.decode("utf-8"), tmp_path)

    config = resolve_template(template, cwd=tmp_path, home=tmp_path / "home", report=Report("t", Format.MD)).config
    page_break = original.frontmatter.get("page_break") or {}
    rule_levels = _levels(page_break.get("before")) | _levels(config["layout"]["page_break"]["before"])
    known_kinds = set(config["tables"].get("variants") or {})

    assert normalize(back.doc, rule_levels=rule_levels) == normalize(
        original.doc, rule_levels=rule_levels, known_kinds=known_kinds
    )
    assert _front(back.frontmatter) == _front(original.frontmatter)
    assert back.frontmatter.get("template") == (template or "default")
    assert result.report.coverage == 1.0
    assert not [e for e in result.report.events if e.code == Codes.IMPORT_TABLE_UNWRAPPED]  # no form tables here


@pytest.mark.parametrize("template", [None, "ruled"])
@pytest.mark.parametrize("name", ["kitchen-sink.md", "korean-report.md"])
def test_hwpx_roundtrip_keeps_body(tmp_path, name, template):
    """The same check through hwpx, with only M3b §5.3's hwpx losses taken out as well."""
    shutil.copytree(FIXTURES / "assets", tmp_path / "assets")
    if template:
        write_template(tmp_path / ".mdcast" / "templates", template, RULED)
    md = (FIXTURES / name).read_text(encoding="utf-8")
    original = _read(md, tmp_path)
    data = export(tmp_path, md, Format.HWPX, template)
    result = convert(
        Source(data, "x.hwpx", Format.HWPX), [Format.MD], options=Options(cwd=tmp_path, home=tmp_path / "home")
    )
    out = result.outputs[0]
    back = _read(out.data.decode("utf-8"), tmp_path)

    config = resolve_template(template, cwd=tmp_path, home=tmp_path / "home", report=Report("t", Format.MD)).config
    page_break = original.frontmatter.get("page_break") or {}
    rule_levels = _levels(page_break.get("before")) | _levels(config["layout"]["page_break"]["before"])

    # M3b §5.3 (b): hwpx keeps no table kind (no style or name on hp:tbl, only borderFill ids)
    assert normalize(back.doc, rule_levels=rule_levels) == normalize(
        original.doc, rule_levels=rule_levels, known_kinds=set(), hwpx=True
    )
    assert _front(back.frontmatter) == _front(original.frontmatter)
    assert back.frontmatter.get("template") == (template or "default")
    assert result.report.coverage == 1.0
    assert not [e for e in result.report.events if e.code == Codes.IMPORT_TABLE_UNWRAPPED]  # no form tables here


def _counts(doc: pf.Doc) -> dict[str, Any]:
    """What the pdf round trip compares: h1·h2 (level, text), tables, merged cells, pictures."""
    out: dict[str, Any] = {"headings": [], "tables": 0, "rowspan": 0, "colspan": 0, "images": 0}

    def count(elem: pf.Element, _doc: pf.Doc) -> None:
        if isinstance(elem, pf.Header) and elem.level <= 2:  # h3 and below: M3c §5 allowed loss
            out["headings"].append((elem.level, pf.stringify(elem)))
        elif isinstance(elem, pf.Table):
            out["tables"] += 1
        elif isinstance(elem, pf.TableCell):
            out["rowspan"] += elem.rowspan > 1
            out["colspan"] += elem.colspan > 1
        elif isinstance(elem, pf.Image):
            out["images"] += 1

    doc.walk(count)
    return out


@pytest.mark.parametrize("name", ["kitchen-sink.md", "korean-report.md"])
def test_pdf_roundtrip_counts(tmp_path, name):
    """M3c §7: through pdf (built-in default) the body is not compared block by block, only by counts.

    Bold is not asserted: without 맑은 고딕 on the system the bundled variable Noto draws it, whose
    bold keeps no bold font name. Running headers are not asserted either: they are dropped only
    from 3 pages on (M3c §4.5), and the page count follows the fonts the system has.
    """
    shutil.copytree(FIXTURES / "assets", tmp_path / "assets")
    # the fixture's sample.png is 1×1 px, drawn at under 1pt: a decoration the reader drops by
    # design (M3c §4.6). A real-sized picture in its place checks that pictures come back.
    shutil.copy(FIXTURES / "assets" / "screen.png", tmp_path / "assets" / "sample.png")
    md = (FIXTURES / name).read_text(encoding="utf-8")
    original = _read(md, tmp_path)
    data = export(tmp_path, md, Format.PDF)
    result = convert(
        Source(data, "x.pdf", Format.PDF), [Format.MD], options=Options(cwd=tmp_path, home=tmp_path / "home")
    )
    out = result.outputs[0]
    (tmp_path / "x_assets").mkdir()
    for path, picture in out.assets.items():
        (tmp_path / path).write_bytes(picture)
    back = _read(out.data.decode("utf-8"), tmp_path)

    assert result.report.coverage == 1.0
    assert _counts(back.doc) == _counts(original.doc)
    assert back.frontmatter.get("template") == "default"
    assert _front(back.frontmatter) == _front(original.frontmatter)
    warned = {e.code for e in result.report.events if e.level is Level.WARN}
    assert not warned & {Codes.PDF_MULTICOLUMN_SUSPECTED, Codes.PDF_SCANNED_SUSPECTED, Codes.IMPORT_OBJECT_SKIPPED}


def _cells(doc: pf.Doc) -> list[str]:
    tables = [b for b in doc.content if isinstance(b, pf.Table)]
    assert len(tables) == 1
    out: list[str] = []
    tables[0].walk(lambda e, _d: out.append(pf.stringify(e).strip()) if isinstance(e, pf.TableCell) else None)
    return out


@pytest.mark.parametrize("target", [Format.DOCX, Format.HWPX])
def test_long_definition_table_comes_back_as_a_table(tmp_path, target):
    """R21: a 2-column MD table of terms and long definitions is not a form; its bold header is gone by the form filter."""
    rows = "\n".join(f"| {term} | {('뜻풀이 문장 ' * 32).strip()}{term} |" for term in ("가", "나", "다"))
    md = f"# 개요\n\n| 용어 | 정의 |\n|---|---|\n{rows}\n"
    original = _read(md, tmp_path)
    data = export(tmp_path, md, target)
    result = convert(
        Source(data, f"x.{target.value}", target), [Format.MD], options=Options(cwd=tmp_path, home=tmp_path / "home")
    )
    back = _read(result.outputs[0].data.decode("utf-8"), tmp_path)
    assert [type(b).__name__ for b in back.doc.content] == ["Header", "Table"]
    assert _cells(back.doc) == _cells(original.doc)
    assert result.report.coverage == 1.0
    assert not [e for e in result.report.events if e.code == Codes.IMPORT_TABLE_UNWRAPPED]
