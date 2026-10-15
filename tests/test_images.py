from dataclasses import replace

import panflute as pf
from helpers import build, make_reference_docx, tiny_png

from mdcast.report import Codes
from mdcast.types import Format
from mdcast.writers.images import localize_images


def images(doc):
    found = []
    doc.walk(lambda e, d: found.append(e.url) if isinstance(e, pf.Image) else None)
    return found


def test_relative_image_with_korean_and_space_is_copied(tmp_path):
    (tmp_path / "그림 1.png").write_bytes(tiny_png())
    doc, ctx = build(tmp_path, "![설명](<그림 1.png>)\n", Format.DOCX)
    doc = localize_images(doc, ctx)
    assert images(doc) == ["assets/img1.png"]
    assert (ctx.work_dir / "assets" / "img1.png").read_bytes() == tiny_png()
    assert ctx.report.events == []


def test_missing_image_becomes_placeholder_with_warning(tmp_path):
    doc, ctx = build(tmp_path, "앞 ![없는 그림](none.png) 뒤\n", Format.PDF)
    doc = localize_images(doc, ctx)
    assert images(doc) == []
    assert "[이미지: 없는 그림]" in pf.stringify(doc)
    assert [(e.code, e.where["format"]) for e in ctx.report.events] == [(Codes.IMAGE_FETCH_FAILED, "pdf")]


def test_remote_image_offline_is_not_fetched(tmp_path):
    doc, ctx = build(tmp_path, "![로고](https://example.com/logo.png)\n", Format.DOCX, offline=True)
    doc = localize_images(doc, ctx)
    assert images(doc) == []
    assert [e.code for e in ctx.report.events] == [Codes.IMAGE_FETCH_FAILED]


def test_absolute_path_image(tmp_path):
    target = tmp_path / "abs.png"
    target.write_bytes(tiny_png())
    doc, ctx = build(tmp_path, f"![a](<{target.as_posix()}>)\n", Format.DOCX)
    doc = localize_images(doc, ctx)
    assert images(doc) == ["assets/img1.png"]


def test_remote_image_unreachable_online_becomes_placeholder(tmp_path):
    doc, ctx = build(tmp_path, "![x](http://127.0.0.1:9/a.png)\n", Format.DOCX, offline=False)
    ctx.options = replace(ctx.options, url_timeout_s=0.5)
    doc = localize_images(doc, ctx)
    assert images(doc) == []
    assert [e.code for e in ctx.report.events] == [Codes.IMAGE_FETCH_FAILED]


def test_make_reference_docx_adds_styles_and_footer(tmp_path):
    import docx

    path = make_reference_docx(tmp_path / "ref.docx", footer_runs=["a", "b"], extra_styles=("MyStyle",))
    document = docx.Document(str(path))
    assert "MyStyle" in [s.name for s in document.styles]
    assert document.sections[0].footer.paragraphs[0].text == "ab"
