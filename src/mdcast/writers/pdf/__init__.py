from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import panflute as pf
import typst

from mdcast.ast import convert_doc
from mdcast.fonts import font_paths, latin_name, unknown_font_name
from mdcast.report import Codes, Report
from mdcast.writers.context import RenderError, WriterContext
from mdcast.writers.images import localize_images
from mdcast.writers.pdf.config import build_typst_config

MAIN_PREAMBLE = (
    '#import "mdcast.typ": *\n'
    "#let cfg = json(bytes(sys.inputs.cfg))\n"
    "#show: conf.with(cfg)\n"
)


def _compile(main: Path, root: Path, cfg_json: str):
    return typst.compile_with_warnings(
        str(main), root=str(root), font_paths=font_paths(), sys_inputs={"cfg": cfg_json}
    )


def _reset_ordered_lists(doc: pf.Doc) -> None:
    """Let the template's ``lists.ordered`` patterns govern, not pandoc's per-list ``#set enum``."""

    def action(elem: pf.Element, _doc: pf.Doc):
        if isinstance(elem, pf.OrderedList):
            elem.style = "DefaultStyle"
            elem.delimiter = "DefaultDelim"

    doc.walk(action)


def _report_warnings(warnings, ctx: WriterContext, report: Report) -> None:
    primaries: dict[str, str] = {}
    for role in ("body", "heading", "code"):
        family = str(ctx.template.config["fonts"][role].get("family") or "")
        if family:
            primaries[latin_name(family).lower()] = family
    for warning in warnings:
        name = unknown_font_name(warning.message)
        if name is not None:
            if name in primaries:
                report.warn(
                    Codes.FONT_FALLBACK,
                    f"PDF: '{primaries[name]}' 글꼴이 없어 대체 글꼴로 조판했습니다",
                    once=True,
                    format="pdf",
                    font=primaries[name],
                )
            continue
        report.info(Codes.RENDER_WARNING, f"Typst 경고: {warning.message}", once=True, format="pdf")


def write_pdf(doc: pf.Doc, ctx: WriterContext) -> bytes:
    doc = localize_images(doc, ctx)
    _reset_ordered_lists(doc)
    try:
        body = convert_doc(doc, "typst")
    except RuntimeError as exc:
        raise RenderError(f"pandoc typst 변환 실패: {exc}") from exc
    cfg: dict[str, Any] = build_typst_config(ctx.template, ctx.fields, ctx.report)
    cfg_json = json.dumps(cfg, ensure_ascii=False)
    main = ctx.work_dir / "main.typ"
    main.write_text(MAIN_PREAMBLE + body, encoding="utf-8")
    layout = ctx.template.container_for("pdf")
    builtin = ctx.template.builtin_container("pdf")
    candidates = []
    if layout.path is not None and layout.path.is_file():
        candidates.append((layout.path, layout.source))
    if builtin.path is not None and (
        not candidates or candidates[0][0].resolve() != builtin.path.resolve()
    ):
        candidates.append((builtin.path, "builtin"))
    last_error: Exception | None = None
    for path, source in candidates:
        shutil.copyfile(path, ctx.work_dir / "mdcast.typ")
        try:
            pdf, warnings = _compile(main, ctx.work_dir, cfg_json)
        except typst.TypstError as exc:
            last_error = exc
            if source == "custom":
                ctx.report.warn(
                    Codes.TEMPLATE_INVALID,
                    f"커스텀 pdf.typ 를 컴파일할 수 없어 내장 레이아웃으로 다시 그립니다: {exc}",
                    format="pdf",
                )
            continue
        _report_warnings(warnings, ctx, ctx.report)
        return pdf
    raise RenderError(f"Typst 컴파일 실패: {last_error}")
