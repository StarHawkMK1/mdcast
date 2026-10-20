from __future__ import annotations

import panflute as pf

from mdcast.report import Report
from mdcast.types import Format, Source
from mdcast.writers.md import write_md


def back(md: str) -> pf.Doc:
    from mdcast.readers.md import read_md

    return read_md(Source(md.encode(), "t.md", Format.MD), Report("t.md", Format.MD)).doc


def doc_with(*blocks) -> pf.Doc:
    return pf.Doc(*blocks)


def first(doc: pf.Doc, kind):
    found: list = []
    doc.walk(lambda e, d: found.append(e) if isinstance(e, kind) else None)
    return found[0]


def cell(*blocks, rowspan: int = 1, colspan: int = 1) -> pf.TableCell:
    return pf.TableCell(*blocks, rowspan=rowspan, colspan=colspan)


def txt(text: str) -> pf.Plain:
    return pf.Plain(pf.Str(text))


def make_table(head: list[list[pf.TableCell]], body: list[list[pf.TableCell]], caption=None) -> pf.Table:
    width = sum(c.colspan for c in head[0] if True) if head else sum(c.colspan for c in body[0])
    return pf.Table(
        pf.TableBody(*[pf.TableRow(*r) for r in body]),
        head=pf.TableHead(*[pf.TableRow(*r) for r in head]),
        caption=pf.Caption(*caption) if caption else pf.Caption(),
        colspec=[("AlignDefault", "ColWidthDefault")] * width,
    )


def simple_table() -> pf.Table:
    return make_table([[cell(txt("a")), cell(txt("b"))]], [[cell(txt("1")), cell(txt("2"))]])


def merged_table_with_note() -> pf.Table:
    note = pf.Note(pf.Para(pf.Str("칸"), pf.Space(), pf.Str("각주.")))
    return make_table(
        [[cell(txt("h1")), cell(txt("h2"))]],
        [
            [cell(pf.Plain(pf.Str("x"), note), rowspan=2), cell(txt("y"))],
            [cell(txt("z"))],
        ],
    )


def spans(table: pf.Table) -> list[list[tuple[int, int]]]:
    rows = list(table.head.content)
    for body in table.content:
        rows += list(body.content)
    return [[(c.rowspan, c.colspan) for c in r.content] for r in rows]


def note_texts(doc: pf.Doc) -> list[str]:
    out: list[str] = []
    doc.walk(lambda e, d: out.append(pf.stringify(e).strip()) if isinstance(e, pf.Note) else None)
    return out


def pagebreak_raw() -> pf.RawBlock:
    return pf.RawBlock("<!-- pagebreak -->", "html")


def tables(doc: pf.Doc) -> list[pf.Table]:
    return [b for b in doc.content if isinstance(b, pf.Table)]


def test_frontmatter_only_known_nonempty_keys():
    md = write_md(pf.Doc(pf.Para(pf.Str("본문"))), {"title": "제목", "author": "", "template": None})
    assert md.startswith("---\ntitle: 제목\n---\n\n본문")


def test_no_frontmatter_when_empty():
    assert write_md(pf.Doc(pf.Para(pf.Str("본문"))), {"other": "x"}) == "본문\n"


def test_simple_table_is_pipe_and_merged_is_clean_html():
    md = write_md(doc_with(simple_table(), merged_table_with_note()), {})
    assert "| a | b |" in md
    assert 'rowspan="2"' in md and "style=" not in md and "<colgroup" not in md and "class=" not in md
    assert "[^t1]" in md and "\n[^t1]: " in md
    t = [b for b in back(md).content if isinstance(b, pf.Table)]
    assert spans(t[1]) == spans(merged_table_with_note()) and note_texts(back(md)) == ["칸 각주."]


def test_captioned_or_multiblock_cells_use_html():
    captioned = make_table(
        [[cell(txt("a")), cell(txt("b"))]],
        [[cell(txt("1")), cell(txt("2"))]],
        caption=[pf.Plain(pf.Str("표"), pf.Space(), pf.Str("캡션"))],
    )
    multi = make_table(
        [[cell(txt("a")), cell(txt("b"))]],
        [[
            cell(pf.Para(pf.Str("첫째")), pf.Para(pf.Str("둘째"))),
            cell(pf.BulletList(pf.ListItem(txt("항목1")), pf.ListItem(txt("항목2")))),
        ]],
    )
    inner = make_table([[cell(txt("i1")), cell(txt("i2"))]], [[cell(txt("i3")), cell(txt("i4"))]])
    nested = make_table([[cell(txt("a")), cell(txt("b"))]], [[cell(txt("outer")), cell(inner)]])
    md = write_md(doc_with(captioned, multi, nested), {})
    assert "<caption>" in md and "|" not in md
    assert "style=" not in md and "class=" not in md and "<colgroup" not in md
    got = tables(back(md))
    assert len(got) == 3
    assert pf.stringify(got[0].caption).strip() == "표 캡션"
    assert [len(c.content) for c in got[1].content[0].content[0].content] == [2, 1]
    assert isinstance(got[1].content[0].content[0].content[1].content[0], pf.BulletList)
    inner_back = got[2].content[0].content[0].content[1].content[0]
    assert isinstance(inner_back, pf.Table)
    assert pf.stringify(inner_back).replace("\n", "") == "i1i2i3i4"


def test_pagebreak_marker_and_math_survive():
    md = write_md(doc_with(pagebreak_raw(), pf.Para(pf.Math("x^2", format="InlineMath"))), {})
    assert "<!-- pagebreak -->" in md and "$x^2$" in md


def test_table_kind_marker_on_own_line():
    md = write_md(doc_with(pf.RawBlock("<!-- table: data -->", "html"), simple_table()), {})
    assert "\n<!-- table: data -->\n" in "\n" + md


def test_no_hard_wrap():
    long = " ".join(["단어"] * 100)
    words = [pf.Str(w) if w else pf.Space() for w in long.replace(" ", "\0 \0").split("\0")]
    md = write_md(doc_with(pf.Para(*[x for x in words if str(x)])), {})
    lines = [line for line in md.splitlines() if line]
    assert len(lines) == 1 and len(lines[0]) >= 200


def test_image_link_with_space_in_folder():
    md = write_md(doc_with(pf.Para(pf.Image(pf.Str("그림"), url="보고 서_assets/image1.png"))), {})
    assert first(back(md), pf.Image).url == "보고 서_assets/image1.png"


def test_image_in_html_cell_with_space():
    table = make_table(
        [[cell(txt("a")), cell(txt("b"))]],
        [[cell(pf.Plain(pf.Image(pf.Str("그림"), url="보고 서_assets/image1.png")), colspan=2)]],
    )
    md = write_md(doc_with(table), {})
    assert "<img" in md and "colspan" in md
    assert first(back(md), pf.Image).url == "보고 서_assets/image1.png"


def test_cell_notes_numbered_across_document_and_multiblock_definition():
    def merged(text: str) -> pf.Table:
        note = pf.Note(pf.Para(pf.Str(text)), pf.Para(pf.Str(text + "-2")))
        return make_table(
            [[cell(txt("h1")), cell(txt("h2"))]],
            [[cell(pf.Plain(pf.Str("x"), note), rowspan=2), cell(txt("y"))], [cell(txt("z"))]],
        )

    md = write_md(doc_with(merged("가"), merged("나")), {})
    assert "[^t1]" in md and "[^t2]" in md
    assert "\n[^t1]: 가\n\n    가-2\n" in md
    assert note_texts(back(md)) == ["가\n\n가-2", "나\n\n나-2"]
