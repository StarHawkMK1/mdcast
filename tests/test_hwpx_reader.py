from __future__ import annotations

import io
import zipfile

import panflute as pf
import pytest
from hwpx_builder import cell, hwpx_bytes, p, run, tbl
from lxml import etree

from mdcast.readers.docx_package import PAGEBREAK_SENTINEL
from mdcast.readers.hwpx import read_hwpx
from mdcast.readers.hwpx.body import BodyReader
from mdcast.readers.hwpx.package import HP, CharStyle, HwpxError, ParaStyle, open_hwpx
from mdcast.report import Report
from mdcast.types import Format, Source


def _replace(data: bytes, name: str, blob: bytes) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            target.writestr(info, blob if info.filename == name else source.read(info.filename))
    return out.getvalue()


def test_open_reads_spine_order_styles_and_meta():
    data = hwpx_bytes(
        p(run("첫")),
        p(run("둘")),
        title="제목",
        meta={"mdcast.generator": "mdcast 0.1", "creator": "홍"},
    )
    pkg = open_hwpx(data)
    assert len(pkg.sections) == 2 and pkg.title == "제목" and pkg.creator == "홍"
    assert pkg.generator == {"mdcast.generator": "mdcast 0.1"}
    assert pkg.styles.chars["1"].bold and pkg.styles.paras["3"] == ParaStyle("NUMBER", 0, "1")
    assert pkg.styles.numbering_start["2"] == 3


def test_sections_follow_spine_order_not_manifest_order():
    data = hwpx_bytes(p(run("첫")), p(run("둘")))
    content = zipfile.ZipFile(io.BytesIO(data)).read("Contents/content.hpf").decode()
    forward = '<opf:itemref idref="section0"/><opf:itemref idref="section1"/>'
    assert forward in content
    swapped = content.replace(
        forward, '<opf:itemref idref="section1"/><opf:itemref idref="section0"/>'
    )
    pkg = open_hwpx(_replace(data, "Contents/content.hpf", swapped.encode()))
    assert ["".join(section.itertext()) for section in pkg.sections] == ["둘", "첫"]


def test_fixed_header_ids_map_to_styles():
    styles = open_hwpx(hwpx_bytes(p(run("a")))).styles
    assert styles.chars == {
        "0": CharStyle(),
        "1": CharStyle(bold=True),
        "2": CharStyle(italic=True),
        "3": CharStyle(superscript=True),
        "4": CharStyle(subscript=True),
        "5": CharStyle(strike=True),
    }
    assert styles.paras == {
        "0": ParaStyle(),
        "1": ParaStyle("OUTLINE", 0),
        "2": ParaStyle("OUTLINE", 1),
        "3": ParaStyle("NUMBER", 0, "1"),
        "4": ParaStyle("NUMBER", 1, "1"),
        "5": ParaStyle("BULLET", 0, "1"),
        "6": ParaStyle("NUMBER", 0, "2"),
    }
    assert styles.numbering_start == {"1": 1, "2": 3}


def test_empty_meta_values_are_absent():
    pkg = open_hwpx(hwpx_bytes(p(run("a")), meta={"mdcast.generator": "", "mdcast.template": "t"}))
    assert pkg.title is None and pkg.creator is None
    assert pkg.generator == {"mdcast.template": "t"}


def test_bin_data_keyed_by_manifest_id():
    pkg = open_hwpx(hwpx_bytes(p(run("a")), bin_data={"image1.png": b"PNGDATA"}))
    assert pkg.bin_data == {"image1": ("image1.png", b"PNGDATA")}


def test_not_a_zip_is_hwpx_error():
    with pytest.raises(HwpxError):
        open_hwpx(b"x")


def test_missing_content_hpf_is_hwpx_error():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        target.writestr("mimetype", "application/hwp+zip")
    with pytest.raises(HwpxError):
        open_hwpx(out.getvalue())


def test_encrypted_package_is_hwpx_error_naming_security():
    with pytest.raises(HwpxError, match="암호|보안"):
        open_hwpx(hwpx_bytes(p(run("a")), encrypted=True))


def test_unreadable_section_is_hwpx_error_naming_security():
    data = _replace(hwpx_bytes(p(run("a"))), "Contents/section0.xml", b"\x93\x11\xfe garbled")
    with pytest.raises(HwpxError, match="암호|보안"):
        open_hwpx(data)


def _read(*sections: str, **kw):
    report = Report("a.hwpx", Format.HWPX)
    return read_hwpx(Source(hwpx_bytes(*sections, **kw), "a.hwpx", Format.HWPX), report, "a_assets"), report


def read(*sections: str, **kw) -> tuple[pf.Doc, Report]:
    imported, report = _read(*sections, **kw)
    return imported.doc, report


def text(elem: pf.Element) -> str:
    return pf.stringify(elem, newlines=False)


def kinds(elems) -> list[str]:
    return [type(e).__name__ for e in elems]


def test_runs_keep_bold_italic_sup_sub_strike_and_breaks():
    doc, _ = read(p(run("굵", "1"), run("기", "2"), run("x"), run("2", "3")))
    para = doc.content[0]
    assert [type(i).__name__ for i in para.content] == ["Strong", "Emph", "Str", "Superscript"]

    doc, _ = read(p(run("H"), run("2", "4"), run("O "), run("지움", "5")))
    para = doc.content[0]
    assert kinds(para.content) == ["Str", "Subscript", "Str", "Space", "Strikeout"]
    assert text(para) == "H2O 지움"


def test_tab_and_line_break_inside_text():
    t = '<hp:run charPrIDRef="0"><hp:t>가<hp:tab width="0" leader="0" type="1"/>나<hp:lineBreak/>다</hp:t></hp:run>'
    doc, _ = read(p(t))
    assert kinds(doc.content[0].content) == ["Str", "Space", "Str", "LineBreak", "Str"]
    assert text(doc.content[0]) == "가 나 다"


def test_same_style_runs_merge_and_edge_spaces_leave_the_wrapper():
    doc, _ = read(p(run("본"), run("문 "), run("굵 ", "1"), run("게", "1"), run(" 끝 ")))
    para = doc.content[0]
    assert kinds(para.content) == ["Str", "Space", "Strong", "Space", "Str"]
    assert text(para.content[0]) == "본문"
    assert kinds(para.content[2].content) == ["Str", "Space", "Str"]
    assert text(para) == "본문 굵 게 끝"


def test_paragraphs_without_text_are_dropped():
    doc, _ = read(p(run("하나")), p(), p(run("   ")), p(run("둘")))
    assert [text(b) for b in doc.content] == ["하나", "둘"]


def test_unknown_run_children_keep_the_text_around_them():
    body = (
        '<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="0"><hp:secPr id=""/><hp:ctrl><hp:colPr id="" type="NEWSPAPER"/></hp:ctrl>'
        "<hp:t>앞<hp:markpenBegin/>표시<hp:markpenEnd/>뒤</hp:t></hp:run></hp:p>"
    )
    doc, _ = read(body)
    assert [text(b) for b in doc.content] == ["앞표시뒤"]


def test_unknown_style_ids_read_as_plain():
    doc, _ = read(p(run("글", "99"), para="99"))
    assert kinds(doc.content) == ["Para"] and kinds(doc.content[0].content) == ["Str"]


def test_outline_paragraphs_are_headers_and_page_break_leaves_sentinel():
    doc, _ = read(p(run("개요"), para="1"), p(run("세부"), para="2"), p(run("본문")), p(run("다음"), page_break=True))
    assert kinds(doc.content) == ["Header", "Header", "Para", "Para", "Para"]
    assert [b.level for b in doc.content[:2]] == [1, 2]
    assert text(doc.content[0]) == "개요"
    assert text(doc.content[3]) == PAGEBREAK_SENTINEL
    assert text(doc.content[4]) == "다음"


def test_page_break_on_an_empty_paragraph_still_leaves_sentinel():
    doc, _ = read(p(run("앞")), p(page_break=True), p(run("뒤")))
    assert [text(b) for b in doc.content] == ["앞", PAGEBREAK_SENTINEL, "뒤"]


def _outline_header_with_level(level: str) -> str:
    return (
        '<hh:paraPr id="7" tabPrIDRef="0" condense="0"><hh:align horizontal="JUSTIFY" vertical="BASELINE"/>'
        f'<hh:heading type="OUTLINE" idRef="0" level="{level}"/></hh:paraPr>'
    )


@pytest.mark.parametrize(("level", "expected"), [("5", 6), ("7", 6), ("9", None)])
def test_deep_outline_levels_cap_at_six_and_nine_is_body(level, expected):
    data = hwpx_bytes(p(run("깊은"), para="7"))
    header = zipfile.ZipFile(io.BytesIO(data)).read("Contents/header.xml").decode()
    header = header.replace("</hh:paraProperties>", _outline_header_with_level(level) + "</hh:paraProperties>")
    data = _replace(data, "Contents/header.xml", header.encode())
    report = Report("a.hwpx", Format.HWPX)
    block = read_hwpx(Source(data, "a.hwpx", Format.HWPX), report, "a_assets").doc.content[0]
    if expected is None:
        assert isinstance(block, pf.Para)
    else:
        assert isinstance(block, pf.Header) and block.level == expected


def test_paragraph_in_cell_is_plain_without_sentinel():
    pkg = open_hwpx(hwpx_bytes(p(run("a"))))
    reader = BodyReader(pkg, Report("a.hwpx", Format.HWPX), None)
    xml = (
        f'<hp:p xmlns:hp="{HP}" id="0" paraPrIDRef="1" styleIDRef="0" pageBreak="1" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="1"><hp:t>칸 글</hp:t></hp:run></hp:p>'
    )
    blocks = reader.paragraph(etree.fromstring(xml), in_cell=True)
    assert kinds(blocks) == ["Plain"] and kinds(blocks[0].content) == ["Strong"]


def test_sections_are_read_in_spine_order():
    doc, _ = read(p(run("하나")), p(run("둘")))
    assert [text(b) for b in doc.content] == ["하나", "둘"]


def test_sections_keep_every_paragraph():
    imported, _ = _read(p(run("가")) + p(run("나")), p(run("다")) + p(run("라")), p(run("마")))
    assert [text(b) for b in imported.doc.content] == ["가", "나", "다", "라", "마"]
    assert imported.source_text == ["가", "나", "다", "라", "마"]


def test_source_text_has_one_entry_per_paragraph():
    table = tbl([[cell(p(run("칸 하나")), col=0, row=0), cell(p(run("칸 둘")), col=1, row=0)]], cols=2)
    imported, _ = _read(p(run("앞 "), run("굵게", "1"), table, run("뒤")), p(), p(run("끝")))
    # a paragraph's own text, then each paragraph of its tables on its own line; empty ones are left out
    assert imported.source_text == ["앞 굵게뒤", "칸 하나", "칸 둘", "끝"]


def test_frontmatter_media_and_generator():
    imported, _ = _read(p(run("a")), title="제목", meta={"creator": "", "mdcast.template": "t"})
    assert imported.frontmatter == {"title": "제목"}
    assert imported.media == {} and imported.table_styles == []
    assert imported.generator == {"mdcast.template": "t"}
    imported, _ = _read(p(run("a")), meta={"creator": "홍"})
    assert imported.frontmatter == {"author": "홍"}


def test_read_hwpx_lets_hwpx_error_through():
    with pytest.raises(HwpxError, match="암호|보안"):
        _read(p(run("a")), encrypted=True)
