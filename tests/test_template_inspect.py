from helpers import make_reference_docx, write_template

from mdcast.report import Codes, Report
from mdcast.templates import describe_template, resolve_template, validate_template
from mdcast.types import Format


def resolve(ref, tmp_path):
    return resolve_template(ref, cwd=tmp_path, home=tmp_path / "home", report=Report("t", Format.MD))


def test_describe_lists_fields_from_slots_and_defaults(tmp_path):
    tpl_dir = write_template(
        tmp_path, "t",
        "name: t\nheader: {left: '{{dept}}', right: '{{security}}'}\nfields: {defaults: {owner: 김}}\n",
    )
    info = describe_template(resolve(str(tpl_dir), tmp_path))
    assert info["fields"] == ["dept", "security", "owner"]
    assert "page" in info["reserved_fields"]
    assert info["formats"]["pdf"]["container"] == "builtin"
    assert info["supported_targets"] == ["docx", "hwpx", "pdf"]


def test_describe_reads_reference_docx_placeholders(tmp_path):
    tpl_dir = write_template(tmp_path, "t", "name: t\nheader: {source: reference}\n")
    make_reference_docx(tpl_dir / "reference.docx", header_runs=["{{de", "pt}} {{page}}"])
    info = describe_template(resolve(str(tpl_dir), tmp_path))
    assert "dept" in info["fields"] and "page" not in info["fields"]


def test_describe_survives_corrupt_reference_docx(tmp_path):
    tpl_dir = write_template(
        tmp_path, "t", "name: t\nheader: {source: reference}\n", {"reference.docx": b"not a zip"}
    )
    info = describe_template(resolve(str(tpl_dir), tmp_path))
    assert info["fields"] == []
    assert info["header_source"] == "reference"


def test_validate_reports_missing_style_and_font(tmp_path):
    tpl_dir = write_template(
        tmp_path, "t",
        "name: t\nstyles: {heading1: {docx: 없는스타일}}\nfonts: {body: {family: 없는글꼴xyz}}\n",
    )
    make_reference_docx(tpl_dir / "reference.docx")
    _, report = validate_template(str(tpl_dir), cwd=tmp_path, home=tmp_path / "home")
    found = [e.code for e in report.events]
    assert Codes.STYLE_UNMAPPED in found and Codes.FONT_FALLBACK in found


def test_validate_present_custom_style_is_clean(tmp_path):
    tpl_dir = write_template(tmp_path, "t", "name: t\nstyles: {heading1: {docx: 내제목}}\n")
    make_reference_docx(tpl_dir / "reference.docx", extra_styles=("내제목",))
    _, report = validate_template(str(tpl_dir), cwd=tmp_path, home=tmp_path / "home")
    assert Codes.STYLE_UNMAPPED not in [e.code for e in report.events]


def test_validate_broken_template_never_raises(tmp_path):
    tpl_dir = write_template(tmp_path, "t", "page: [unclosed", {"reference.docx": b"not a zip"})
    _, report = validate_template(str(tpl_dir), cwd=tmp_path, home=tmp_path / "home")
    assert Codes.TEMPLATE_INVALID in [e.code for e in report.events]


def test_validate_corrupt_reference_docx_is_a_warning(tmp_path):
    tpl_dir = write_template(tmp_path, "t", "name: t\n", {"reference.docx": b"not a zip"})
    _, report = validate_template(str(tpl_dir), cwd=tmp_path, home=tmp_path / "home")
    codes = [e.code for e in report.events]
    assert Codes.TEMPLATE_INVALID in codes


def test_validate_missing_template_falls_back(tmp_path):
    tpl, report = validate_template("nope", cwd=tmp_path, home=tmp_path / "home")
    assert tpl.source == "builtin"
    assert Codes.TEMPLATE_NOT_FOUND in [e.code for e in report.events]
