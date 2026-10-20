import shutil
from pathlib import Path

from docx_builder import strip_mdcast_metadata
from helpers import export

from mdcast.pipeline import convert
from mdcast.report import Codes, Level
from mdcast.types import Format, Source

SAMPLE = Path(__file__).parent / "fixtures" / "md" / "assets" / "sample.png"


def test_convert_docx_to_md(tmp_path):
    shutil.copy(SAMPLE, tmp_path / "sample.png")
    data = strip_mdcast_metadata(export(tmp_path, "# 개요\n\n- 가\n- 나\n\n![](sample.png)\n", Format.DOCX))
    res = convert(Source(data, "보고 서.docx", Format.DOCX), [Format.MD])
    out = res.outputs[0]
    assert out.name == "보고 서.md" and out.data.decode().count("# 개요") == 1
    # pandoc names the media after the relationship id (rIdN.png), the reader keeps the package's name
    assert len(out.assets) == 1 and next(iter(out.assets)).startswith("보고 서_assets/")
    assert next(iter(out.assets)).endswith(".png")
    assert next(iter(out.assets)).rsplit("/", 1)[1] in out.data.decode()
    assert res.report.coverage == 1.0


def _docx(tmp_path):
    return export(tmp_path, "# 개요\n\n본문\n", Format.DOCX)


def test_docx_to_other_target_is_unsupported(tmp_path):
    res = convert(Source(_docx(tmp_path), "a.docx", Format.DOCX), [Format.PDF])
    errors = [e for e in res.report.events if e.code == Codes.TARGET_UNSUPPORTED]
    assert errors and "docx 입력은 md 로만 변환합니다" in errors[0].message
    assert res.outputs[0].data is None


def test_corrupt_docx_is_input_corrupt():
    res = convert(Source(b"PK\x03\x04broken", "a.docx", Format.DOCX), [Format.MD])
    assert any(e.code == Codes.INPUT_CORRUPT for e in res.report.events)
    assert res.outputs[0].data is None


def test_hwpx_and_pdf_input_still_unsupported():
    for fmt, mark in ((Format.HWPX, "M3b"), (Format.PDF, "M3c")):
        res = convert(Source(b"x", f"a.{fmt.value}", fmt), [Format.MD])
        events = [e for e in res.report.events if e.code == Codes.INPUT_UNSUPPORTED]
        assert events and mark in events[0].message


def test_template_is_ignored_for_docx(tmp_path):
    res = convert(Source(_docx(tmp_path), "a.docx", Format.DOCX), [Format.MD], template="없는템플릿")
    assert res.outputs[0].data is not None
    notes = [e for e in res.report.events if "템플릿을 쓰지 않습니다" in e.message]
    assert [(e.level, e.code) for e in notes] == [(Level.INFO, Codes.RENDER_WARNING)] and "없는템플릿" in notes[0].message
    assert notes[0] in res.report.events_for(Format.MD)
    res = convert(Source(_docx(tmp_path), "a.docx", Format.DOCX), [Format.MD])
    assert not [e for e in res.report.events if "템플릿" in e.message]


def test_typed_punctuation_and_math_keep_full_coverage(tmp_path):
    from docx_builder import add_para, docx_bytes

    def build(d):
        add_para(d, "개요", outline=0)
        add_para(d, "검토 결과는 다음과 같다...")
        add_para(d, "A--B 구간")
        add_para(d, "Owner's note")

    res = convert(Source(docx_bytes(build), "a.docx", Format.DOCX), [Format.MD])
    assert res.report.coverage == 1.0
    assert not [e for e in res.report.events if e.code == Codes.IMPORT_TEXT_MISSING]

    md = "# 제목\n\n본문 $x^2$ 이다.\n\n| a | b |\n|---|---|\n| $y^3$ | z |\n\nTable: 캡션\n"
    data = strip_mdcast_metadata(export(tmp_path, md, Format.DOCX))
    res = convert(Source(data, "m.docx", Format.DOCX), [Format.MD])
    assert res.report.coverage == 1.0
    assert not [e for e in res.report.events if e.code == Codes.IMPORT_TEXT_MISSING]


def test_large_table_imports_with_few_pandoc_calls(monkeypatch):
    import pypandoc
    from docx_builder import add_para, docx_bytes

    def build(d):
        add_para(d, "제목", outline=0)
        table = d.add_table(rows=50, cols=6)
        for r in range(50):
            for c in range(6):
                table.cell(r, c).text = f"칸 {r}-{c}"
        table.cell(1, 0).merge(table.cell(2, 0))  # a merged cell makes it an HTML table

    data = docx_bytes(build)
    calls: list[str] = []
    real = pypandoc.convert_text, pypandoc.convert_file
    monkeypatch.setattr(pypandoc, "convert_text", lambda *a, **k: calls.append("t") or real[0](*a, **k))
    monkeypatch.setattr(pypandoc, "convert_file", lambda *a, **k: calls.append("f") or real[1](*a, **k))
    res = convert(Source(data, "a.docx", Format.DOCX), [Format.MD])
    assert len(calls) <= 8  # was one call per cell (300+)
    assert "칸 49-5" in res.outputs[0].data.decode() and res.report.coverage == 1.0


def test_imported_odd_asset_folder_exports_again(tmp_path):
    import io

    from docx_builder import docx_bytes
    from helpers import tiny_png

    data = docx_bytes(lambda d: d.add_picture(io.BytesIO(tiny_png())))
    res = convert(Source(data, "붙임1)50%20 계획.docx", Format.DOCX), [Format.MD])
    out = res.outputs[0]
    for name, blob in out.assets.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(blob)
    assert "붙임1%2950%2520%20계획_assets/" in out.data.decode()
    back = convert(Source(out.data, "붙임.md", Format.MD, base_dir=tmp_path), [Format.DOCX])
    assert back.outputs[0].data is not None
    assert not [e for e in back.report.events if e.code == Codes.IMAGE_FETCH_FAILED]


def test_hand_written_encoded_image_paths_still_export(tmp_path):
    from helpers import tiny_png

    for name in ("my pic.png", "50%.png", "a(1).png"):
        (tmp_path / name).write_bytes(tiny_png())
    md = (
        "![a](my%20pic.png)\n\n![b](50%25.png)\n\n![c](50%.png)\n\n![d](a(1).png)\n\n![e](a%281%29.png)\n\n"
        '<table><tr><td><img src="my%20pic.png" alt="f"></td><td><img src="50%25.png" alt="g"></td></tr></table>\n'
    )
    res = convert(Source(md.encode(), "a.md", Format.MD, base_dir=tmp_path), [Format.DOCX])
    assert res.outputs[0].data is not None
    assert not [e for e in res.report.events if e.code == Codes.IMAGE_FETCH_FAILED]


def test_import_prints_no_pandoc_warnings(tmp_path, caplog, capfd):
    import logging

    md = (
        "# 개요\n\n<table><tr><th>a</th><th>b</th></tr>"
        '<tr><td rowspan="2">x[^1]</td><td>y</td></tr><tr><td>z</td></tr></table>\n\n[^1]: 칸 각주\n'
    )
    data = strip_mdcast_metadata(export(tmp_path, md, Format.DOCX))
    capfd.readouterr()
    with caplog.at_level(logging.WARNING):
        res = convert(Source(data, "a.docx", Format.DOCX), [Format.MD])
    assert "[^t1]: 칸 각주" in res.outputs[0].data.decode()
    assert not [r for r in caplog.records if r.name == "pypandoc"]
    assert "[WARNING]" not in capfd.readouterr().err
