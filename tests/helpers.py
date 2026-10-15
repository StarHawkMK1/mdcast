from __future__ import annotations

import struct
import subprocess
import textwrap
import zlib
from pathlib import Path

from mdcast.ast import clone
from mdcast.fields import resolve_fields
from mdcast.filters import FilterContext, run_filters
from mdcast.readers.md import read_md
from mdcast.report import Report
from mdcast.templates import resolve_template
from mdcast.types import Format, Options, Source
from mdcast.writers.context import WriterContext


def write_template(
    root: Path, name: str, yaml_text: str, files: dict[str, bytes] | None = None
) -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "template.yaml").write_text(textwrap.dedent(yaml_text), encoding="utf-8")
    for filename, data in (files or {}).items():
        (directory / filename).write_bytes(data)
    return directory


def tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + chunk(b"IEND", b"")


def build(tmp_path: Path, md: str, target: Format, template: str | None = None, *, offline: bool = True):
    report = Report("doc.md", Format.MD)
    source = Source(textwrap.dedent(md).encode("utf-8"), "doc.md", Format.MD, base_dir=tmp_path)
    document = read_md(source, report)
    ref = template or document.frontmatter.get("template")
    tpl = resolve_template(ref, cwd=tmp_path, home=tmp_path / "home", report=report)
    fields = resolve_fields(document.frontmatter, tpl.config, report)
    fctx = FilterContext(target, tpl.config, document.frontmatter, report)
    doc = run_filters(clone(document.doc), fctx)
    work = tmp_path / f"work-{target.value}"
    work.mkdir(exist_ok=True)
    ctx = WriterContext(
        target=target,
        template=tpl,
        fields=fields,
        report=report,
        options=Options(offline=offline, cwd=tmp_path, home=tmp_path / "home"),
        base_dir=tmp_path,
        work_dir=work,
        state=fctx.state,
        generator={"generator": "mdcast test", "template": {"name": tpl.name, "source": tpl.source}},
    )
    return doc, ctx


def make_reference_docx(
    path: Path,
    *,
    header_runs: list[str] | None = None,
    footer_runs: list[str] | None = None,
    extra_styles: tuple[str, ...] = (),
) -> Path:
    import docx
    import pypandoc
    from docx.enum.style import WD_STYLE_TYPE

    subprocess.run(
        [pypandoc.get_pandoc_path(), "-o", str(path), "--print-default-data-file", "reference.docx"],
        check=True,
    )
    document = docx.Document(str(path))
    for name in extra_styles:
        document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    section = document.sections[0]
    for part, runs in ((section.header, header_runs), (section.footer, footer_runs)):
        if runs is None:
            continue
        part.is_linked_to_previous = False
        paragraph = part.paragraphs[0]
        paragraph.text = ""
        for text in runs:
            paragraph.add_run(text)
    document.save(str(path))
    return path
