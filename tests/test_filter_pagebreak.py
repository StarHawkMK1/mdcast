import panflute as pf

from mdcast.ast import md_to_doc
from mdcast.filters import pagebreak
from mdcast.filters.context import FilterContext
from mdcast.report import Codes, Report
from mdcast.templates.schema import deep_merge, load_builtin_default
from mdcast.types import Format


def run(md, target=Format.DOCX, before=None, skip_first=True, frontmatter=None, report=None):
    overrides = {}
    if before is not None:
        overrides = {"layout": {"page_break": {"before": before, "skip_first": skip_first}}}
    config = deep_merge(load_builtin_default(), overrides)
    ctx = FilterContext(target, config, frontmatter or {}, report or Report("a.md", Format.MD))
    return list(pagebreak.apply(md_to_doc(md), ctx).content)


def kinds(blocks):
    return ["BR" if isinstance(b, pf.RawBlock) and b.format in ("openxml", "typst") else type(b).__name__ for b in blocks]


def test_marker_becomes_docx_page_break():
    blocks = run("가\n\n<!-- pagebreak -->\n\n나\n")
    assert kinds(blocks) == ["Para", "BR", "Para"]
    assert 'w:type="page"' in blocks[1].text


def test_marker_becomes_typst_pagebreak_and_is_case_insensitive():
    blocks = run("가\n\n<!--PageBreak-->\n\n나\n", target=Format.PDF)
    assert blocks[1].text == "#pagebreak()"


def test_heading_rule_skips_first_matching_heading():
    blocks = run("# A\n\nx\n\n## B\n\ny\n\n## C\n", before=["h2"])
    assert kinds(blocks) == ["Header", "Para", "Header", "Para", "BR", "Header"]


def test_no_break_at_document_start_even_without_skip_first():
    blocks = run("## B\n\ny\n\n## C\n", before=["h2"], skip_first=False)
    assert kinds(blocks) == ["Header", "Para", "BR", "Header"]


def test_frontmatter_overrides_template_dict_list_and_string():
    md = "x\n\n# A\n\ny\n\n# B\n"
    assert kinds(run(md, frontmatter={"page_break": {"before": ["h1"]}})) == [
        "Para", "Header", "Para", "BR", "Header"
    ]
    assert kinds(run(md, frontmatter={"page_break": {"before": ["h1"], "skip_first": False}})) == [
        "Para", "BR", "Header", "Para", "BR", "Header"
    ]
    assert kinds(run("x\n\n## B\n", frontmatter={"page_break": "h2"})) == ["Para", "Header"]
    assert kinds(run("x\n\n## B\n\ny\n\n## C\n", frontmatter={"page_break": ["h2"]})) == [
        "Para", "Header", "Para", "BR", "Header"
    ]


def test_marker_right_before_rule_heading_gives_single_break():
    blocks = run("x\n\n<!-- pagebreak -->\n\n## B\n", before=["h2"], skip_first=False)
    assert kinds(blocks) == ["Para", "BR", "Header"]


def _warned(report):
    return [e for e in report.events if e.code == Codes.TEMPLATE_INVALID and "page_break" in e.message]


def test_invalid_frontmatter_page_break_warns_and_uses_template():
    md = "x\n\n## B\n\ny\n\n## C\n"
    for bad in ({"before": 3}, 5, ["h9"], {"skip_first": "yes"}):
        report = Report("a.md", Format.MD)
        blocks = run(md, before=["h2"], skip_first=True, frontmatter={"page_break": bad}, report=report)
        # template before=[h2], skip_first=True: a bad part falls back to the template, so only C gets a break
        assert _warned(report), bad
        assert kinds(blocks) == ["Para", "Header", "Para", "BR", "Header"], bad


def test_invalid_frontmatter_page_break_skip_first_uses_template_value():
    report = Report("a.md", Format.MD)
    blocks = run("## B\n\ny\n\n## C\n", before=["h2"], skip_first=False,
                 frontmatter={"page_break": {"before": ["h2"], "skip_first": "yes"}}, report=report)
    assert _warned(report)
    assert kinds(blocks) == ["Header", "Para", "BR", "Header"]


def test_invalid_heading_name_dropped_individually_keeps_valid_ones():
    report = Report("a.md", Format.MD)
    blocks = run("# A\n\nx\n\n## B\n\ny\n\n## C\n", frontmatter={"page_break": ["h9", "h2"]}, report=report)
    assert _warned(report)
    assert kinds(blocks) == ["Header", "Para", "Header", "Para", "BR", "Header"]


def test_all_invalid_heading_names_fall_back_to_template_levels():
    report = Report("a.md", Format.MD)
    blocks = run("x\n\n## B\n\ny\n\n## C\n", before=["h2"], skip_first=True,
                 frontmatter={"page_break": ["h9"]}, report=report)
    assert _warned(report)
    assert kinds(blocks) == ["Para", "Header", "Para", "BR", "Header"]


def test_explicit_empty_list_disables_heading_breaks_without_warning():
    report = Report("a.md", Format.MD)
    blocks = run("x\n\n## B\n\ny\n\n## C\n", before=["h2"], skip_first=False,
                 frontmatter={"page_break": []}, report=report)
    assert not _warned(report)
    assert kinds(blocks) == ["Para", "Header", "Para", "Header"]


def test_mixed_list_keeps_valid_names_and_warns():
    report = Report("a.md", Format.MD)
    blocks = run("x\n\n## B\n\ny\n\n## C\n", frontmatter={"page_break": ["h2", "h9"]}, report=report)
    assert _warned(report)
    assert kinds(blocks) == ["Para", "Header", "Para", "BR", "Header"]
