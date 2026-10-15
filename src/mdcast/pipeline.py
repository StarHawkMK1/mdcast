from __future__ import annotations

import contextlib
import importlib.metadata
import tempfile
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import panflute as pf

from mdcast import __version__
from mdcast.ast import clone, pandoc_version
from mdcast.fields import ResolvedFields, resolve_fields
from mdcast.filters import FilterContext, run_filters
from mdcast.readers.md import read_md
from mdcast.report import Codes, Report
from mdcast.templates import ResolvedTemplate, resolve_template
from mdcast.templates.resolve import looks_like_path
from mdcast.types import Format, Options, Output, Result, Source
from mdcast.writers.context import RenderError, WriterContext
from mdcast.writers.docx import write_docx
from mdcast.writers.pdf import write_pdf

WRITERS: dict[Format, Callable[[pf.Doc, WriterContext], bytes]] = {
    Format.DOCX: write_docx,
    Format.PDF: write_pdf,
}


def output_name(source_name: str, target: Format) -> str:
    return f"{Path(source_name).stem}.{target.value}"


def build_generator(tpl: ResolvedTemplate) -> dict[str, Any]:
    return {
        "generator": f"mdcast {__version__}",
        "pandoc": pandoc_version(),
        "typst": importlib.metadata.version("typst"),
        "template": {"name": tpl.name, "version": tpl.version, "source": tpl.source},
    }


def prepare_target(
    document: Any,
    target: Format,
    tpl: ResolvedTemplate,
    fields: ResolvedFields,
    report: Report,
    options: Options,
    base_dir: Path | None,
    work_dir: Path,
    generator: dict[str, Any],
) -> tuple[pf.Doc, WriterContext]:
    """Per-target preparation shared by convert() and tests: own AST copy, filters, writer context."""
    tpl.note_container_fallbacks(target.value, report)
    work_dir.mkdir(parents=True, exist_ok=True)
    fctx = FilterContext(target, tpl.config, document.frontmatter, report)
    doc = run_filters(clone(document.doc), fctx)
    ctx = WriterContext(
        target=target,
        template=tpl,
        fields=fields,
        report=report,
        options=options,
        base_dir=base_dir,
        work_dir=work_dir,
        state=fctx.state,
        generator=generator,
    )
    return doc, ctx


@contextlib.contextmanager
def _workspace(options: Options, report: Report) -> Iterator[Path]:
    if options.keep_temp:
        path = Path(tempfile.mkdtemp(prefix="mdcast-", dir=options.temp_root))
        report.temp_dir = str(path)
        yield path
        return
    with tempfile.TemporaryDirectory(prefix="mdcast-", dir=options.temp_root) as tmp:
        yield Path(tmp)


def convert(
    source: Source,
    targets: Sequence[Format],
    template: str | None = None,
    options: Options | None = None,
) -> Result:
    options = options or Options()
    report = Report(source.name, source.format)
    outputs = [Output(t, output_name(source.name, t), None) for t in dict.fromkeys(targets)]

    if source.format is not Format.MD:
        report.error(Codes.INPUT_UNSUPPORTED, f"{source.format.value} 입력 변환은 아직 지원하지 않습니다 (M3 예정)")
        report.set_outputs(outputs)
        return Result(outputs, report)
    try:
        document = read_md(source, report)
    except Exception as exc:  # noqa: BLE001 - unreadable input fails every target
        report.error(Codes.INPUT_CORRUPT, f"입력을 해석할 수 없습니다: {exc}")
        report.set_outputs(outputs)
        return Result(outputs, report)

    cwd, home = options.cwd or Path.cwd(), options.home or Path.home()
    formats = [o.format.value for o in outputs]
    try:
        ref = template
        if ref is None and document.frontmatter.get("template"):
            ref = str(document.frontmatter["template"])
            # a path written in the document is relative to the document, like its images
            if looks_like_path(ref) and not Path(ref).is_absolute() and source.base_dir is not None:
                ref = str(source.base_dir / ref)
        tpl = resolve_template(ref, cwd=cwd, home=home, report=report)
        report.template = tpl.info(formats)
    except Exception as exc:  # noqa: BLE001 - a broken template must not stop the conversion
        report.warn(Codes.TEMPLATE_INVALID, f"템플릿을 불러오는 중 예기치 않은 오류로 내장 기본 템플릿을 씁니다: {exc!r}")
        try:
            tpl = resolve_template(None, cwd=cwd, home=home, report=report)
            report.template = tpl.info(formats)
        except Exception as exc2:  # noqa: BLE001
            report.error(Codes.RENDER_FAILED, f"내장 기본 템플릿도 불러올 수 없어 변환하지 못했습니다: {exc2!r}")
            report.set_outputs(outputs)
            return Result(outputs, report)
    try:
        fields = resolve_fields(document.frontmatter, tpl.config, report)
    except Exception as exc:  # noqa: BLE001
        report.warn(Codes.RENDER_WARNING, f"필드 값을 정리하는 중 예기치 않은 오류로 필드를 빈칸으로 둡니다: {exc!r}")
        fields = ResolvedFields({}, report)
    try:
        generator = build_generator(tpl)
    except Exception as exc:  # noqa: BLE001
        report.warn(Codes.RENDER_WARNING, f"생성 정보를 모으는 중 예기치 않은 오류로 mdcast 버전만 기록합니다: {exc!r}")
        generator = {"mdcast": __version__}

    # only entering the workspace can fail the conversion; a cleanup error at exit must not
    # discard outputs that are already built
    workspace = contextlib.ExitStack()
    try:
        root = workspace.enter_context(_workspace(options, report))
    except Exception as exc:  # noqa: BLE001
        report.error(Codes.RENDER_FAILED, f"임시 작업 폴더를 만들 수 없어 변환하지 못했습니다: {exc!r}")
        report.set_outputs(outputs)
        return Result(outputs, report)
    try:
        for output in outputs:
            target = output.format
            writer = WRITERS.get(target)
            if writer is None:
                report.error(Codes.TARGET_UNSUPPORTED, f"{target.value} 출력은 아직 지원하지 않습니다", format=target.value)
                continue
            try:
                doc, wctx = prepare_target(
                    document, target, tpl, fields, report, options, source.base_dir, root / target.value, generator
                )
                output.data = writer(doc, wctx)
            except RenderError as exc:
                report.error(Codes.RENDER_FAILED, f"{target.value} 생성 실패: {exc}", format=target.value)
            except Exception as exc:  # noqa: BLE001 - one target must not take down the others
                report.error(Codes.RENDER_FAILED, f"{target.value} 생성 중 예기치 않은 오류: {exc!r}", format=target.value)
    finally:
        try:
            workspace.close()
        except Exception as exc:  # noqa: BLE001
            report.info(Codes.RENDER_WARNING, f"임시 작업 폴더를 지우지 못했습니다: {exc!r}")

    report.set_outputs(outputs)
    return Result(outputs, report)
