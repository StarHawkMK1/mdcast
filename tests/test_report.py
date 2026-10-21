import pytest

from mdcast.report import Codes, Level, Report, TemplateInfo
from mdcast.types import Format, Output


def new_report() -> Report:
    return Report("a.md", Format.MD)


def test_info_only_is_ok():
    r = new_report()
    r.info(Codes.FIELD_EMPTY, "x")
    assert r.status_for(Format.DOCX) == "ok"


def test_global_warning_degrades_every_format():
    r = new_report()
    r.warn(Codes.TEMPLATE_NOT_FOUND, "x")
    assert r.status_for(Format.DOCX) == "degraded"
    assert r.status_for(Format.PDF) == "degraded"


def test_format_warning_only_degrades_that_format():
    r = new_report()
    r.warn(Codes.FONT_FALLBACK, "x", format="pdf")
    assert r.status_for(Format.DOCX) == "ok"
    assert r.status_for(Format.PDF) == "degraded"


def test_format_error_fails_only_that_format():
    r = new_report()
    r.error(Codes.RENDER_FAILED, "x", format="pdf")
    assert r.status_for(Format.PDF) == "failed"
    assert r.status_for(Format.DOCX) == "ok"


def test_global_error_fails_everything():
    r = new_report()
    r.error(Codes.INPUT_CORRUPT, "x")
    assert r.status_for(Format.DOCX) == "failed"


def test_once_deduplicates_identical_events():
    r = new_report()
    r.info(Codes.FIELD_EMPTY, "x", once=True, field="dept")
    r.info(Codes.FIELD_EMPTY, "x", once=True, field="dept")
    assert len(r.events) == 1
    assert r.events[0].level is Level.INFO


def test_set_outputs_marks_missing_data_failed():
    r = new_report()
    r.set_outputs([Output(Format.DOCX, "a.docx", b"x"), Output(Format.PDF, "a.pdf", None)])
    assert r.outputs == [
        {"format": "docx", "name": "a.docx", "status": "ok"},
        {"format": "pdf", "name": "a.pdf", "status": "failed"},
    ]


def test_to_dict_shape():
    r = new_report()
    r.template = TemplateInfo("rep", "1.0.0", "custom", "/t/rep", {"docx": {"container": "custom", "styles": "custom"}})
    r.warn(Codes.TEMPLATE_INVALID, "bad", key="page.size")
    r.set_outputs([Output(Format.DOCX, "a.docx", b"x")])
    d = r.to_dict()
    assert d["input"] == {"name": "a.md", "format": "md"}
    assert d["template"]["source"] == "custom"
    assert d["template"]["per_format"]["docx"]["container"] == "custom"
    assert d["events"] == [
        {"level": "warn", "code": "TEMPLATE_INVALID", "message": "bad", "where": {"key": "page.size"}}
    ]
    assert d["outputs"][0]["status"] == "degraded"


def test_format_parsing():
    assert Format.parse(" PDF ") is Format.PDF
    assert Format.from_filename("보고서.MD") is Format.MD
    assert Format.from_filename("x.markdown") is Format.MD
    with pytest.raises(ValueError):
        Format.from_filename("x.txt")


def test_coverage_is_reported_only_when_measured():
    r = Report("a.docx", Format.DOCX)
    assert "coverage" not in r.to_dict()
    r.coverage = 0.9875
    assert r.to_dict()["coverage"] == 0.9875


def test_import_codes_exist():
    for name in ("IMPORT_HEADING_INFERRED", "IMPORT_LIST_INFERRED", "IMPORT_TEXT_MISSING",
                 "IMPORT_IMAGE_TEXT", "IMPORT_HEADER_SKIPPED", "IMAGE_CONVERT_FAILED", "OUTPUT_EXISTS",
                 "HWPX_EQUATION_PRESERVED", "IMPORT_OBJECT_SKIPPED", "IMPORT_SYMBOL_MAPPED",
                 "IMPORT_TABLE_UNWRAPPED"):
        assert getattr(Codes, name) == name
