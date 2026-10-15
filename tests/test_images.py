import http.server
import threading
from contextlib import contextmanager
from dataclasses import replace

import docx
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
    path = make_reference_docx(tmp_path / "ref.docx", footer_runs=["a", "b"], extra_styles=("MyStyle",))
    document = docx.Document(str(path))
    assert "MyStyle" in [s.name for s in document.styles]
    assert document.sections[0].footer.paragraphs[0].text == "ab"


@contextmanager
def serve(handler_body):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            handler_body(self)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def failed_codes(tmp_path, url):
    doc, ctx = build(tmp_path, f"![x]({url})\n", Format.DOCX, offline=False)
    ctx.options = replace(ctx.options, url_timeout_s=2.0)
    doc = localize_images(doc, ctx)
    return images(doc), [e.code for e in ctx.report.events]


def test_directory_as_image_path_becomes_placeholder(tmp_path):
    (tmp_path / "dir.png").mkdir()
    doc, ctx = build(tmp_path, "![d](dir.png)\n", Format.DOCX)
    doc = localize_images(doc, ctx)
    assert images(doc) == []
    assert [e.code for e in ctx.report.events] == [Codes.IMAGE_FETCH_FAILED]


def test_unreadable_local_file_becomes_placeholder(tmp_path, monkeypatch):
    (tmp_path / "a.png").write_bytes(tiny_png())

    def boom(self):
        raise PermissionError("denied")

    monkeypatch.setattr("pathlib.Path.read_bytes", boom)
    doc, ctx = build(tmp_path, "![d](a.png)\n", Format.DOCX)
    doc = localize_images(doc, ctx)
    assert images(doc) == []
    assert [e.code for e in ctx.report.events] == [Codes.IMAGE_FETCH_FAILED]


def test_short_body_response_becomes_placeholder(tmp_path):
    def body(h):
        h.send_response(200)
        h.send_header("Content-Length", "1000")
        h.end_headers()
        h.wfile.write(b"abc")
        h.wfile.flush()
        h.close_connection = True

    with serve(body) as base:
        assert failed_codes(tmp_path, base + "/a.png") == ([], [Codes.IMAGE_FETCH_FAILED])


def test_oversized_image_becomes_placeholder(tmp_path, monkeypatch):
    monkeypatch.setattr("mdcast.writers.images.MAX_IMAGE_BYTES", 10)

    def body(h):
        h.send_response(200)
        h.send_header("Content-Length", str(len(tiny_png())))
        h.end_headers()
        h.wfile.write(tiny_png())

    with serve(body) as base:
        assert failed_codes(tmp_path, base + "/a.png") == ([], [Codes.IMAGE_FETCH_FAILED])


def test_redirect_to_non_http_is_refused(tmp_path):
    def body(h):
        h.send_response(302)
        h.send_header("Location", "ftp://127.0.0.1/a.png")
        h.end_headers()

    with serve(body) as base:
        assert failed_codes(tmp_path, base + "/a.png") == ([], [Codes.IMAGE_FETCH_FAILED])


def test_reachable_remote_image_is_downloaded(tmp_path):
    def body(h):
        h.send_response(200)
        h.send_header("Content-Length", str(len(tiny_png())))
        h.end_headers()
        h.wfile.write(tiny_png())

    with serve(body) as base:
        assert failed_codes(tmp_path, base + "/a.png") == (["assets/img1.png"], [])
