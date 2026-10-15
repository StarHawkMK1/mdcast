from __future__ import annotations

import io
from pathlib import Path

import panflute as pf
from docx import Document

from mdcast.ast import convert_doc
from mdcast.report import Codes
from mdcast.writers.context import RenderError, WriterContext
from mdcast.writers.docx.headers import apply_headers
from mdcast.writers.docx.meta import apply_metadata
from mdcast.writers.docx.numbering import apply_list_numbering
from mdcast.writers.docx.styles import apply_elements, apply_page, remap_styles
from mdcast.writers.docx.tables import apply_tables
from mdcast.writers.images import localize_images


def _pandoc_docx(doc: pf.Doc, ctx: WriterContext, reference: Path | None):
    out = ctx.work_dir / "out.docx"
    args = [f"--resource-path={ctx.work_dir}"]
    if reference is not None:
        args.append(f"--reference-doc={reference}")
    convert_doc(doc, "docx", outputfile=out, extra_args=args)
    return Document(str(out))


def _open_output(doc: pf.Doc, ctx: WriterContext):
    """Open pandoc's output; returns ``(document, container_source)`` of the container really used."""
    container = ctx.template.container_for("docx")
    if container.path is not None:
        try:
            return _pandoc_docx(doc, ctx, container.path), container.source
        except Exception as exc:
            if container.source != "custom":
                raise RenderError(f"pandoc docx 변환 실패: {exc}") from exc
            ctx.report.warn(
                Codes.TEMPLATE_INVALID,
                f"커스텀 reference.docx 를 쓸 수 없어 내장 그릇으로 변환합니다: {exc}",
                format="docx",
            )
    builtin = ctx.template.builtin_container("docx")
    try:
        return _pandoc_docx(doc, ctx, builtin.path), builtin.source
    except Exception as exc:
        raise RenderError(f"pandoc docx 변환 실패: {exc}") from exc


def write_docx(doc: pf.Doc, ctx: WriterContext) -> bytes:
    doc = localize_images(doc, ctx)
    d, container_source = _open_output(doc, ctx)
    config = ctx.template.config
    # a custom container's own style values beat the built-in default (spec 3.3):
    # apply only what the template yaml (or its parent) set explicitly
    looks = ctx.template.explicit if container_source == "custom" else config
    apply_page(d, looks)
    used = remap_styles(d, config, ctx.report)
    apply_elements(d, looks, used)
    apply_headers(d, config, ctx.fields)
    apply_list_numbering(d, config)
    explicit_tables = ctx.template.explicit if container_source == "custom" else None
    apply_tables(d, config, explicit_tables, ctx.state.get("tables", []), ctx.report)
    apply_metadata(d, ctx.generator, ctx.fields)
    buffer = io.BytesIO()
    d.save(buffer)
    return buffer.getvalue()
