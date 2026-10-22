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


def test_one_paragraph_caption_reads_back_as_plain():
    # pandoc's docx reader gives the caption as Para; `<caption><p>` would come back as Para
    captioned = make_table(
        [[cell(txt("a")), cell(txt("b"))]],
        [[cell(txt("1")), cell(txt("2"))]],
        caption=[pf.Para(pf.Str("요약"), pf.Space(), pf.Str("표"))],
    )
    md = write_md(doc_with(captioned), {})
    assert "<caption>요약 표</caption>" in md
    caption = tables(back(md))[0].caption.content
    assert len(caption) == 1 and isinstance(caption[0], pf.Plain)


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


def _note_shape(note: pf.Note) -> list[tuple[str, str]]:
    return [(type(b).__name__, pf.stringify(b).strip()) for b in note.content]


def test_cell_note_starting_with_a_code_block_or_list_keeps_its_blocks():
    notes = [
        pf.Note(pf.CodeBlock("a over b"), pf.Para(pf.Str("뒤"))),
        pf.Note(pf.CodeBlock("x = 1", classes=["python"])),
        pf.Note(pf.BulletList(pf.ListItem(txt("가")), pf.ListItem(txt("나"))), pf.Para(pf.Str("끝"))),
    ]
    table = make_table(
        [[cell(txt("h1")), cell(txt("h2"))]],
        [[cell(pf.Plain(pf.Str("x"), *notes), rowspan=2), cell(txt("y"))], [cell(txt("z"))]],
    )
    md = write_md(doc_with(table), {})
    assert "\n[^t1]:\n\n        a over b\n" in md  # the label alone, the blocks indented under it
    found: list[pf.Note] = []
    back(md).walk(lambda e, d: found.append(e) if isinstance(e, pf.Note) else None)
    assert [_note_shape(n) for n in found] == [_note_shape(n) for n in notes]
    assert found[1].content[0].classes == ["python"]


def figure(url: str, caption: str) -> pf.Figure:
    return pf.Figure(
        pf.Plain(pf.Image(pf.Str("alt"), url=url)),
        caption=pf.Caption(pf.Plain(pf.Str(caption))),
    )


def test_captioned_figure_becomes_image_with_caption_alt():
    md = write_md(doc_with(figure("그림 폴더/a.png", "도표1")), {})
    assert "<figure" not in md and "![도표1](" in md
    image = first(back(md), pf.Image)
    assert pf.stringify(image) == "도표1" and image.url == "그림 폴더/a.png"


def test_figure_in_html_cell_becomes_image():
    table = make_table(
        [[cell(txt("a")), cell(txt("b"))]],
        [[cell(figure("x.png", "셀 그림"), colspan=2)]],
    )
    md = write_md(doc_with(table), {})
    assert "<figure" not in md
    assert pf.stringify(first(back(md), pf.Image)) == "셀 그림"


def test_figure_with_two_images_keeps_everything():
    fig = pf.Figure(
        pf.Plain(pf.Image(pf.Str("a"), url="1.png")),
        pf.Plain(pf.Image(pf.Str("b"), url="2.png")),
        caption=pf.Caption(pf.Plain(pf.Str("공통"))),
    )
    got = back(write_md(doc_with(fig), {}))
    urls = []
    got.walk(lambda e, d: urls.append(e.url) if isinstance(e, pf.Image) else None)
    assert urls == ["1.png", "2.png"] and "공통" in pf.stringify(got)


def pipe_table(inline) -> pf.Table:
    return make_table([[cell(txt("h1")), cell(txt("h2"))]], [[cell(pf.Plain(inline)), cell(txt("z"))]])


def test_pipes_in_cells_round_trip_via_html():
    for inline in (pf.Str("a|b"), pf.Code("a|b"), pf.Math("a|b", format="InlineMath")):
        md = write_md(doc_with(pipe_table(inline)), {})
        assert "<table>" in md
        got = tables(back(md))[0]
        assert spans(got) == [[(1, 1), (1, 1)], [(1, 1), (1, 1)]]
        assert "a|b" in pf.stringify(got.content[0].content[0].content[0])


def test_image_path_with_space_in_pipe_cell_and_cell_note_is_encoded():
    image = pf.Image(pf.Str("그림"), url="보고 서/a.png")
    md = write_md(doc_with(make_table([[cell(txt("h1"))]], [[cell(pf.Plain(image))]])), {})
    assert "(보고%20서/a.png)" in md
    assert first(back(md), pf.Image).url == "보고 서/a.png"
    note = pf.Note(pf.Para(pf.Image(pf.Str("n"), url="보고 서/b.png")))
    merged = make_table(
        [[cell(txt("h1")), cell(txt("h2"))]],
        [[cell(pf.Plain(pf.Str("x"), note), rowspan=2), cell(txt("y"))], [cell(txt("z"))]],
    )
    md = write_md(doc_with(merged), {})
    assert "[^t1]: ![n](보고%20서/b.png)" in md


def test_remote_image_url_keeps_percent_encoding():
    got = back("![x](https://example.com/a%20b.png)\n")
    assert first(got, pf.Image).url == "https://example.com/a%20b.png"


def count_pandoc_calls(monkeypatch) -> list[str]:
    import pypandoc

    calls: list[str] = []
    for name in ("convert_text", "convert_file"):
        real = getattr(pypandoc, name)

        def counting(*args, _real=real, _name=name, **kwargs):
            calls.append(_name)
            return _real(*args, **kwargs)

        monkeypatch.setattr(pypandoc, name, counting)
    return calls


def test_cells_of_every_table_render_in_one_pandoc_call_per_format(monkeypatch):
    rows = 50
    head = [cell(txt(f"h{c}")) for c in range(6)]
    pipe = make_table([head], [[cell(txt(f"p{r}-{c}")) for c in range(6)] for r in range(rows)])
    body = [[cell(txt(f"m{r}-{c}")) for c in range(6)] for r in range(rows)]
    body[0][0] = cell(pf.Plain(pf.Str("m0-0"), pf.Note(pf.Para(pf.Str("칸각주")))), rowspan=2)
    del body[1][0]
    inner = make_table([[cell(txt("i1")), cell(txt("i2"))]], [[cell(txt("i3")), cell(txt("i4"))]])
    body[2][1] = cell(inner)
    merged = make_table([[cell(txt(f"h{c}")) for c in range(6)]], body)
    calls = count_pandoc_calls(monkeypatch)
    md = write_md(doc_with(pipe, merged), {})
    assert len(calls) <= 4  # html cells, pipe cells, the body, the one cell note
    assert "mdcast-cell" not in md
    got = tables(back(md))
    assert [len(t.content[0].content) for t in got] == [rows, rows]
    assert pf.stringify(got[0].content[0].content[-1].content[-1]).strip() == f"p{rows - 1}-5"
    assert pf.stringify(got[1].content[0].content[-1].content[-1]).strip() == f"m{rows - 1}-5"
    assert spans(got[1])[1][0] == (2, 1) and note_texts(back(md)) == ["칸각주"]
    assert pf.stringify(got[1].content[0].content[2].content[1]).replace("\n", "") == "i1i2i3i4"


def maths(doc: pf.Doc) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    doc.walk(lambda e, d: found.append((e.format, e.text)) if isinstance(e, pf.Math) else None)
    return found


def test_math_in_html_table_round_trips_as_math():
    inline = r"x^2 + \frac{a}{b} < c \& d"
    display = r"\sum_{i=1}^{n} i"
    note = pf.Note(pf.Para(pf.Str("각주"), pf.Space(), pf.Math(r"\theta", format="InlineMath")))
    table = make_table(
        [[cell(txt("h1")), cell(txt("h2"))]],
        [
            [cell(pf.Plain(pf.Math(inline, format="InlineMath"), note), rowspan=2), cell(txt("y"))],
            [cell(pf.Plain(pf.Math(display, format="DisplayMath")))],
        ],
        caption=[pf.Plain(pf.Str("캡션"), pf.Space(), pf.Math("y^3", format="InlineMath"))],
    )
    md = write_md(doc_with(table), {})
    assert '<span class="math inline">' in md and '<span class="math display">' in md
    assert r"[^t1]: 각주 $\theta$" in md
    got = back(md)
    expected = [("InlineMath", "y^3"), ("InlineMath", inline), ("InlineMath", r"\theta"), ("DisplayMath", display)]
    assert sorted(maths(got)) == sorted(expected)


ODD_STEMS = ["붙임1)계획", "x)y", "(최종", "a<b>", "50%할인", "a%20b", "보고서 (최종) v2"]


def test_odd_local_image_paths_round_trip_in_body_and_cells():
    for stem in ODD_STEMS:
        url = f"{stem}_assets/image1.png"
        body = pf.Para(pf.Image(pf.Str("그림"), url=url))
        pipe = make_table([[cell(txt("h"))]], [[cell(pf.Plain(pf.Image(pf.Str("그림"), url=url)))]])
        html = make_table(
            [[cell(txt("a")), cell(txt("b"))]],
            [[cell(pf.Plain(pf.Image(pf.Str("그림"), url=url)), colspan=2)]],
        )
        got = back(write_md(doc_with(body, pipe, html), {}))
        assert image_urls(got) == [url] * 3, stem


def image_urls(doc: pf.Doc) -> list[str]:
    urls: list[str] = []
    doc.walk(lambda e, d: urls.append(e.url) if isinstance(e, pf.Image) else None)
    return urls


def test_copy_element_copies_content_not_ancestors():
    from mdcast.ast import clone, copy_element

    # a loaded document has parent links (a hand-built one does not)
    doc = clone(pf.Doc(*[pf.Para(pf.Str(str(i))) for i in range(3)], pf.Para(pf.Str("a"), pf.Note(pf.Para(pf.Str("n"))))))
    para = doc.content[3]
    copied = copy_element(para)
    assert copied is not para and copied.content[1] is not para.content[1]
    assert copied.to_json() == para.to_json()
    assert copied.parent is doc  # the document itself was not copied
    copied.content[0].text = "b"
    assert pf.stringify(para).startswith("a")


def test_table_inside_a_cell_note_keeps_its_cells():
    inner = make_table([[cell(txt("n1")), cell(txt("n2"))]], [[cell(txt("n3")), cell(txt("n4"))]])
    note = pf.Note(pf.Para(pf.Str("앞")), inner)
    merged = make_table(
        [[cell(txt("h1")), cell(txt("h2"))]],
        [[cell(pf.Plain(pf.Str("x"), note), rowspan=2), cell(txt("y"))], [cell(txt("z"))]],
    )
    md = write_md(doc_with(merged), {})
    assert "mdcast-cell" not in md
    assert all(text in md for text in ("n1", "n2", "n3", "n4"))
    assert all(text in note_texts(back(md))[0] for text in ("앞", "n1", "n4"))


def aligns(table: pf.Table) -> list[str]:
    return [a for a, _ in table.colspec]


def cell_aligns(table: pf.Table) -> list[list[str]]:
    rows = [r for body in table.content for r in body.content]
    return [[c.alignment for c in r.content] for r in rows]


def test_html_table_keeps_column_alignment():
    captioned = make_table(
        [[cell(txt("항목")), cell(txt("값")), cell(txt("비고"))]],
        [[cell(txt("가")), cell(txt("1")), cell(txt("중앙"))], [cell(txt("나")), cell(txt("2")), cell(txt("중앙"))]],
        caption=[pf.Plain(pf.Str("요약"))],
    )
    captioned.colspec = [("AlignLeft", "ColWidthDefault"), ("AlignRight", "ColWidthDefault"), ("AlignCenter", "ColWidthDefault")]
    md = write_md(doc_with(captioned), {})
    assert '<td align="right">1</td>' in md and "<th>값</th>" in md
    got = tables(back(md))[0]
    assert aligns(got) == ["AlignLeft", "AlignRight", "AlignCenter"]
    assert cell_aligns(got) == [["AlignDefault"] * 3] * 2  # like a pipe table: the column holds it


def test_html_table_alignment_survives_a_spanning_first_row():
    table = make_table(
        [[cell(txt("a")), cell(txt("b"))]],
        [[cell(txt("합친 칸"), colspan=2)], [cell(txt("1")), cell(txt("2"))]],
    )
    table.colspec = [("AlignCenter", "ColWidthDefault"), ("AlignRight", "ColWidthDefault")]
    md = write_md(doc_with(table), {})
    assert '<td colspan="2">합친 칸</td>' in md  # its columns disagree: no alignment of its own
    got = tables(back(md))[0]
    assert aligns(got) == ["AlignCenter", "AlignRight"]
    assert cell_aligns(got) == [["AlignDefault"], ["AlignDefault"] * 2]


def kinds(doc: pf.Doc) -> list[str]:
    return [type(b).__name__ for b in doc.content]


def colon_line(*before: pf.Inline) -> pf.Para:
    return pf.Para(*before, pf.LineBreak(), pf.Str(":"), pf.Space(), pf.Str("b"))


def test_line_starting_with_colon_after_hard_break_stays_text():
    r"""``a\`` then ``: b`` would read back as a definition list (term + definition)."""
    cases = [
        doc_with(colon_line(pf.Str("a"))),
        doc_with(pf.Para(pf.Str("a")), pf.Para(pf.Str(":"), pf.Space(), pf.Str("b"))),
        doc_with(pf.Para(pf.Str("a"), pf.LineBreak(), pf.Str("~"), pf.Space(), pf.Str("b"))),
        doc_with(pf.Para(pf.Strong(pf.Str("a"), pf.LineBreak(), pf.Str(":"), pf.Space(), pf.Str("b")))),
        doc_with(pf.Para(pf.Strong(pf.Str("a"), pf.LineBreak()), pf.Str(":"), pf.Space(), pf.Str("b"))),
        doc_with(pf.Para(pf.Emph(pf.Str("a"), pf.LineBreak()), pf.Str(":"), pf.Space(), pf.Str("b"))),
        doc_with(pf.BulletList(pf.ListItem(pf.Plain(pf.Str("a"), pf.LineBreak(), pf.Str(":"), pf.Space(), pf.Str("b"))))),
        doc_with(pf.Para(pf.Str("x")), pf.BlockQuote(pf.Para(pf.Str("a")), pf.Para(pf.Str(":"), pf.Space(), pf.Str("b")))),
    ]
    for doc in cases:
        md = write_md(doc, {})
        again = back(md)
        assert kinds(again) == kinds(doc), md
        assert pf.stringify(again) == pf.stringify(doc), md
        assert first_or_none(again, pf.DefinitionList) is None, md
        assert "\\: b" in md or "\\~ b" in md, md


def test_break_at_the_end_of_a_container_puts_the_next_text_at_a_line_start():
    from mdcast.writers.md import _escape_line_starts

    for kind in (pf.Strong, pf.Emph):
        para = pf.Para(kind(pf.Str("a"), pf.LineBreak()), pf.Str(":"), pf.Space(), pf.Str("b"))
        _escape_line_starts(para.content, True)
        assert [type(e).__name__ for e in para.content][1:3] == ["RawInline", "Space"]


def test_breaks_at_the_edge_of_emphasis_keep_their_shape():
    r"""``**a\`` + newline + ``**`` would read back as literal asterisks: the break goes outside."""
    cases = [
        (pf.Para(pf.Strong(pf.Str("a"), pf.LineBreak()), pf.Str("b")), ["Strong", "LineBreak", "Str"]),
        (pf.Para(pf.Emph(pf.Str("a"), pf.LineBreak()), pf.Str("b")), ["Emph", "LineBreak", "Str"]),
        (pf.Para(pf.Strikeout(pf.Str("a"), pf.LineBreak()), pf.Str("b")), ["Strikeout", "LineBreak", "Str"]),
        (pf.Para(pf.Str("a"), pf.Strong(pf.LineBreak(), pf.Str("b"))), ["Str", "LineBreak", "Strong"]),
        (pf.Para(pf.Strong(pf.Emph(pf.Str("a"), pf.LineBreak())), pf.Str("b")), ["Strong", "LineBreak", "Str"]),
        # pandoc writes no space before a hard break
        (pf.Para(pf.Strong(pf.Str("a"), pf.Space(), pf.LineBreak()), pf.Str("b")), ["Strong", "LineBreak", "Str"]),
    ]
    for para, shape in cases:
        md = write_md(doc_with(para), {})
        again = back(md)
        assert [type(e).__name__ for e in again.content[0].content] == shape, md
        assert "*" not in pf.stringify(again), md
        # written again, it comes back the same
        assert back(write_md(again, {})).content[0].to_json() == again.content[0].to_json(), md


def first_or_none(doc: pf.Doc, kind):
    found: list = []
    doc.walk(lambda e, d: found.append(e) if isinstance(e, kind) else None)
    return found[0] if found else None


def test_colon_inside_a_line_is_not_escaped():
    md = write_md(doc_with(pf.Para(pf.Str("a:"), pf.Space(), pf.Str("b"), pf.LineBreak(), pf.Str(":b"))), {})
    assert r"\:" not in md


def test_colon_line_in_a_cell_note_stays_text():
    note = pf.Note(pf.Para(pf.Str("n")), pf.Para(pf.Str(":"), pf.Space(), pf.Str("m")))
    doc = doc_with(make_table([[cell(txt("h")), cell(txt("i"))]], [[cell(pf.Plain(pf.Str("v"), note), colspan=2)]]))
    again = back(write_md(doc, {}))
    assert first_or_none(again, pf.DefinitionList) is None
    assert [type(b).__name__ for b in first(again, pf.Note).content] == ["Para", "Para"]


def test_hard_break_in_heading_is_written_as_space():
    """An ATX heading is one line: a hard break would end it and push the rest into a paragraph."""
    doc = doc_with(
        pf.Header(pf.Strong(pf.Str("a")), pf.LineBreak(), pf.Str(":"), pf.Space(), pf.Str("b"), level=3),
        pf.Para(pf.Str("c")),
    )
    again = back(write_md(doc, {}))
    assert kinds(again) == ["Header", "Para"]
    assert pf.stringify(again.content[0]) == "a : b"


def test_superscript_and_subscript_round_trip():
    doc = doc_with(pf.Para(pf.Str("x"), pf.Superscript(pf.Str("*")), pf.Str("y"), pf.Subscript(pf.Str("2"))))
    again = back(write_md(doc, {}))
    assert [type(i).__name__ for i in again.content[0].content] == ["Str", "Superscript", "Str", "Subscript"]
    assert pf.stringify(again) == pf.stringify(doc)



def scripts(doc: pf.Doc) -> list[pf.Element]:
    found: list = []
    doc.walk(lambda e, d: found.append(e) if isinstance(e, (pf.Superscript, pf.Subscript)) else None)
    return found


def paired() -> list[list[pf.Inline]]:
    """Text pandoc's markdown would read as ``~sub~`` / ``^super^`` if written bare."""
    return [
        [pf.Str("서울~대전~부산")],
        [pf.Str("1~2~3단계")],
        [pf.Str("2^10^")],
        [pf.Str("a~b~c~d")],
        [pf.Str("~~x~~")],
        [pf.Str("a~\u00a0b~c")],  # a no-break space does not end a pair
        [pf.Str("서울~"), pf.Strong(pf.Str("대전")), pf.Str("~부산")],  # one pair over three inlines
        [pf.Str("가^"), pf.Str("나^다")],
    ]


def test_tilde_and_caret_pairs_in_body_and_heading_stay_text():
    for make in (lambda i: pf.Para(*i), lambda i: pf.Header(*i, level=2)):
        for inlines in paired():
            doc = doc_with(make(inlines), pf.Para(pf.Str("끝")))
            md = write_md(doc, {})
            again = back(md)
            assert kinds(again) == kinds(doc), md
            assert scripts(again) == [], md
            assert pf.stringify(again) == pf.stringify(doc), md


def test_tilde_and_caret_pairs_in_pipe_cells_stay_text():
    for inlines in paired():
        if "\u00a0" in pf.stringify(pf.Plain(*inlines)):
            continue  # a pipe cell's text is squeezed: its no-break space becomes a space (as before)
        doc = doc_with(make_table([[cell(txt("h")), cell(txt("i"))]], [[cell(pf.Plain(*inlines)), cell(txt("2^3^"))]]))
        md = write_md(doc, {})
        assert "<table>" not in md, md
        again = back(md)
        assert scripts(again) == [], md
        assert pf.stringify(again) == pf.stringify(doc), md


def test_tilde_and_caret_pairs_in_cell_notes_stay_text():
    for inlines in paired():
        note = pf.Note(pf.Para(*inlines), pf.Para(pf.Str("x^y^z")))
        doc = doc_with(make_table([[cell(txt("h")), cell(txt("i"))]], [[cell(pf.Plain(pf.Str("v"), note), colspan=2)]]))
        md = write_md(doc, {})
        assert "[^t1]:" in md, md
        again = back(md)
        assert scripts(again) == [], md
        assert pf.stringify(first(again, pf.Note)) == pf.stringify(note), md


def test_tilde_pairs_in_html_cells_are_left_bare():
    """An HTML cell reads ``~`` as text, and a raw gfm escape there would be dropped."""
    doc = doc_with(make_table([[cell(txt("h")), cell(txt("i"))]], [[cell(txt("서울~대전~부산"), colspan=2)]]))
    md = write_md(doc, {})
    assert "<table>" in md and "\\" not in md, md
    again = back(md)
    assert scripts(again) == []
    assert pf.stringify(again) == pf.stringify(doc)


def test_lone_tilde_and_pairs_split_by_spaces_are_not_escaped():
    lone = [
        [pf.Str("2026.1~2026.12")],
        [pf.Str("10~20"), pf.Space(), pf.Str("%")],
        [pf.Str("a~b"), pf.Space(), pf.Str("c~d")],
        [pf.Str("x^2"), pf.Space(), pf.Str("y^2")],
    ]
    for inlines in lone:
        doc = doc_with(pf.Para(pf.Str("앞"), pf.Space(), *inlines))
        md = write_md(doc, {})
        assert "\\" not in md, md
        assert pf.stringify(back(md)) == pf.stringify(doc), md


def test_real_scripts_are_still_written_as_tags_beside_escaped_pairs():
    doc = doc_with(pf.Para(pf.Str("a~b~c"), pf.Superscript(pf.Str("2")), pf.Subscript(pf.Str("i"))))
    md = write_md(doc, {})
    assert "<sup>2</sup>" in md and "<sub>i</sub>" in md, md
    again = back(md)
    assert [type(i).__name__ for i in again.content[0].content] == ["Str", "Superscript", "Subscript"]
    assert pf.stringify(again) == pf.stringify(doc)


def test_tilde_and_caret_pairs_across_emphasis_and_links_stay_text():
    across = [
        [pf.Str("a~"), pf.Strong(pf.Str("b~c"))],
        [pf.Strong(pf.Str("a~b")), pf.Str("~c")],
        [pf.Emph(pf.Str("a~b")), pf.Strong(pf.Str("c~d"))],
        [pf.Str("x^"), pf.Emph(pf.Str("y^z"))],
        [pf.Str("a~"), pf.Link(pf.Str("b~c"), url="http://x")],
    ]
    for inlines in across:
        doc = doc_with(pf.Para(*inlines))
        md = write_md(doc, {})
        again = back(md)
        assert scripts(again) == [], md
        assert pf.stringify(again) == pf.stringify(doc), md


def test_tildes_beside_and_inside_strikeout_stay_text():
    cases = [
        [pf.Str("10~"), pf.Strikeout(pf.Str("x"))],
        [pf.Strikeout(pf.Str("x")), pf.Str("~10")],
        [pf.Strikeout(pf.Str("a~b"))],
        [pf.Str("a~"), pf.Strikeout(pf.Str("b~c"))],
        [pf.Strikeout(pf.Str("a"), pf.Space(), pf.Str("10~20"), pf.Space(), pf.Str("b"))],
        [pf.Str("10~20"), pf.Strikeout(pf.Str("x"))],
    ]
    for inlines in cases:
        doc = doc_with(pf.Para(*inlines))
        md = write_md(doc, {})
        again = back(md)
        assert scripts(again) == [], md
        assert kinds(again) == kinds(doc) and len(strikes(again)) == 1, md
        assert pf.stringify(again) == pf.stringify(doc), md


def strikes(doc: pf.Doc) -> list[pf.Strikeout]:
    found: list = []
    doc.walk(lambda e, d: found.append(e) if isinstance(e, pf.Strikeout) else None)
    return found


def test_tilde_and_caret_pairs_in_frontmatter_title_and_author_stay_text():
    from mdcast.readers.md import read_md

    for text in ("서울~대전~부산", "2^10^", "a~b~c d^e", "2026.1~2026.12"):
        md = write_md(doc_with(pf.Para(pf.Str("x"))), {"title": text, "author": [text, "b"]})
        meta = read_md(Source(md.encode(), "t.md", Format.MD), Report("t.md", Format.MD)).frontmatter
        assert meta["title"] == text, md
        assert meta["author"] == [text, "b"], md


def _merged_with(text: str) -> pf.Table:
    return make_table([[cell(txt("h"), colspan=2)]], [[cell(txt(text)), cell(pf.Plain(pf.Code(text)))]])


def test_html_cell_gets_no_variation_selector_from_pandoc():
    """pandoc's HTML writer puts U+FE0E after the two arrows; the MD keeps the cell's own text."""
    text = "a\u2194b \u21a9c"
    md = write_md(doc_with(_merged_with(text)), {})
    assert "<table>" in md and "\ufe0e" not in md
    got = tables(back(md))[0].content[0].content[0].content
    assert [pf.stringify(c).strip() for c in got] == [text, text]


def test_html_cell_keeps_a_variation_selector_it_has():
    for text in ("a\u2194\ufe0eb", "a\u2194\ufe0fb"):
        md = write_md(doc_with(_merged_with(text)), {})
        got = tables(back(md))[0].content[0].content[0].content
        assert [pf.stringify(c).strip() for c in got] == [text, text]


def test_highlighted_code_in_html_cell_keeps_its_arrow():
    """Code with a language class is highlighted: it gets no selector from pandoc and is not shielded."""
    text = "a\u2194b"
    for lang in ("python", "haskell", "c"):
        table = make_table(
            [[cell(txt("h"), colspan=2)]],
            [[cell(pf.CodeBlock(text, classes=[lang])), cell(pf.Plain(pf.Code(text, classes=[lang])))]],
        )
        md = write_md(doc_with(table), {})
        assert "mdcast-cell" not in md and "\ufe0e" not in md
        block, inline = tables(back(md))[0].content[0].content[0].content
        assert first(block, pf.CodeBlock).text == text
        assert first(inline, pf.Code).text == text
