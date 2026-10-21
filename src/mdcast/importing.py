from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from mdcast.coverage import measure_coverage
from mdcast.filters.importing import ImportContext, run_import_filters
from mdcast.readers.docx import read_docx
from mdcast.readers.hwpx import read_hwpx
from mdcast.readers.imported import ImportedDocument
from mdcast.report import Codes, Report
from mdcast.types import Format, Options, Output, Result, Source
from mdcast.writers.md import write_md

READERS: dict[Format, Callable[[Source, Report, str], ImportedDocument]] = {
    Format.DOCX: read_docx,
    Format.HWPX: read_hwpx,
}


def import_document(
    source: Source, targets: Sequence[Format], options: Options, template: str | None = None
) -> Result:
    """docx·hwpx → MD. Only MD is a valid target; the images go along as ``{stem}_assets/{name}``."""
    report = Report(source.name, source.format)
    stem = Path(source.name).stem
    outputs = [Output(t, f"{stem}.{t.value}", None) for t in dict.fromkeys(targets)]
    if template:
        report.info(Codes.RENDER_WARNING, f"가져오기에서는 템플릿을 쓰지 않습니다 (지정한 템플릿 '{template}' 무시)")

    for output in outputs:
        if output.format is not Format.MD:
            report.error(
                Codes.TARGET_UNSUPPORTED,
                f"{source.format.value} 입력은 md 로만 변환합니다 (간접 변환은 아직 지원하지 않습니다)",
                format=output.format.value,
            )
    md_output = next((o for o in outputs if o.format is Format.MD), None)
    if md_output is None:
        report.set_outputs(outputs)
        return Result(outputs, report)

    assets_dir = f"{stem}_assets"
    try:
        imp = READERS[source.format](source, report, assets_dir)
    except Exception as exc:  # noqa: BLE001 - any unreadable package (HwpxError too) is corrupt input
        report.error(Codes.INPUT_CORRUPT, f"입력을 해석할 수 없습니다: {exc}")
        report.set_outputs(outputs)
        return Result(outputs, report)

    cwd, home = options.cwd or Path.cwd(), options.home or Path.home()
    ctx = ImportContext(report, imp.frontmatter, imp.generator, cwd, home, table_styles=imp.table_styles)
    try:
        doc = run_import_filters(imp.doc, ctx)
        md = write_md(doc, imp.frontmatter)
    except Exception as exc:  # noqa: BLE001 - never a traceback
        report.error(Codes.RENDER_FAILED, f"md 생성 중 예기치 않은 오류: {exc!r}", format=Format.MD.value)
        report.set_outputs(outputs)
        return Result(outputs, report)
    try:
        measure_coverage(imp.source_text, md, report, ctx.prefixes)
    except Exception as exc:  # noqa: BLE001 - coverage is a check, not the product
        report.warn(Codes.RENDER_WARNING, f"내용 보존율을 계산하는 중 예기치 않은 오류로 건너뜁니다: {exc!r}")

    md_output.data = md.encode("utf-8")
    md_output.assets = {f"{assets_dir}/{name}": data for name, data in imp.media.items()}
    report.set_outputs(outputs)
    return Result(outputs, report)
