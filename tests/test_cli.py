import json
import os
import subprocess
import sys
from pathlib import Path

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


def test_unsupported_target_exits_1_but_writes_others(env, monkeypatch):
    from mdcast import pipeline
    from mdcast.types import Format

    monkeypatch.delitem(pipeline.WRITERS, Format.HWPX)
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


def test_output_write_failure_exits_1_and_reports(env, monkeypatch):
    md = write_md(env)
    real = Path.write_bytes

    def flaky(self, data):
        if self.name == "보고 서.docx":
            raise PermissionError("denied")
        return real(self, data)

    monkeypatch.setattr(Path, "write_bytes", flaky)
    human = run("convert", str(md), "--to", "docx,pdf", "--offline")
    assert human.exit_code == 1
    assert "✖ 보고 서.docx" in human.output
    assert not (env / "보고 서.docx").exists() and (env / "보고 서.pdf").is_file()
    data = json.loads(run("convert", str(md), "--to", "docx", "--json").output)
    assert data["outputs"][0]["status"] == "failed"
    assert any(e["code"] == "OUTPUT_WRITE_FAILED" and e["level"] == "error" for e in data["events"])


def test_out_dir_under_regular_file_fails_cleanly(env):
    blocker = env / "파일"
    blocker.write_text("x", encoding="utf-8")
    r = run("convert", str(write_md(env)), "--out-dir", str(blocker / "sub"))
    assert r.exit_code == 1 and "✖" in r.output


def test_unreadable_input_is_korean_error(env, monkeypatch):
    md = write_md(env)

    def deny(self):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_bytes", deny)
    r = run("convert", str(md))
    assert r.exit_code == 1
    assert "입력 파일을 읽지 못했습니다" in r.output and "Traceback" not in r.output


def test_frontmatter_template_path_is_relative_to_the_document(env):
    docs = env / "docs"
    write_template(docs, "양식", "name: doc-form\n")
    path = write_md(docs, "보고서.md", "---\ntemplate: ./양식\n---\n\n본문\n")
    r = run("convert", str(path.relative_to(env)), "--offline")
    assert r.exit_code == 0, r.output
    assert "템플릿: doc-form" in r.output
    assert "찾지 못해" not in r.output


def test_first_run_shows_no_panflute_syntax_warning(tmp_path):
    # a fresh bytecode cache makes Python compile panflute from source, as on the first run after install
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONWARNINGS", "PYTHONDONTWRITEBYTECODE")}
    proc = subprocess.run(
        [sys.executable, "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-m", "mdcast", "--version"],
        capture_output=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0
    assert b"SyntaxWarning" not in proc.stderr, proc.stderr.decode("utf-8", "replace")


def test_unknown_format_message_is_korean_only(env):
    r = run("convert", str(write_md(env)), "--to", "txt")
    assert r.exit_code == 2
    assert "지원하지 않는 형식: txt (docx, pdf 중 선택)" in r.output
    assert "is not a valid" not in r.output


def test_quiet_success_prints_nothing(env):
    r = run("convert", str(write_md(env)), "--quiet", "--offline")
    assert r.exit_code == 0
    assert r.output == ""
