import shutil
from pathlib import Path

from docx_builder import strip_mdcast_metadata
from helpers import export

from mdcast.pipeline import convert
from mdcast.report import Codes
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
