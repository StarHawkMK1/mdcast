import panflute as pf

from mdcast.ast import md_to_doc
from mdcast.filters import tables
from mdcast.filters.context import FilterContext
from mdcast.report import Codes, Report
from mdcast.templates.schema import deep_merge, load_builtin_default
from mdcast.types import Format

VARIANTS = {"tables": {"variants": {"plain": {"header": {"background": None, "bold": False}}}}}
TWO_TABLES = "<!-- table: plain -->\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n| c |\n|---|\n| 3 |\n"


def run(md, target=Format.DOCX, overrides=None):
    config = deep_merge(load_builtin_default(), overrides or {})
    ctx = FilterContext(target, config, {}, Report("a.md", Format.MD))
    return tables.apply(md_to_doc(md), ctx), ctx


def test_variant_marker_attaches_to_next_table_and_is_removed():
    doc, ctx = run(TWO_TABLES, overrides=VARIANTS)
    assert [type(b).__name__ for b in doc.content] == ["Table", "Table"]
    assert ctx.state["tables"] == [{"variant": "plain", "head_rows": 1}, {"variant": None, "head_rows": 1}]


def test_unknown_variant_is_info_and_uses_default():
    _, ctx = run("<!-- table: fancy -->\n\n| a |\n|---|\n| 1 |\n")
    assert ctx.state["tables"] == [{"variant": None, "head_rows": 1}]
    assert [e.code for e in ctx.report.events] == [Codes.TABLE_VARIANT_UNKNOWN]


def test_marker_without_table_is_info_and_paragraph_kept():
    doc, ctx = run("<!-- table: plain -->\n\n문단\n", overrides=VARIANTS)
    assert [type(b).__name__ for b in doc.content] == ["Para"]
    assert [e.code for e in ctx.report.events] == [Codes.TABLE_VARIANT_UNKNOWN]


def test_default_alignment_keeps_explicit_alignment():
    doc, _ = run("| a | b |\n|---|--:|\n| 1 | 2 |\n")
    assert [a for a, _ in doc.content[0].colspec] == ["AlignLeft", "AlignRight"]


def test_header_cells_centered_and_bold():
    doc, _ = run("| a | b |\n|---|---|\n| 1 | 2 |\n")
    cells = doc.content[0].head.content[0].content
    assert all(c.alignment == "AlignCenter" for c in cells)
    assert isinstance(cells[0].content[0].content[0], pf.Strong)


def test_variant_without_bold_leaves_header_plain():
    doc, _ = run(TWO_TABLES, overrides=VARIANTS)
    first_cell = doc.content[0].head.content[0].content[0]
    assert not isinstance(first_cell.content[0].content[0], pf.Strong)


def test_full_width_sets_equal_fractions_and_auto_keeps_default():
    doc, _ = run("| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert [w for _, w in doc.content[0].colspec] == [0.5, 0.5]
    doc, _ = run("| a | b |\n|---|---|\n| 1 | 2 |\n", overrides={"tables": {"width": "auto"}})
    assert [w for _, w in doc.content[0].colspec] == ["ColWidthDefault", "ColWidthDefault"]


def test_pdf_wraps_top_level_tables():
    doc, _ = run(TWO_TABLES, target=Format.PDF, overrides=VARIANTS)
    texts = [b.text if isinstance(b, pf.RawBlock) else type(b).__name__ for b in doc.content]
    assert texts == [
        '#mdcast-table(cfg, "plain", 1)[', "Table", "]",
        '#mdcast-table(cfg, "_default", 1)[', "Table", "]",
    ]


def test_nested_table_is_styled_and_recorded_in_document_order():
    md = "> | a |\n> |---|\n> | 1 |\n\n<!-- table: plain -->\n\n| b |\n|---|\n| 2 |\n"
    doc, ctx = run(md, overrides=VARIANTS)
    nested = doc.content[0].content[0]
    assert nested.head.content[0].content[0].alignment == "AlignCenter"
    assert ctx.state["tables"] == [{"variant": None, "head_rows": 1}, {"variant": "plain", "head_rows": 1}]


def test_table_settings_merges_variant():
    config = deep_merge(load_builtin_default(), VARIANTS)
    s = tables.table_settings(config, "plain")
    assert s["header"]["background"] is None and s["font_size"] == "10pt" and "variants" not in s
def test_footnote_tables_are_not_collected():
    # footnote tables live in footnotes.xml, so they must not shift later variants
    md = (
        "text[^1]\n\n[^1]: note\n\n    | f |\n    |---|\n    | 9 |\n\n"
        "<!-- table: plain -->\n\n| b |\n|---|\n| 2 |\n"
    )
    doc, ctx = run(md, overrides=VARIANTS)
    assert ctx.state["tables"] == [{"variant": "plain", "head_rows": 1}]
    note_table = next(e for e in _all(doc) if isinstance(e, pf.Table) and tables._in_footnote(e))
    assert isinstance(note_table.head.content[0].content[0].content[0].content[0], pf.Strong)


def _all(doc):
    found = []
    doc.walk(lambda e, _d: found.append(e))
    return found


def test_second_marker_reports_the_unattached_first():
    md = "<!-- table: plain -->\n\n<!-- table: other -->\n\n| a |\n|---|\n| 1 |\n"
    _, ctx = run(md, overrides=VARIANTS)
    codes = [(e.code, e.where.get("variant")) for e in ctx.report.events]
    assert codes[0] == (Codes.TABLE_VARIANT_UNKNOWN, "plain")


def test_hwpx_tables_carry_their_variant():
    doc, _ = run(TWO_TABLES, target=Format.HWPX, overrides=VARIANTS)
    first, second = doc.content
    assert first.attributes["mdcast-variant"] == "plain"
    assert "mdcast-variant" not in second.attributes


def test_docx_tables_get_no_variant_attribute():
    doc, _ = run(TWO_TABLES, overrides=VARIANTS)
    assert all("mdcast-variant" not in t.attributes for t in doc.content)


ROWSPAN = "+----+----+\n| 가 | 1  |\n+    +----+\n|    | 2  |\n+----+----+\n| 나 | 3  |\n+----+----+\n"


def test_first_column_bold_follows_the_grid_under_a_rowspan():
    doc, _ = run(ROWSPAN, overrides={"tables": {"first_column": {"bold": True}}})
    rows = [row for body in doc.content[0].content for row in body.content]
    texts = [[pf.stringify(c) for c in row.content] for row in rows]
    bold = [[isinstance(c.content[0].content[0], pf.Strong) for c in row.content] for row in rows]
    assert texts == [["가", "1"], ["2"], ["나", "3"]]
    assert bold == [[True, False], [False], [True, False]]
