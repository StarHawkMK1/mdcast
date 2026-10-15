import io
import zipfile

from docx.oxml.ns import qn
from helpers import build, write_template
from lxml import etree

from mdcast.types import Format
from mdcast.writers.docx import write_docx
from mdcast.writers.docx.xml import mm_to_twips


def abstract_levels(data: bytes):
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/numbering.xml"))
    result = []
    for abstract in root.findall(qn("w:abstractNum")):
        levels = []
        for lvl in abstract.findall(qn("w:lvl")):
            fmt = lvl.find(qn("w:numFmt")).get(qn("w:val"))
            text = lvl.find(qn("w:lvlText")).get(qn("w:val"))
            ind = lvl.find(qn("w:pPr")).find(qn("w:ind"))
            fonts = lvl.find(qn("w:rPr"))
            east = fonts.find(qn("w:rFonts")).get(qn("w:eastAsia")) if fonts is not None and fonts.find(qn("w:rFonts")) is not None else None
            levels.append((fmt, text, int(ind.get(qn("w:left"))), east))
        result.append(levels)
    return result


def render(tmp_path, md, template=None):
    doc, ctx = build(tmp_path, md, Format.DOCX, template=template)
    return write_docx(doc, ctx)


def test_bullet_levels_use_template_symbols_and_body_font(tmp_path):
    data = render(tmp_path, "- 하나\n    - 둘\n        - 셋\n")
    bullets = [lv for lv in abstract_levels(data) if lv[0][0] == "bullet"]
    assert bullets, "pandoc should create a bullet abstractNum"
    first = bullets[0]
    assert [t for _, t, _, _ in first[:5]] == ["□", "○", "-", "·", "·"]
    assert first[0][3] == "맑은 고딕"
    assert first[1][2] == mm_to_twips(10)


def test_ordered_levels_use_korean_formats(tmp_path):
    data = render(tmp_path, "1. 첫째\n    1. 둘째\n        1. 셋째\n")
    ordered = [lv for lv in abstract_levels(data) if lv[0][0] != "bullet"]
    first = ordered[0]
    assert [(f, t) for f, t, _, _ in first[:3]] == [("decimal", "%1."), ("ganada", "%2."), ("decimal", "%3)")]


def test_custom_patterns(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nlists: {ordered: ['(1)', '①']}\n")
    data = render(tmp_path, "1. a\n    1. b\n        1. c\n", str(tpl))
    ordered = next(lv for lv in abstract_levels(data) if lv[0][0] != "bullet")
    assert [(f, t) for f, t, _, _ in ordered[:3]] == [
        ("decimal", "(%1)"),
        ("decimalEnclosedCircle", "%2"),
        ("decimalEnclosedCircle", "%3"),
    ]
