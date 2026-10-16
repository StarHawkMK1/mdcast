import importlib.metadata
import json

import pytest
import typst
from helpers import build, write_template

from mdcast import __version__
from mdcast.ast import pandoc_version
from mdcast.fonts import font_paths, unknown_font_name
from mdcast.report import Codes
from mdcast.types import Format
from mdcast.writers.pdf.config import build_typst_config


def cfg_for(tmp_path, md="본문\n", template=None):
    _, ctx = build(tmp_path, md, Format.PDF, template=template)
    return build_typst_config(ctx.template, ctx.fields, ctx.report), ctx


def test_bundled_font_is_visible_to_typst(tmp_path):
    # System fonts are ignored so this fails if the bundle is missing even when
    # Noto Sans KR happens to be installed system-wide.
    src = tmp_path / "probe.typ"
    src.write_text('#set text(font: "Noto Sans KR")\n가', encoding="utf-8")
    assert font_paths(), "bundled font directory missing"
    _, warnings = typst.compile_with_warnings(
        str(src), root=str(tmp_path), font_paths=font_paths(), ignore_system_fonts=True
    )
    assert [w.message for w in warnings if unknown_font_name(w.message) == "noto sans kr"] == []


def test_page_fonts_and_json_serialisable(tmp_path):
    cfg, _ = cfg_for(tmp_path)
    assert (cfg["page"]["width"], cfg["page"]["height"]) == (210.0, 297.0)
    assert cfg["page"]["margin"]["top"] == 20
    assert cfg["fonts"]["body"] == ["Malgun Gothic", "Noto Sans KR"]
    json.dumps(cfg)


def test_elements_are_normalised(tmp_path):
    cfg, _ = cfg_for(tmp_path)
    h1 = cfg["elements"]["heading1"]
    assert (h1["size"], h1["bold"], h1["color"]) == (16.0, True, "#1F3864")
    assert cfg["elements"]["body"]["line_height"] == pytest.approx(1.6)
    assert "leading" not in cfg["elements"]["body"]
    assert cfg["tables"]["_default"]["line_height"] == pytest.approx(1.3)
    assert cfg["elements"]["quote"]["indent_left"] == 5.0
    assert cfg["elements"]["code"]["background"] == "#F6F8FA"


def test_header_footer_segments(tmp_path):
    cfg, _ = cfg_for(tmp_path, "---\ntitle: 사업계획\n---\n\n본문\n")
    assert cfg["header"]["right"] == [{"t": "text", "v": "사업계획"}]
    assert cfg["header"]["line"] == "below"
    assert cfg["footer"]["center"] == [{"t": "page"}, {"t": "text", "v": " / "}, {"t": "pages"}]
    assert cfg["document"]["title"] == "사업계획"


def test_keywords_carry_generator_versions(tmp_path):
    cfg, _ = cfg_for(tmp_path)
    kw = cfg["document"]["keywords"]
    assert "mdcast" in kw
    assert f"mdcast:{__version__}" in kw
    assert f"pandoc:{pandoc_version()}" in kw
    assert f"typst:{importlib.metadata.version('typst')}" in kw
    assert any(k.startswith("template:") for k in kw)


def test_table_variants_and_lists(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\ntables: {variants: {plain: {header: {background: null}}}}\nlists: {ordered: ['Ⅰ.', '(가)']}\n")
    cfg, _ = cfg_for(tmp_path, template=str(tpl))
    assert cfg["tables"]["_default"]["header"]["background"] == "#F2F2F2"
    assert cfg["tables"]["plain"]["header"]["background"] is None
    assert cfg["tables"]["plain"]["font_size"] == 10.0
    assert cfg["lists"]["ordered"] == ["I.", "(가)"]


def test_reference_header_is_simplified_for_pdf(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nheader: {source: reference}\n")
    _, ctx = cfg_for(tmp_path, template=str(tpl))
    assert [(e.code, e.where["format"]) for e in ctx.report.events if e.code == Codes.PDF_HEADER_SIMPLIFIED] == [
        (Codes.PDF_HEADER_SIMPLIFIED, "pdf")
    ]
