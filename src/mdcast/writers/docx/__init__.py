from __future__ import annotations

import io
from pathlib import Path

import panflute as pf
from docx import Document

from mdcast.ast import convert_doc
from mdcast.report import Codes
from mdcast.units import parse_pt
from mdcast.writers.context import RenderError, WriterContext
from mdcast.writers.docx.headers import apply_headers
from mdcast.writers.docx.meta import apply_metadata
from mdcast.writers.docx.numbering import apply_list_numbering
from mdcast.writers.docx.styles import (
    apply_elements,
    apply_page,
    disable_autospace,
    remap_styles,
    tighten_compact,
)
from mdcast.writers.docx.tables import apply_tables
from mdcast.writers.images import localize_images

# pandoc would typeset these as Title/Subtitle/Author/Date/Abstract paragraphs at the top of the
# body, outside the template's looks and absent from the PDF (spec 0.4, 1.2). They stay available
# as fields; the core properties are written from the fields by apply_metadata.
TITLE_BLOCK_KEYS = ("title", "subtitle", "author", "date", "abstract")


def _drop_title_block(doc: pf.Doc) -> None:
    for key in TITLE_BLOCK_KEYS:
        if key in doc.metadata:
            del doc.metadata[key]


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
    _drop_title_block(doc)
    d, container_source = _open_output(doc, ctx)
    config = ctx.template.config
    # a custom container's own style values beat the built-in default (spec 3.3):
    # apply only what the template yaml (or its parent) set explicitly
    looks = ctx.template.explicit if container_source == "custom" else config
    if container_source != "custom":
        disable_autospace(d)
        tighten_compact(d)
    apply_page(d, looks)
    used = remap_styles(d, config, ctx.report)
    apply_elements(d, looks, used, fallback_pt=parse_pt(config["elements"]["body"]["size"]))
    apply_headers(d, config, ctx.fields)
    apply_list_numbering(d, config)
    explicit_tables = ctx.template.explicit if container_source == "custom" else None
    apply_tables(d, config, explicit_tables, ctx.state.get("tables", []), ctx.report)
    apply_metadata(d, ctx.generator, ctx.fields, ctx.report)
    buffer = io.BytesIO()
    d.save(buffer)
    return buffer.getvalue()
