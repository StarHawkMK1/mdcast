from pathlib import Path

from helpers import write_template

from mdcast.report import Codes, Level, Report
from mdcast.templates import list_templates, resolve_template
from mdcast.types import Format


def resolve(ref, tmp_path: Path):
    report = Report("a.md", Format.MD)
    tpl = resolve_template(ref, cwd=tmp_path, home=tmp_path / "home", report=report)
    return tpl, report


def codes(report):
    return [e.code for e in report.events]


def project_dir(tmp_path: Path) -> Path:
    return tmp_path / ".mdcast" / "templates"


def test_no_ref_uses_builtin_default(tmp_path):
    tpl, r = resolve(None, tmp_path)
    assert (tpl.name, tpl.source) == ("default", "builtin")
    assert r.events == []
    assert tpl.config["page"]["size"] == "A4"
    assert tpl.container_for("docx").path is None
    assert tpl.container_for("pdf").path.name == "pdf.typ"


def test_unknown_name_warns_and_uses_default(tmp_path):
    tpl, r = resolve("no-such", tmp_path)
    assert tpl.source == "builtin"
    assert codes(r) == [Codes.TEMPLATE_NOT_FOUND]


def test_project_template_shadows_user_template(tmp_path):
    write_template(project_dir(tmp_path), "rep", "name: rep\nversion: 2.0.0\npage: {size: A3}\n")
    write_template(
        tmp_path / "home" / ".mdcast" / "templates", "rep", "name: rep\npage: {size: A5}\n"
    )
    tpl, r = resolve("rep", tmp_path)
    assert (tpl.source, tpl.version) == ("custom", "2.0.0")
    assert tpl.config["page"]["size"] == "A3"
    assert tpl.config["page"]["margin"]["top"] == "20mm"
    assert r.events == []


def test_path_with_spaces_and_korean(tmp_path):
    d = write_template(tmp_path / "양식 폴더", "보고서 양식", "name: 보고서\n")
    tpl, r = resolve(str(d), tmp_path)
    assert tpl.name == "보고서"
    assert tpl.location == d
    assert r.events == []


def test_relative_path_with_spaces_and_korean(tmp_path):
    write_template(tmp_path / "양식 폴더", "보고서 양식", "name: 보고서\n")
    tpl, r = resolve("./양식 폴더/보고서 양식", tmp_path)
    assert tpl.name == "보고서"
    assert r.events == []


def test_extends_merges_parent_then_child(tmp_path):
    write_template(
        project_dir(tmp_path),
        "base",
        "name: base\npage: {margin: {top: 30mm}}\ntables: {font_size: 9pt}\n",
    )
    write_template(
        project_dir(tmp_path), "child", "name: child\nextends: base\ntables: {font_size: 8pt}\n"
    )
    tpl, r = resolve("child", tmp_path)
    assert tpl.config["page"]["margin"]["top"] == "30mm"
    assert tpl.config["tables"]["font_size"] == "8pt"
    assert r.events == []


def test_extends_missing_parent_warns(tmp_path):
    write_template(project_dir(tmp_path), "child", "name: child\nextends: ghost\n")
    tpl, r = resolve("child", tmp_path)
    assert tpl.source == "custom"
    assert codes(r) == [Codes.TEMPLATE_NOT_FOUND]


def test_self_extends_warns(tmp_path):
    write_template(project_dir(tmp_path), "loop", "name: loop\nextends: loop\n")
    _, r = resolve("loop", tmp_path)
    assert codes(r) == [Codes.TEMPLATE_INVALID]


def test_multilevel_extends_warns(tmp_path):
    write_template(project_dir(tmp_path), "a", "name: a\n")
    write_template(project_dir(tmp_path), "b", "name: b\nextends: a\n")
    write_template(project_dir(tmp_path), "c", "name: c\nextends: b\n")
    _, r = resolve("c", tmp_path)
    assert codes(r) == [Codes.TEMPLATE_INVALID]


def test_broken_yaml_reports_and_keeps_custom_identity(tmp_path):
    write_template(project_dir(tmp_path), "broken", "page: [unclosed")
    tpl, r = resolve("broken", tmp_path)
    assert (tpl.source, tpl.name) == ("custom", "broken")
    assert tpl.config["page"]["size"] == "A4"
    assert codes(r) == [Codes.TEMPLATE_INVALID]


def test_container_fallback_is_info_for_yaml_headers(tmp_path):
    write_template(project_dir(tmp_path), "rep", "name: rep\n")
    tpl, r = resolve("rep", tmp_path)
    assert tpl.container_for("docx").source == "builtin"
    tpl.note_container_fallbacks("docx", r)
    assert [(e.level, e.code, e.where["format"]) for e in r.events] == [
        (Level.INFO, Codes.TEMPLATE_CONTAINER_FALLBACK, "docx")
    ]


def test_container_fallback_is_warn_for_reference_headers(tmp_path):
    write_template(project_dir(tmp_path), "rep", "name: rep\nheader: {source: reference}\n")
    tpl, r = resolve("rep", tmp_path)
    tpl.note_container_fallbacks("docx", r)
    assert r.events[0].level is Level.WARN


def test_custom_container_detected(tmp_path):
    write_template(project_dir(tmp_path), "rep", "name: rep\n", {"reference.docx": b"stub"})
    tpl, r = resolve("rep", tmp_path)
    assert tpl.container_for("docx").source == "custom"
    tpl.note_container_fallbacks("docx", r)
    assert r.events == []


def test_info_lists_per_format_sources(tmp_path):
    write_template(
        project_dir(tmp_path), "rep", "name: rep\nversion: 1.2.0\n", {"reference.docx": b"stub"}
    )
    tpl, _ = resolve("rep", tmp_path)
    info = tpl.info(["docx", "pdf"])
    assert info.source == "custom" and info.version == "1.2.0"
    assert info.per_format == {
        "docx": {"container": "custom", "styles": "custom"},
        "pdf": {"container": "builtin", "styles": "custom"},
    }


def test_list_templates_reports_origins(tmp_path):
    write_template(project_dir(tmp_path), "rep", "name: rep\n")
    write_template(tmp_path / "home" / ".mdcast" / "templates", "mine", "name: mine\n")
    entries = {(e.name, e.origin) for e in list_templates(tmp_path, tmp_path / "home")}
    assert {("rep", "project"), ("mine", "user"), ("default", "builtin")} <= entries


# --- controller rulings -------------------------------------------------


def test_invalid_child_value_falls_back_to_parent_value(tmp_path):
    write_template(project_dir(tmp_path), "base", "name: base\nelements: {body: {size: 12pt}}\n")
    write_template(
        project_dir(tmp_path),
        "child",
        "name: child\nextends: base\nelements: {body: {size: banana}}\n",
    )
    tpl, r = resolve("child", tmp_path)
    assert tpl.config["elements"]["body"]["size"] == "12pt"
    assert codes(r) == [Codes.TEMPLATE_INVALID]


def test_invalid_parent_value_falls_back_to_default(tmp_path):
    write_template(project_dir(tmp_path), "base", "name: base\nelements: {body: {size: banana}}\n")
    write_template(project_dir(tmp_path), "child", "name: child\nextends: base\n")
    tpl, r = resolve("child", tmp_path)
    assert tpl.config["elements"]["body"]["size"] == "11pt"
    assert codes(r) == [Codes.TEMPLATE_INVALID]


def test_explicit_holds_only_yaml_values(tmp_path):
    write_template(project_dir(tmp_path), "base", "name: base\npage: {margin: {top: 30mm}}\n")
    write_template(
        project_dir(tmp_path), "child", "name: child\nextends: base\ntables: {font_size: 8pt}\n"
    )
    tpl, _ = resolve("child", tmp_path)
    assert tpl.explicit["tables"]["font_size"] == "8pt"
    assert tpl.explicit["page"]["margin"]["top"] == "30mm"
    assert "left" not in tpl.explicit["page"]["margin"]
    assert "size" not in tpl.explicit["page"]
    assert "fonts" not in tpl.explicit
    for meta in ("name", "version", "extends", "files", "schema", "description"):
        assert meta not in tpl.explicit


def test_explicit_uses_sanitized_values(tmp_path):
    write_template(project_dir(tmp_path), "base", "name: base\nelements: {body: {size: 12pt}}\n")
    write_template(
        project_dir(tmp_path),
        "child",
        "name: child\nextends: base\nelements: {body: {size: banana}}\n",
    )
    tpl, _ = resolve("child", tmp_path)
    assert tpl.explicit["elements"]["body"]["size"] == "12pt"


def test_explicit_is_empty_for_builtin_default(tmp_path):
    tpl, _ = resolve(None, tmp_path)
    assert tpl.explicit == {}


def test_builtin_container_ignores_custom_files(tmp_path):
    write_template(project_dir(tmp_path), "rep", "name: rep\n", {"reference.docx": b"stub"})
    tpl, _ = resolve("rep", tmp_path)
    assert tpl.builtin_container("docx").path is None
    assert tpl.builtin_container("hwpx") == tpl.builtin_container("docx")
    pdf = tpl.builtin_container("pdf")
    assert pdf.source == "builtin" and pdf.path.name == "pdf.typ" and pdf.path.is_file()
