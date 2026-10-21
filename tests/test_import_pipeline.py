import shutil
from pathlib import Path

import panflute as pf
from docx_builder import strip_mdcast_metadata
from helpers import export
from hwpx_builder import cell, hwpx_bytes, p, run, tbl

from mdcast.ast import grid_cells
from mdcast.pipeline import convert
from mdcast.readers.hwpx import read_hwpx
from mdcast.readers.md import read_md
from mdcast.report import Codes, Level, Report
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


def test_pdf_input_still_unsupported():
    res = convert(Source(b"x", "a.pdf", Format.PDF), [Format.MD])
    events = [e for e in res.report.events if e.code == Codes.INPUT_UNSUPPORTED]
    assert events and "M3c" in events[0].message


def test_hwpx_converts_to_md_with_coverage():
    result = convert(Source(hwpx_bytes(p(run("본문 글"))), "a.hwpx", Format.HWPX), [Format.MD])
    assert result.outputs[0].data.decode().strip() == "본문 글" and result.report.coverage == 1.0


def test_hwpx_formatting_headings_and_page_break_reach_md():
    data = hwpx_bytes(
        p(run("개요"), para="1"),
        p(run("굵게", "1"), run(" 그리고 "), run("기울임", "2")),
        p(run("다음 쪽"), page_break=True),
        title="보고",
        meta={"creator": "홍"},
    )
    result = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
    md = result.outputs[0].data.decode()
    assert md.startswith("---\n") and "title: 보고" in md and "author: 홍" in md
    assert "# 개요" in md and "**굵게** 그리고 *기울임*" in md
    assert "<!-- pagebreak -->\n\n다음 쪽" in md
    assert result.report.coverage == 1.0


def test_empty_hwpx_gives_empty_md_and_one_heading_warning():
    result = convert(Source(hwpx_bytes(p()), "a.hwpx", Format.HWPX), [Format.MD])
    out = result.outputs[0]
    assert out.data is not None and out.data.decode().strip() == ""
    assert result.report.outputs[0]["status"] != "failed" and result.report.coverage == 1.0
    warnings = [(e.level, e.code) for e in result.report.events if e.level is not Level.INFO]
    assert warnings == [(Level.WARN, Codes.IMPORT_HEADING_INFERRED)]


def test_corrupt_hwpx_is_input_corrupt_without_traceback():
    for data in (b"PK\x03\x04broken", hwpx_bytes(p(run("a")), encrypted=True)):
        res = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
        errors = [e for e in res.report.events if e.level is Level.ERROR]
        assert [e.code for e in errors] == [Codes.INPUT_CORRUPT]
        assert errors[0].message.startswith("입력을 해석할 수 없습니다: ") and "Traceback" not in errors[0].message
        assert res.outputs[0].data is None and res.report.outputs[0]["status"] == "failed"
    assert "암호" in errors[0].message or "보안" in errors[0].message


def _hwpx_grid(table) -> list[list[tuple[str, int, int, int]]]:
    rows = list(table.head.content) + [row for body in table.content for row in body.content]
    starts = {id(c): col for c, col in grid_cells(rows)}
    return [[(pf.stringify(c).strip(), starts[id(c)], c.rowspan, c.colspan) for c in row.content] for row in rows]


def test_hwpx_table_spans_survive_md_round_trip():
    inner = tbl([[cell(p(run("안")), col=0, row=0), cell(p(run("쪽")), col=1, row=0)]], cols=2)
    rows = [
        [cell(p(run("구분")), col=0, row=0, rowspan=2), cell(p(run("값")), col=1, row=0, colspan=2)],
        [cell(p(run("상")), col=1, row=1), cell(p(run("하")), col=2, row=1)],
        [cell(p(run("x")), col=0, row=2), cell(p(inner), col=1, row=2, colspan=2)],
        [cell(p(run("y")), col=0, row=3, colspan=2), cell(p(run("z")), col=2, row=3)],
    ]
    data = hwpx_bytes(p(tbl(rows, cols=3)))
    report = Report("a.hwpx", Format.HWPX)
    source = read_hwpx(Source(data, "a.hwpx", Format.HWPX), report, "a_assets").doc.content[0]
    result = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc.content
    assert [type(b).__name__ for b in back] == ["Table"]
    assert _hwpx_grid(back[0]) == _hwpx_grid(source)
    assert len(back[0].head.content) == len(source.head.content) == 2
    nested = [e for e in back[0].content[0].content[0].content[1].content if isinstance(e, pf.Table)]
    assert len(nested) == 1 and _hwpx_grid(nested[0]) == [[("안", 0, 1, 1), ("쪽", 1, 1, 1)]]


def _cell_blocks(table) -> list[list[list[tuple[str, str]]]]:
    rows = list(table.head.content) + [row for body in table.content for row in body.content]
    return [
        [[(type(b).__name__, pf.stringify(b).strip()) for b in c.content] for c in row.content]
        for row in rows
    ]


def test_hwpx_multi_paragraph_cells_and_captions_survive_md_round_trip():
    inner = tbl([[cell(p(run("안")), col=0, row=0)]], cols=1)
    caption = (
        '<hp:caption side="BOTTOM" fullSz="0" width="8504" gap="850" lastWidth="8000">'
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP">'
        f"{p(run('제목 하나'))}{p(run('제목 둘'))}</hp:subList></hp:caption>"
    )
    rows = [
        [cell(p(run("머리 가")), col=0, row=0), cell(p(run("머리 나")), col=1, row=0)],
        [cell(p(run("첫 줄")), p(run("둘째 줄")), col=0, row=1), cell(p(run("하나")), col=1, row=1)],
        [cell(p(run("앞"), inner, run("뒤")), col=0, row=2), cell(p(run("글"), inner), col=1, row=2)],
    ]
    table = tbl(rows, cols=2).replace('<hp:pos treatAsChar="1"/>', '<hp:pos treatAsChar="1"/>' + caption)
    data = hwpx_bytes(p(table))
    report = Report("a.hwpx", Format.HWPX)
    source = read_hwpx(Source(data, "a.hwpx", Format.HWPX), report, "a_assets").doc.content[0]
    result = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc.content
    assert [type(b).__name__ for b in back] == ["Table"]
    assert _cell_blocks(source)[1][0] == [("Para", "첫 줄"), ("Para", "둘째 줄")]
    assert _cell_blocks(back[0]) == _cell_blocks(source)
    caption_blocks = [(type(b).__name__, pf.stringify(b).strip()) for b in back[0].caption.content]
    assert caption_blocks == [("Para", "제목 하나"), ("Para", "제목 둘")]


def test_hwpx_footnote_in_table_cell_survives_md_round_trip():
    footnote = (
        '<hp:run charPrIDRef="0"><hp:ctrl><hp:footNote number="1" suffixChar="41" instId="1">'
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP">'
        f"{p(run('칸 각주 글'))}</hp:subList></hp:footNote></hp:ctrl></hp:run>"
    )
    rows = [
        [cell(p(run("머리")), col=0, row=0)],
        [cell(p(run("칸 글"), footnote), col=0, row=1)],
    ]
    data = hwpx_bytes(p(tbl(rows, cols=1)))
    result = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0
    md = result.outputs[0].data.decode()
    assert "[^" in md and "<td>" in md  # a note label in an HTML cell (M3a D9)
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc
    assert [type(b).__name__ for b in back.content] == ["Table"]
    in_cell = back.content[0].content[0].content[0].content[0]
    notes = []
    in_cell.walk(lambda e, _d: notes.append(e) if isinstance(e, pf.Note) else None)
    assert [pf.stringify(n).strip() for n in notes] == ["칸 각주 글"]


def test_hwpx_equation_alone_in_a_cell_note_stays_a_code_block():
    equation = '<hp:run charPrIDRef="0"><hp:equation id="1"><hp:script>q over r</hp:script></hp:equation></hp:run>'
    footnote = (
        '<hp:run charPrIDRef="0"><hp:ctrl><hp:footNote number="1" suffixChar="41" instId="1">'
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP">'
        f"{p(equation)}{p(run('설명'))}</hp:subList></hp:footNote></hp:ctrl></hp:run>"
    )
    rows = [[cell(p(run("머리")), col=0, row=0)], [cell(p(run("칸"), footnote), col=0, row=1)]]
    data = hwpx_bytes(p(tbl(rows, cols=1)))
    result = convert(Source(data, "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0
    back = read_md(Source(result.outputs[0].data, "a.md", Format.MD), Report("a.md", Format.MD)).doc
    notes = []
    back.walk(lambda e, _d: notes.append(e) if isinstance(e, pf.Note) else None)
    assert [(type(b).__name__, pf.stringify(b).strip()) for b in notes[0].content] == [
        ("CodeBlock", "q over r"),
        ("Para", "설명"),
    ]


def test_hwpx_to_docx_is_target_unsupported():
    res = convert(Source(hwpx_bytes(p(run("a"))), "a.hwpx", Format.HWPX), [Format.DOCX, Format.MD])
    errors = [e for e in res.report.events if e.code == Codes.TARGET_UNSUPPORTED]
    assert len(errors) == 1 and errors[0].where.get("format") == "docx"
    assert errors[0].message == "hwpx 입력은 md 로만 변환합니다 (간접 변환은 아직 지원하지 않습니다)"
    outs = {o.format: o for o in res.outputs}
    assert outs[Format.DOCX].data is None and outs[Format.MD].data.decode().strip() == "a"


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
