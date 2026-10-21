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
from mdcast.report import Report
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


def normalize(doc: pf.Doc, *, rule_levels: set[int], known_kinds: set[str] | None = None) -> list:
    """Block structure and text, with only M3a §5.4 (b) taken out.

    ``known_kinds`` None keeps every table-kind marker (the side that must not lose one).
    """
    blocks = json.loads(json.dumps(doc.to_json()))["blocks"]
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
