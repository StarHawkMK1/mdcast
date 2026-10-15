import zipfile
from io import BytesIO
from pathlib import Path

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


def test_unsupported_target_fails_only_that_target(tmp_path):
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


def test_non_md_input_is_unsupported(tmp_path):
    result = pipeline.convert(Source(b"PK", "a.docx", Format.DOCX), [Format.MD], options=opts(tmp_path))
    assert statuses(result) == {"md": "failed"}
    assert [e.code for e in result.report.events] == [Codes.INPUT_UNSUPPORTED]


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
