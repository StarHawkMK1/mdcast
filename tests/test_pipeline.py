import importlib.metadata
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from helpers import write_template

from mdcast import pipeline
from mdcast.report import Codes, Level
from mdcast.types import Format, Options, Source


def src(text: str, name: str = "보고 서.md") -> Source:
    return Source(text.encode("utf-8"), name, Format.MD, base_dir=None)


def opts(tmp_path: Path, **kw) -> Options:
    return Options(offline=True, cwd=tmp_path, home=tmp_path / "home", **kw)


def by_format(result):
    return {o.format: o for o in result.outputs}


def statuses(result):
    return {o["format"]: o["status"] for o in result.report.outputs}


def test_md_to_docx_and_pdf(tmp_path):
    result = pipeline.convert(src("# 개요\n\n본문\n"), [Format.DOCX, Format.PDF], options=opts(tmp_path))
    outs = by_format(result)
    assert outs[Format.DOCX].name == "보고 서.docx" and outs[Format.DOCX].data[:2] == b"PK"
    assert outs[Format.PDF].data.startswith(b"%PDF")
    assert statuses(result)[Format.DOCX.value] == "ok"
    assert statuses(result)[Format.PDF.value] in ("ok", "degraded")
    assert result.report.template.name == "default"


def test_unsupported_target_fails_only_that_target(tmp_path, monkeypatch):
    monkeypatch.delitem(pipeline.WRITERS, Format.HWPX)
    result = pipeline.convert(src("본문\n"), [Format.DOCX, Format.HWPX], options=opts(tmp_path))
    assert statuses(result) == {"docx": "ok", "hwpx": "failed"}
    errors = [(e.code, e.where.get("format")) for e in result.report.events if e.level is Level.ERROR]
    assert errors == [(Codes.TARGET_UNSUPPORTED, "hwpx")]


def test_template_from_frontmatter_and_explicit_override(tmp_path):
    write_template(tmp_path / ".mdcast" / "templates", "rep", "name: rep\n")
    write_template(tmp_path / ".mdcast" / "templates", "other", "name: other\n")
    md = "---\ntemplate: rep\n---\n\n본문\n"
    assert pipeline.convert(src(md), [Format.DOCX], options=opts(tmp_path)).report.template.name == "rep"
    assert pipeline.convert(src(md), [Format.DOCX], "other", options=opts(tmp_path)).report.template.name == "other"


def test_custom_template_container_fallback_is_reported(tmp_path):
    write_template(tmp_path / ".mdcast" / "templates", "rep", "name: rep\n")
    result = pipeline.convert(src("본문\n"), [Format.DOCX], "rep", options=opts(tmp_path))
    assert [(e.code, e.where.get("format")) for e in result.report.events if e.code == Codes.TEMPLATE_CONTAINER_FALLBACK] == [
        (Codes.TEMPLATE_CONTAINER_FALLBACK, "docx")
    ]
    assert result.report.template.per_format["docx"] == {"container": "builtin", "styles": "custom"}


def test_empty_and_frontmatter_only_inputs_still_produce_files(tmp_path):
    for text in ("", "---\ntitle: 제목만\n---\n"):
        result = pipeline.convert(src(text), [Format.DOCX, Format.PDF], options=opts(tmp_path))
        assert all(o.data for o in result.outputs), text


def test_writer_crash_is_contained(tmp_path, monkeypatch):
    def boom(doc, ctx):
        raise ValueError("boom")

    monkeypatch.setitem(pipeline.WRITERS, Format.PDF, boom)
    result = pipeline.convert(src("본문\n"), [Format.DOCX, Format.PDF], options=opts(tmp_path))
    assert statuses(result) == {"docx": "ok", "pdf": "failed"}
    assert any(e.code == Codes.RENDER_FAILED and "boom" in e.message for e in result.report.events)


def test_writer_oserror_is_contained(tmp_path, monkeypatch):
    def boom(doc, ctx):
        raise OSError("disk full")

    monkeypatch.setitem(pipeline.WRITERS, Format.DOCX, boom)
    result = pipeline.convert(src("본문\n"), [Format.DOCX, Format.PDF], options=opts(tmp_path))
    outs = by_format(result)
    assert outs[Format.DOCX].data is None
    assert outs[Format.PDF].data.startswith(b"%PDF")
    errors = [(e.code, e.where.get("format")) for e in result.report.events if e.level is Level.ERROR]
    assert errors == [(Codes.RENDER_FAILED, "docx")]


def test_pdf_input_reaches_the_importer(tmp_path):
    """A .pdf goes to the pdf reader, not the MD path: a broken one fails there as INPUT_CORRUPT."""
    result = pipeline.convert(Source(b"%PDF", "a.pdf", Format.PDF), [Format.MD], options=opts(tmp_path))
    assert statuses(result) == {"md": "failed"}
    assert [e.code for e in result.report.events] == [Codes.INPUT_CORRUPT]


def test_keep_temp_records_work_dir(tmp_path):
    result = pipeline.convert(src("본문\n"), [Format.DOCX], options=opts(tmp_path, keep_temp=True, temp_root=tmp_path))
    work = Path(result.report.temp_dir)
    assert (work / "docx" / "out.docx").is_file()


def test_duplicate_targets_are_collapsed(tmp_path):
    result = pipeline.convert(src("본문\n"), [Format.DOCX, Format.DOCX], options=opts(tmp_path))
    assert len(result.outputs) == 1


def test_generator_versions_reach_docx_custom_properties(tmp_path):
    result = pipeline.convert(src("본문\n"), [Format.DOCX], options=opts(tmp_path))
    with zipfile.ZipFile(BytesIO(result.outputs[0].data)) as z:
        custom = z.read("docProps/custom.xml").decode("utf-8")
    for key in ("mdcast.generator", "mdcast.pandoc", "mdcast.typst", "mdcast.template.name"):
        assert key in custom


def test_relative_frontmatter_template_path_resolves_from_the_document_folder(tmp_path):
    docs = tmp_path / "docs"
    write_template(docs, "양식", "name: from-doc\n")
    source = Source("---\ntemplate: ./양식\n---\n\n본문\n".encode(), "보고서.md", Format.MD, base_dir=docs)
    result = pipeline.convert(source, [Format.DOCX], options=opts(tmp_path))
    assert result.report.template.name == "from-doc"
    assert Codes.TEMPLATE_NOT_FOUND not in [e.code for e in result.report.events]


def test_explicit_template_path_still_resolves_from_cwd(tmp_path):
    docs = tmp_path / "docs"
    write_template(docs, "양식", "name: from-doc\n")
    source = Source("본문\n".encode(), "보고서.md", Format.MD, base_dir=docs)
    result = pipeline.convert(source, [Format.DOCX], "./양식", options=opts(tmp_path))
    assert result.report.template.name == "default"
    assert Codes.TEMPLATE_NOT_FOUND in [e.code for e in result.report.events]


def test_frontmatter_template_name_is_not_treated_as_a_path(tmp_path):
    docs = tmp_path / "docs"
    write_template(docs, "rep", "name: wrong\n")
    write_template(tmp_path / ".mdcast" / "templates", "rep", "name: rep\n")
    source = Source("---\ntemplate: rep\n---\n\n본문\n".encode(), "보고서.md", Format.MD, base_dir=docs)
    assert pipeline.convert(source, [Format.DOCX], options=opts(tmp_path)).report.template.name == "rep"


def _warn_codes(result):
    return [e.code for e in result.report.events if e.level is Level.WARN]


def _errors(result):
    return [e for e in result.report.events if e.level is Level.ERROR]


def test_template_resolution_crash_falls_back_to_builtin_default(tmp_path, monkeypatch):
    real = pipeline.resolve_template

    def flaky(ref, **kw):
        if ref is not None:
            raise RuntimeError("resolver bug")
        return real(ref, **kw)

    monkeypatch.setattr(pipeline, "resolve_template", flaky)
    result = pipeline.convert(src("# 개요\n\n본문\n"), [Format.DOCX, Format.PDF], "rep", options=opts(tmp_path))
    assert all(o.data for o in result.outputs), [e.to_dict() for e in result.report.events]
    assert result.report.template.name == "default"
    assert Codes.TEMPLATE_INVALID in _warn_codes(result)
    assert not _errors(result)


def test_template_fallback_crash_is_an_error_not_an_exception(tmp_path, monkeypatch):
    def broken(ref, **kw):
        raise RuntimeError("resolver bug")

    monkeypatch.setattr(pipeline, "resolve_template", broken)
    result = pipeline.convert(src("본문\n"), [Format.DOCX, Format.PDF], options=opts(tmp_path))
    assert [o.data for o in result.outputs] == [None, None]
    assert statuses(result) == {"docx": "failed", "pdf": "failed"}
    assert [e.code for e in _errors(result)] == [Codes.RENDER_FAILED]


def test_template_info_crash_falls_back_to_builtin_default(tmp_path, monkeypatch):
    calls = []
    real_info = pipeline.ResolvedTemplate.info

    def flaky_info(self, formats):
        calls.append(self.name)
        if len(calls) == 1:
            raise KeyError("per_format")
        return real_info(self, formats)

    monkeypatch.setattr(pipeline.ResolvedTemplate, "info", flaky_info)
    result = pipeline.convert(src("본문\n"), [Format.DOCX, Format.PDF], options=opts(tmp_path))
    assert all(o.data for o in result.outputs)
    assert Codes.TEMPLATE_INVALID in _warn_codes(result)


def test_fields_crash_uses_empty_fields(tmp_path, monkeypatch):
    def broken(*args, **kw):
        raise TypeError("fields bug")

    monkeypatch.setattr(pipeline, "resolve_fields", broken)
    result = pipeline.convert(src("---\ntitle: 제목\n---\n\n본문\n"), [Format.DOCX, Format.PDF], options=opts(tmp_path))
    assert all(o.data for o in result.outputs), [e.to_dict() for e in result.report.events]
    assert Codes.RENDER_WARNING in _warn_codes(result)
    assert not _errors(result)


def test_generator_crash_uses_a_minimal_generator(tmp_path, monkeypatch):
    def broken(tpl):
        raise importlib.metadata.PackageNotFoundError("typst")

    monkeypatch.setattr(pipeline, "build_generator", broken)
    result = pipeline.convert(src("본문\n"), [Format.DOCX, Format.PDF], options=opts(tmp_path))
    assert all(o.data for o in result.outputs), [e.to_dict() for e in result.report.events]
    assert Codes.RENDER_WARNING in _warn_codes(result)
    assert not _errors(result)
    docx_data = by_format(result)[Format.DOCX].data
    with zipfile.ZipFile(BytesIO(docx_data)) as z:
        custom = z.read("docProps/custom.xml").decode("utf-8")
    assert "mdcast.generator" in custom


@pytest.mark.parametrize("keep_temp", [False, True])
def test_workspace_that_cannot_be_created_is_an_error(tmp_path, keep_temp):
    options = opts(tmp_path, keep_temp=keep_temp, temp_root=tmp_path / "missing")
    result = pipeline.convert(src("본문\n"), [Format.DOCX, Format.PDF], options=options)
    assert [o.data for o in result.outputs] == [None, None]
    assert statuses(result) == {"docx": "failed", "pdf": "failed"}
    assert [e.code for e in _errors(result)] == [Codes.RENDER_FAILED]


def test_workspace_cleanup_error_keeps_the_outputs(tmp_path, monkeypatch):
    import contextlib

    @contextlib.contextmanager
    def sticky(options, report):
        work = tmp_path / "work"
        work.mkdir()
        yield work
        raise PermissionError("locked")

    monkeypatch.setattr(pipeline, "_workspace", sticky)
    result = pipeline.convert(src("본문\n"), [Format.DOCX, Format.PDF], options=opts(tmp_path))
    assert all(o.data for o in result.outputs)
    assert not _errors(result)
    assert any(e.code == Codes.RENDER_WARNING and "locked" in e.message for e in result.report.events)
