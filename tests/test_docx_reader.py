from __future__ import annotations

import io
import zipfile

import panflute as pf
import pytest
from docx.shared import Inches
from docx_builder import add_para, docx_bytes
from helpers import tiny_bmp, tiny_png

from mdcast.readers.docx import read_docx
from mdcast.report import Report
from mdcast.types import Format, Source


def first(doc: pf.Doc, kind: type) -> pf.Element:
    found: list[pf.Element] = []
    doc.walk(lambda e, _d: found.append(e) if isinstance(e, kind) else None)
    return found[0]


def read(data: bytes, name: str = "보고 서.docx"):
    report = Report(name, Format.DOCX)
    return read_docx(Source(data, name, Format.DOCX), report, "보고 서_assets"), report


def test_bmp_picture_is_extracted_as_png_with_assets_url():
    data = docx_bytes(lambda d: d.add_picture(io.BytesIO(tiny_bmp())))
    imp, _ = read(data)
    img = first(imp.doc, pf.Image)
    assert img.url == "보고 서_assets/image1.png"
    assert imp.media["image1.png"][:8] == b"\x89PNG\r\n\x1a\n"
    assert pf.stringify(img) == "그림"
    assert "width" not in img.attributes and "height" not in img.attributes


def test_small_picture_in_table_cell_warns_image_text():
    def build(d):
        table = d.add_table(1, 2)
        table.cell(0, 1).paragraphs[0].add_run().add_picture(io.BytesIO(tiny_png()), height=Inches(0.3))

    _, report = read(docx_bytes(build))
    ev = [e for e in report.events if e.code == "IMPORT_IMAGE_TEXT"]
    assert len(ev) == 1 and ev[0].where == {"table": 1, "row": 1, "col": 2}


def test_image_text_numbers_tables_in_document_preorder():
    def build(d):
        outer = d.add_table(1, 1)
        cell = outer.cell(0, 0)
        inner = cell.add_table(1, 1)
        inner.cell(0, 0).paragraphs[0].add_run().add_picture(io.BytesIO(tiny_png()), height=Inches(0.2))
        cell.add_paragraph()
        after = d.add_table(2, 1)
        after.cell(1, 0).paragraphs[0].add_run().add_picture(io.BytesIO(tiny_png()), height=Inches(0.2))

    _, report = read(docx_bytes(build))
    places = [e.where for e in report.events if e.code == "IMPORT_IMAGE_TEXT"]
    assert places == [{"table": 2, "row": 1, "col": 1}, {"table": 3, "row": 2, "col": 1}]


def test_large_or_described_picture_in_cell_is_quiet():
    def build(d):
        table = d.add_table(1, 2)
        table.cell(0, 0).paragraphs[0].add_run().add_picture(io.BytesIO(tiny_png()), height=Inches(2))
        d.add_picture(io.BytesIO(tiny_png()), height=Inches(0.2))

    _, report = read(docx_bytes(build))
    assert not [e for e in report.events if e.code == "IMPORT_IMAGE_TEXT"]


def test_header_footer_and_comments_are_reported():
    def build(d):
        d.sections[0].header.paragraphs[0].text = "머리말"
        add_para(d, "본문")

    _, report = read(docx_bytes(build))
    assert len([e for e in report.events if e.code == "IMPORT_HEADER_SKIPPED"]) == 1
    _, plain = read(docx_bytes(lambda d: add_para(d, "본문")))
    assert not [e for e in plain.events if e.code == "IMPORT_HEADER_SKIPPED"]


def test_frontmatter_and_source_text():
    def build(d):
        d.core_properties.title = "제목"
        d.core_properties.author = "작성자"
        add_para(d, "본문")

    imp, _ = read(docx_bytes(build))
    assert imp.frontmatter == {"title": "제목", "author": "작성자"}
    assert "본문" in imp.source_text


def test_corrupt_bytes_raise():
    with pytest.raises(zipfile.BadZipFile):
        read(b"not a zip")


def test_description_is_kept_as_alt_text():
    def build(d):
        d.add_picture(io.BytesIO(tiny_png()))
        d.inline_shapes[0]._inline.docPr.set("descr", "매출 그래프")

    imp, _ = read(docx_bytes(build))
    assert pf.stringify(first(imp.doc, pf.Image)) == "매출 그래프"


def test_comments_are_reported():
    def build(d):
        run = add_para(d, "본문").runs[0]
        d.add_comment(run, text="메모", author="a")

    _, report = read(docx_bytes(build))
    assert len([e for e in report.events if e.code == "IMPORT_HEADER_SKIPPED"]) == 1


def test_colliding_media_names_stay_distinct():
    import zipfile

    def build(d):
        d.add_picture(io.BytesIO(tiny_bmp()))
        d.add_picture(io.BytesIO(tiny_png()))

    src = zipfile.ZipFile(io.BytesIO(docx_bytes(build)))
    renames = {"word/media/image1.bmp": "word/media/a/pic.bmp", "word/media/image2.png": "word/media/b/pic.png"}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for info in src.infolist():
            blob = src.read(info.filename)
            if info.filename in renames:
                target.writestr(renames[info.filename], blob)
                continue
            if info.filename == "word/_rels/document.xml.rels":
                text = blob.decode("utf-8")
                for old, new in renames.items():
                    text = text.replace(old.removeprefix("word/"), new.removeprefix("word/"))
                blob = text.encode("utf-8")
            target.writestr(info, blob)
    imp, _ = read(out.getvalue())
    images = []
    imp.doc.walk(lambda e, _d: images.append(e) if isinstance(e, pf.Image) else None)
    urls = [i.url for i in images]
    assert len(set(urls)) == 2 and len(imp.media) == 2
    assert all(u.split("/", 1)[1] in imp.media for u in urls)


def _rename_media(data: bytes, old: str, new: str) -> bytes:
    import zipfile

    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for info in src.infolist():
            blob = src.read(info.filename)
            if info.filename == f"word/{old}":
                entry = zipfile.ZipInfo("x")
                entry.filename = f"word/{new}"  # set after init: ZipInfo would turn backslashes into slashes
                target.writestr(entry, blob)
                continue
            if info.filename == "word/_rels/document.xml.rels":
                blob = blob.decode("utf-8").replace(old, new).encode("utf-8")
            target.writestr(info.filename, blob)
    return out.getvalue()


def test_media_names_never_escape_the_assets_folder():
    from mdcast.readers.docx import _media_name

    B = chr(92)
    assert _media_name(f"media/..{B}..{B}evil.png", 1) == "evil.png"
    assert _media_name(f"media/a{B}b{B}pic.png", 1) == "pic.png"
    assert _media_name("media/a/b.png", 1) == "b.png"
    for url in ("media/..", "media/.", "media/", f"media{B}..", ""):
        assert _media_name(url, 3) == "image3.png"


def test_media_names_lose_characters_windows_forbids():
    from mdcast.readers.docx import _media_name

    assert _media_name('media/a:b*c?d"e<f>g|h.png', 1) == "a_b_c_d_e_f_g_h.png"
    assert _media_name("media/C:pic.png", 1) == "C_pic.png"


def test_odd_media_path_still_imports_inside_assets():
    data = docx_bytes(lambda d: d.add_picture(io.BytesIO(tiny_png())))
    imp, _ = read(_rename_media(data, "media/image1.png", "media/a/b/pic.png"))
    assert list(imp.media) == ["pic.png"] and first(imp.doc, pf.Image).url == "보고 서_assets/pic.png"
