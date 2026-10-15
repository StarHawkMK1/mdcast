from pathlib import Path

import pytest

from mdcast import pipeline
from mdcast.report import Codes
from mdcast.types import Format, Options, Source

FIXTURES = Path(__file__).parent / "fixtures" / "md"
KITCHEN = FIXTURES / "kitchen-sink.md"
EDGE = FIXTURES / "edge-cases.md"

# case -> (template yaml, extra template files, expected code or None when output alone is the contract)
CASES = {
    "broken-yaml": ("page: [unclosed", {}, Codes.TEMPLATE_INVALID),
    "wrong-types": ("page: A4\nlists: {bullet: '□'}\ntables: 3\n", {}, Codes.TEMPLATE_INVALID),
    "bad-values": (
        "page: {size: A9, margin: {top: 2px}}\nelements: {heading1: {color: navy, size: big}}\nlists: {ordered: ['※']}\n",
        {},
        Codes.TEMPLATE_INVALID,
    ),
    "unknown-keys": ("foo: 1\nelements: {heading1: {shadow: true}}\n", {}, Codes.TEMPLATE_INVALID),
    "missing-parent": ("name: x\nextends: ghost\n", {}, Codes.TEMPLATE_NOT_FOUND),
    "self-extends": ("name: self-extends\nextends: self-extends\n", {}, Codes.TEMPLATE_INVALID),
    "bad-reference-docx": ("name: x\n", {"reference.docx": b"not a zip"}, Codes.TEMPLATE_INVALID),
    "bad-pdf-layout": ("name: x\n", {"pdf.typ": b"#let conf = ("}, Codes.TEMPLATE_INVALID),
    "unknown-font": (
        "fonts: {body: {family: 없는글꼴, fallback: []}, heading: {family: 없는글꼴}}\n",
        {},
        Codes.FONT_FALLBACK,
    ),
    "reference-header-without-docx": (
        "header: {source: reference}\nfooter: {source: reference}\n",
        {},
        Codes.PDF_HEADER_SIMPLIFIED,
    ),
    # I1 crash inputs
    "null-margin-top": ("page: {margin: {top: null}}\n", {}, Codes.TEMPLATE_INVALID),
    "null-font-body": ("fonts: {body: null}\n", {}, Codes.TEMPLATE_INVALID),
    "numeric-header-center": ("header: {center: 2026}\n", {}, None),
    "int-bool-italic": ("elements: {body: {italic: 1}}\n", {}, Codes.TEMPLATE_INVALID),
    "int-caption-format": ("tables: {caption: {format: 1}}\n", {}, None),
}

FRONTMATTER_CASES = {
    "frontmatter-page-break-int": (
        "---\ntitle: t\npage_break: {before: 3}\n---\n\n# 하나\n\n본문\n\n# 둘\n\n본문\n",
        Codes.TEMPLATE_INVALID,
    ),
    "frontmatter-malformed-yaml": ("---\ntitle: [unclosed\n---\n\n# 본문\n", Codes.FRONTMATTER_INVALID),
}


def _convert(tmp_path: Path, source: Source, template: str | None):
    return pipeline.convert(
        source,
        [Format.DOCX, Format.PDF],
        template,
        Options(offline=True, cwd=tmp_path, home=tmp_path / "home"),
    )


@pytest.mark.parametrize("fixture", [KITCHEN, EDGE], ids=lambda p: p.stem)
@pytest.mark.parametrize("case", sorted(CASES))
def test_broken_templates_never_reject(tmp_path, case, fixture):
    yaml_text, files, expected = CASES[case]
    directory = tmp_path / ".mdcast" / "templates" / case
    directory.mkdir(parents=True)
    (directory / "template.yaml").write_text(yaml_text, encoding="utf-8")
    for filename, data in files.items():
        (directory / filename).write_bytes(data)
    source = Source(fixture.read_bytes(), fixture.name, Format.MD, base_dir=fixture.parent)
    result = _convert(tmp_path, source, case)
    assert len(result.outputs) == 2
    assert all(o.data for o in result.outputs), [e.to_dict() for e in result.report.events]
    if expected is not None:
        assert expected in [e.code for e in result.report.events]


@pytest.mark.parametrize("case", sorted(FRONTMATTER_CASES))
def test_broken_frontmatter_never_rejects(tmp_path, case):
    text, expected = FRONTMATTER_CASES[case]
    source = Source(text.encode("utf-8"), "doc.md", Format.MD, base_dir=tmp_path)
    result = _convert(tmp_path, source, None)
    assert len(result.outputs) == 2
    assert all(o.data for o in result.outputs), [e.to_dict() for e in result.report.events]
    assert expected in [e.code for e in result.report.events]
