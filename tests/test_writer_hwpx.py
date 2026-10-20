from helpers import HWPX_NS as NS
from helpers import build, builtin_hwpx, hwpx_integrity, tiny_bmp, write_template

from mdcast import hwpx, pipeline
from mdcast.hwpx import Package
from mdcast.report import Codes, Level
from mdcast.templates import validate_template
from mdcast.types import Format, Options, Source
from mdcast.writers.hwpx import _load_images, _settings, write_hwpx


def render(tmp_path, md, template=None):
    doc, ctx = build(tmp_path, md, Format.HWPX, template=template)
    return hwpx_integrity(write_hwpx(doc, ctx)), ctx


def body_para(parts, text):
    for p in parts["Contents/section0.xml"].iter(f"{{{NS['hp']}}}p"):
        if "".join("".join(t.itertext()) for t in p.findall("hp:run/hp:t", NS)) == text:
            return p
    raise AssertionError(text)


def text_char(p):
    """charPrIDRef of the first run holding text (the first paragraph starts with secPr/ctrl runs)."""
    return next(r for r in p.findall("hp:run", NS) if r.find("hp:t", NS) is not None).get("charPrIDRef")


def test_builtin_template_looks(tmp_path):
    parts, _ = render(tmp_path, "---\ntitle: 보고서\n---\n\n# 개요\n\n본문 문단\n")
    head = parts["Contents/header.xml"]
    body = body_para(parts, "본문 문단")
    para = head.find(f".//hh:paraPr[@id='{body.get('paraPrIDRef')}']", NS)
    assert para.find("hh:lineSpacing", NS).get("value") == "180"
    heading = body_para(parts, "개요")
    char = head.find(f".//hh:charPr[@id='{text_char(heading)}']", NS)
    assert char.get("height") == "1600" and char.get("textColor") == "#1F3864"
    header_text = "".join(parts["Contents/section0.xml"].find(".//hp:header", NS).itertext())
    assert "보고서" in header_text
    footer = parts["Contents/section0.xml"].find(".//hp:footer", NS)
    assert [n.get("numType") for n in footer.iter(f"{{{NS['hp']}}}autoNum")] == ["PAGE", "TOTAL_PAGE"]


def test_pagebreak_marker_reaches_hwpx(tmp_path):
    parts, _ = render(tmp_path, "가\n\n<!-- pagebreak -->\n\n나\n")
    assert body_para(parts, "나").get("pageBreak") == "1"


def test_degraded_elements_warn_once(tmp_path):
    _, ctx = render(tmp_path, "| a |\n|---|\n| 1 |\n\n| b |\n|---|\n| 2 |\n")
    events = [(e.code, e.where.get("element")) for e in ctx.report.events if e.where.get("format") == "hwpx"]
    assert events.count((Codes.RENDER_WARNING, "table")) == 1


def test_custom_container_gets_only_explicit_values(tmp_path):
    package = Package.read(builtin_hwpx())
    head = package.xml("Contents/header.xml")
    head.find(".//hh:paraPr[@id='0']/hh:lineSpacing", NS).set("value", "150")
    package.set_xml("Contents/header.xml", head)
    tpl = write_template(tmp_path, "t", "name: t\nelements: {body: {size: 12pt}}\n",
                         {"reference.hwpx": package.write()})
    parts, _ = render(tmp_path, "본문\n", str(tpl))
    body = body_para(parts, "본문")
    head = parts["Contents/header.xml"]
    para = head.find(f".//hh:paraPr[@id='{body.get('paraPrIDRef')}']", NS)
    assert para.find("hh:lineSpacing", NS).get("value") == "150"
    char = head.find(f".//hh:charPr[@id='{text_char(body)}']", NS)
    assert char.get("height") == "1200"


def test_broken_custom_container_falls_back(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\n", {"reference.hwpx": b"junk"})
    parts, ctx = render(tmp_path, "본문\n", str(tpl))
    assert body_para(parts, "본문") is not None
    assert Codes.TEMPLATE_INVALID in [e.code for e in ctx.report.events]


def test_missing_hwpx_style_is_info(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nstyles: {quote: {docx: Block Text, hwpx: 인용문}}\n")
    _, ctx = render(tmp_path, "> 인용\n", str(tpl))
    events = [(e.code, e.level, e.where.get("element")) for e in ctx.report.events if e.where.get("format") == "hwpx"]
    assert (Codes.STYLE_UNMAPPED, Level.INFO, "quote") in events


def test_validate_reports_missing_hwpx_style(tmp_path):
    write_template(tmp_path / ".mdcast" / "templates", "t", "name: t\nstyles: {quote: {hwpx: 인용문}}\n",
                   {"reference.hwpx": builtin_hwpx()})
    _, report = validate_template("t", cwd=tmp_path, home=tmp_path / "home")
    assert [(e.code, e.where.get("format")) for e in report.events if e.code == Codes.STYLE_UNMAPPED] == [
        (Codes.STYLE_UNMAPPED, "hwpx")
    ]


def test_pipeline_writes_hwpx(tmp_path):
    source = Source("# 제목\n\n본문\n".encode(), "doc.md", Format.MD, base_dir=tmp_path)
    result = pipeline.convert(source, [Format.HWPX], options=Options(offline=True, cwd=tmp_path, home=tmp_path))
    output = result.outputs[0]
    assert output.name == "doc.hwpx" and output.data[:2] == b"PK"
    hwpx_integrity(output.data)
    assert not [e for e in result.report.events if e.level is Level.ERROR]


def test_code_hangul_text_uses_the_body_font(tmp_path):
    parts, _ = render(tmp_path, "앞\n\n```\n코드\n```\n")
    head = parts["Contents/header.xml"]
    code = body_para(parts, "코드")
    ref = head.find(f".//hh:charPr[@id='{text_char(code)}']/hh:fontRef", NS)
    hangul = head.find(".//hh:fontface[@lang='HANGUL']", NS)
    latin = head.find(".//hh:fontface[@lang='LATIN']", NS)
    assert hangul.find(f"hh:font[@id='{ref.get('hangul')}']", NS).get("face") == "맑은 고딕"
    assert latin.find(f"hh:font[@id='{ref.get('latin')}']", NS).get("face") == "Consolas"


def test_odd_custom_container_falls_back(tmp_path):
    package = Package.read(builtin_hwpx())
    head = package.xml("Contents/header.xml")
    head.find(".//hh:fontface[@lang='HANGUL']", NS).set("lang", "OTHERSCRIPT")  # no Hangul group
    package.set_xml("Contents/header.xml", head)
    yaml_text = "name: t\nfonts: {body: {family: 맑은 고딕}}\n"  # code's Hangul face needs that group
    tpl = write_template(tmp_path, "t", yaml_text, {"reference.hwpx": package.write()})
    parts, ctx = render(tmp_path, "```\n코드\n```\n", str(tpl))
    assert body_para(parts, "코드") is not None
    assert Codes.TEMPLATE_INVALID in [e.code for e in ctx.report.events]


def test_table_looks_come_from_the_full_config(tmp_path):
    _, ctx = build(tmp_path, "| a |\n|---|\n| 1 |\n", Format.HWPX)
    settings = _settings(ctx, custom=False)
    look = settings.tables[None]
    assert look == hwpx.TableLook(width="full", font_size=10.0, line_height=1.3, padding=1.5,
                                  border=hwpx.Border(0.5, "#000000"), border_outer=hwpx.Border(1.0, "#000000"),
                                  header_background="#F2F2F2", header_valign="middle", header_repeat=True,
                                  body_valign="middle", zebra=None, first_column_background=None)
    assert settings.figure_max_ratio == 1.0 and settings.figure_max_mm is None
    assert settings.figure_align == "center"


def test_custom_container_still_gets_variant_table_looks(tmp_path):
    template = write_template(tmp_path, "t", """
        name: t
        tables: {variants: {제출양식: {border: {width: 0.34pt}, border_outer: {width: 0.34pt}, header: {background: "#E5E5E5"}}}}
        figures: {max_width: 120mm}
    """, {"reference.hwpx": builtin_hwpx()})
    _, ctx = build(tmp_path, "본문\n", Format.HWPX, template=str(template))
    settings = _settings(ctx, custom=True)
    assert settings.tables["제출양식"].border == hwpx.Border(0.34, "#000000")
    assert settings.tables["제출양식"].header_background == "#E5E5E5"
    assert settings.tables[None].border_outer == hwpx.Border(1.0, "#000000")
    assert settings.figure_max_ratio is None and settings.figure_max_mm == 120.0


def test_hwpx_images_are_loaded_converted_or_replaced(tmp_path):
    from PIL import Image as PILImage

    PILImage.new("RGB", (40, 20)).save(tmp_path / "w.webp")
    (tmp_path / "t.bmp").write_bytes(tiny_bmp())
    doc, ctx = build(tmp_path, "![w](w.webp) ![b](t.bmp) ![x](none.png)\n", Format.HWPX)
    doc, images = _load_images(doc, ctx)
    assert sorted(image.ext for image in images.values()) == ["bmp", "png"]
    assert [e.code for e in ctx.report.events].count(Codes.IMAGE_FETCH_FAILED) == 1
