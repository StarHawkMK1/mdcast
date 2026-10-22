from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import click

from mdcast import __version__, pipeline
from mdcast.report import Codes, Event, Level, Report
from mdcast.templates import describe_template, list_templates, resolve_template, validate_template
from mdcast.types import Format, Options, Source

_STATUS = {"ok": "✔", "degraded": "⚠", "failed": "✖"}
_LEVEL = {Level.ERROR: "✖", Level.WARN: "⚠", Level.INFO: "ℹ"}
_ORIGIN = {"project": "프로젝트", "user": "사용자", "builtin": "내장"}


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _event_line(event: Event) -> str:
    location = []
    if "format" in event.where:
        location.append(str(event.where["format"]))
    if "line" in event.where:
        location.append(f"{event.where['line']}행")
    prefix = (" · ".join(location) + ": ") if location else ""
    return f"  {_LEVEL[event.level]} {prefix}{event.message}"


def render_human(report: Report, *, verbose: bool, quiet: bool) -> str:
    lines: list[str] = []
    info = report.template
    for output in report.outputs:
        if quiet and output["status"] != "failed":
            continue
        line = f"{_STATUS[output['status']]} {output['name']}"
        if info is not None:
            label = "커스텀" if info.source == "custom" else "내장"
            per_format = info.per_format.get(output["format"], {})
            if info.source == "custom" and output["format"] != "pdf" and per_format.get("container") == "builtin":
                label += " · 그릇은 내장"
            line += f"  템플릿: {info.name} v{info.version} ({label})"
        lines.append(line)
        if report.coverage is not None and output["format"] == "md" and output["status"] != "failed":
            lines.append(f"  내용 보존 {report.coverage:.1%}")
    for event in report.events:
        if event.level is Level.INFO and not verbose:
            continue
        if quiet and event.level is not Level.ERROR:
            continue
        lines.append(_event_line(event))
    hidden = sum(1 for e in report.events if e.level is Level.INFO)
    if hidden and not verbose and not quiet:
        lines.append(f"  ℹ 정보 {hidden}건 (--verbose 로 보기)")
    if report.temp_dir and not quiet:
        lines.append(f"  임시 폴더: {report.temp_dir}")
    return "\n".join(lines)


class _Group(click.Group):
    """Switches the console to UTF-8 before click parses anything, so eager --help/--version are covered."""

    def main(self, *args, **kwargs):
        _utf8_console()
        return super().main(*args, **kwargs)


@click.group(cls=_Group)
@click.version_option(
    __version__,
    prog_name="mdcast",
    message="%(prog)s 버전 %(version)s",
    help="버전 정보를 표시하고 종료합니다.",
)
@click.help_option(help="도움말을 표시하고 종료합니다.")
def main() -> None:
    """mdcast — Markdown ↔ docx · hwpx · pdf, 템플릿 기반 변환기."""


def _refuse_existing(result, destination: Path, force: bool) -> None:
    """Import never overwrites by surprise: nothing is written when x.md or x_assets/ is already there."""
    for output in result.outputs:
        if output.data is None or output.format is not Format.MD:
            continue
        stem = Path(output.name).stem
        clashes = [n for n in (output.name, f"{stem}_assets") if (destination / n).exists()]
        if not clashes:
            continue
        if force:
            shutil.rmtree(destination / f"{stem}_assets", ignore_errors=True)
            continue
        result.report.error(
            Codes.OUTPUT_EXISTS,
            f"{clashes[0]} 이(가) 이미 있습니다. 덮어쓰려면 --force 를 주세요",
            format=output.format.value,
        )
        output.data = None


@main.command()
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--to", "to", default=None, help="출력 포맷, 쉼표로 구분 (기본: md 입력은 docx, 그 밖은 md)")
@click.option("--template", default=None, help="템플릿 이름 또는 폴더 경로")
@click.option("--out-dir", type=click.Path(file_okay=False, path_type=Path), default=None, help="출력 폴더 (기본: 입력 파일 폴더)")
@click.option("--json", "as_json", is_flag=True, help="리포트를 JSON 으로 출력")
@click.option("--verbose", is_flag=True, help="정보(ℹ) 이벤트까지 모두 표시")
@click.option("--quiet", is_flag=True, help="실패만 표시")
@click.option("--keep-temp", is_flag=True, help="중간 산출물(AST, Typst 소스 등)을 남김")
@click.option("--offline", is_flag=True, help="외부 이미지를 내려받지 않음")
@click.option("--force", is_flag=True, help="가져오기 결과(.md, _assets 폴더)가 이미 있어도 덮어씀")
def convert(input_path, to, template, out_dir, as_json, verbose, quiet, keep_temp, offline, force) -> None:
    """MD 를 docx·hwpx·pdf 로, docx·hwpx·pdf 를 MD 로 변환합니다."""
    if input_path.suffix.lower() == ".hwp":
        raise click.UsageError("hwp 파일은 지원하지 않습니다. 한글에서 hwpx 로 저장해 넣으세요")
    try:
        source_format = Format.from_filename(input_path.name)
    except ValueError:
        raise click.UsageError(f"지원하지 않는 입력 형식: {input_path.name} (.md, .docx, .hwpx 파일을 지정하세요)") from None
    if to is None:
        to = "docx" if source_format is Format.MD else "md"
    targets = []
    for name in (t.strip() for t in to.split(",")):
        if not name:
            continue
        try:
            targets.append(Format.parse(name))
        except ValueError:
            raise click.UsageError(f"지원하지 않는 형식: {name} (md, docx, hwpx, pdf 중 선택)") from None
    if not targets:
        raise click.UsageError("--to 에 출력 포맷을 지정하세요")
    try:
        data = input_path.read_bytes()
    except OSError as exc:
        click.echo(f"✖ 입력 파일을 읽지 못했습니다: {exc}", err=True)
        sys.exit(1)
    source = Source(data, input_path.name, source_format, base_dir=input_path.parent.resolve())
    options = Options(offline=offline, keep_temp=keep_temp, cwd=Path.cwd(), home=Path.home())
    try:
        result = pipeline.convert(source, targets, template, options)
    except Exception as exc:  # noqa: BLE001 - never show a raw traceback to the user
        click.echo(f"✖ 변환 중 오류가 발생했습니다: {exc}", err=True)
        sys.exit(1)
    destination = out_dir or input_path.parent
    importing = source_format is not Format.MD
    if importing:
        _refuse_existing(result, destination, force)
    for output in result.outputs:
        if output.data is None:
            continue
        try:
            destination.mkdir(parents=True, exist_ok=True)
            (destination / output.name).write_bytes(output.data)
            root = (destination / f"{Path(output.name).stem}_assets").resolve()
            for key, blob in output.assets.items():
                target = destination / key
                if not target.resolve().is_relative_to(root):
                    result.report.warn(
                        Codes.RENDER_WARNING, f"그림 경로가 그림 폴더 밖을 가리켜 저장하지 않습니다: {key}", format=output.format.value
                    )
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob)
        except OSError as exc:
            result.report.error(Codes.OUTPUT_WRITE_FAILED, f"{output.name} 을(를) 저장하지 못했습니다: {exc}", format=output.format.value)
            output.data = None
    result.report.set_outputs(result.outputs)
    if as_json:
        click.echo(json.dumps(result.report.to_dict(), ensure_ascii=False, indent=2))
    else:
        text = render_human(result.report, verbose=verbose, quiet=quiet)
        if text:
            click.echo(text)
    sys.exit(1 if any(o["status"] == "failed" for o in result.report.outputs) else 0)


@main.group()
def template() -> None:
    """템플릿 목록·설명·검증."""


@template.command("list")
def template_list() -> None:
    """사용 가능한 템플릿과 출처를 보여 줍니다."""
    for entry in list_templates(Path.cwd(), Path.home()):
        click.echo(f"{entry.name}\t{_ORIGIN.get(entry.origin, entry.origin)}\t{entry.path}")


@template.command("describe")
@click.argument("ref")
def template_describe(ref: str) -> None:
    """템플릿의 필드 키·지원 포맷·그릇 출처를 JSON 으로 보여 줍니다."""
    report = Report(ref, Format.MD)
    tpl = resolve_template(ref, cwd=Path.cwd(), home=Path.home(), report=report)
    data = describe_template(tpl)
    if report.events:
        data["events"] = [e.to_dict() for e in report.events]
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


@template.command("validate")
@click.argument("ref")
@click.option("--json", "as_json", is_flag=True, help="리포트를 JSON 으로 출력")
def template_validate(ref: str, as_json: bool) -> None:
    """템플릿을 점검합니다. 문제가 있어도 실패하지 않고 경고만 보여 줍니다."""
    _, report = validate_template(ref, cwd=Path.cwd(), home=Path.home())
    if as_json:
        click.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return
    if not any(e.level is not Level.INFO for e in report.events):
        click.echo(f"✔ {ref}: 문제 없음")
    for event in report.events:
        click.echo(_event_line(event))
