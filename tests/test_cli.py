import json
import os
import subprocess
import sys

import pytest
from click.testing import CliRunner
from helpers import write_template

from mdcast.cli import main


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return tmp_path


def run(*args):
    return CliRunner().invoke(main, list(args))


def write_md(env, name="보고 서.md", text="---\ntitle: 사업계획\n---\n\n# 개요\n\n본문\n"):
    path = env / name
    path.write_text(text, encoding="utf-8")
    return path


def test_convert_writes_files_and_summary(env):
    r = run("convert", str(write_md(env)), "--to", "docx,pdf", "--offline")
    assert r.exit_code == 0, r.output
    assert (env / "보고 서.docx").is_file() and (env / "보고 서.pdf").is_file()
    assert "템플릿: default v1.0.0 (내장)" in r.output


def test_convert_json_report(env):
    r = run("convert", str(write_md(env)), "--to", "docx", "--json")
    data = json.loads(r.output)
    assert data["outputs"][0]["status"] == "ok"
    assert data["template"]["source"] == "builtin"


def test_out_dir(env):
    r = run("convert", str(write_md(env)), "--out-dir", str(env / "out 폴더"))
    assert r.exit_code == 0
    assert (env / "out 폴더" / "보고 서.docx").is_file()


def test_unsupported_target_exits_1_but_writes_others(env):
    r = run("convert", str(write_md(env)), "--to", "docx,hwpx")
    assert r.exit_code == 1
    assert (env / "보고 서.docx").is_file()
    assert "✖ 보고 서.hwpx" in r.output


def test_unknown_format_is_usage_error(env):
    r = run("convert", str(write_md(env)), "--to", "txt")
    assert r.exit_code == 2


def test_custom_template_label_shows_container_fallback(env):
    write_template(env / ".mdcast" / "templates", "rep", "name: rep\nversion: 1.2.0\n")
    r = run("convert", str(write_md(env)), "--template", "rep")
    assert "템플릿: rep v1.2.0 (커스텀 · 그릇은 내장)" in r.output


def test_verbose_shows_info_and_quiet_hides_it(env):
    md = write_md(env, text="본문\n")
    assert "ℹ" in run("convert", str(md), "--verbose").output
    quiet = run("convert", str(md), "--quiet").output
    assert "ℹ" not in quiet and "✔" not in quiet


def test_template_list_describe_validate(env):
    write_template(env / ".mdcast" / "templates", "rep", "name: rep\nheader: {left: '{{dept}}'}\n")
    assert "rep\t프로젝트" in run("template", "list").output
    described = json.loads(run("template", "describe", "rep").output)
    assert described["fields"] == ["dept", "title"]  # right slot {{title}} is inherited from default
    write_template(env / ".mdcast" / "templates", "broken", "page: [unclosed")
    r = run("template", "validate", "broken")
    assert r.exit_code == 0 and "⚠" in r.output


def test_template_path_with_spaces_and_korean(env):
    write_template(env / "양식 폴더", "rep", "name: rep\nversion: 2.0.0\n")
    r = run("convert", str(write_md(env)), "--template", "./양식 폴더/rep")
    assert r.exit_code == 0, r.output
    assert "템플릿: rep v2.0.0 (커스텀 · 그릇은 내장)" in r.output
    assert (env / "보고 서.docx").is_file()
    assert run("template", "describe", "./양식 폴더/rep").exit_code == 0
    assert run("template", "validate", "./양식 폴더/rep").exit_code == 0


def test_unexpected_exception_is_korean_error_not_traceback(env, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("mdcast.pipeline.convert", boom)
    r = run("convert", str(write_md(env)))
    assert r.exit_code == 1
    assert "변환 중 오류" in r.output and "kaboom" in r.output and "Traceback" not in r.output


def test_version_and_help_are_korean():
    assert "mdcast 버전 0.1.0" in run("--version").output
    helped = run("--help").output
    assert "도움말을 표시하고 종료합니다." in helped and "템플릿 기반 변환기" in helped
    assert "convert" in helped and "template" in helped


def test_help_and_version_survive_piped_legacy_console():
    clean = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    for args, expected in ((["--help"], "템플릿 기반 변환기"), (["--version"], "mdcast 버전")):
        proc = subprocess.run([sys.executable, "-m", "mdcast", *args], capture_output=True, env=clean, timeout=60, check=False)
        assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
        assert expected in proc.stdout.decode("utf-8")
