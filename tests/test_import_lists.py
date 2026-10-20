from __future__ import annotations

from pathlib import Path

import panflute as pf

from mdcast.filters.importing import ImportContext, run_import_filters
from mdcast.report import Codes, Level, Report
from mdcast.types import Format


def para(text: str) -> pf.Para:
    out: list[pf.Inline] = []
    for i, word in enumerate(text.split(" ")):
        if i:
            out.append(pf.Space())
        out.append(pf.Str(word))
    return pf.Para(*out)


def plain(text: str) -> pf.Plain:
    return pf.Plain(*para(text).content)


def item(text: str) -> pf.ListItem:
    return pf.ListItem(plain(text))


class Run:
    def __init__(self, *blocks):
        self.report = Report("a.docx", Format.DOCX)
        self.ctx = ImportContext(self.report, {}, {}, Path("."), Path("."))
        self.doc = run_import_filters(pf.Doc(*blocks), self.ctx)

    @property
    def content(self):
        return self.doc.content

    def events(self, level: Level):
        return [e for e in self.report.events if e.code == Codes.IMPORT_LIST_INFERRED and e.level is level]


def run(*blocks) -> pf.Doc:
    return Run(*blocks).doc


def items(lst) -> list[str]:
    return [pf.stringify(i.content[0]).strip() for i in lst.content]


def shape(doc) -> list:
    def one(lst):
        out: list = []
        for li in lst.content:
            out.append(pf.stringify(li.content[0]).strip())
            for sub in li.content[1:]:
                out.append([one(sub)])
        return ("bullet" if isinstance(lst, pf.BulletList) else "ordered", out)

    return [one(b) for b in doc.content if isinstance(b, (pf.BulletList, pf.OrderedList))]


def test_bullet_symbols_nest_by_first_appearance():
    doc = run(para("□ 가"), para("○ 나"), para("- 다"), para("○ 라"), para("□ 마"))
    assert shape(doc) == [("bullet", ["가", [("bullet", ["나", [("bullet", ["다"])], "라"])], "마"])]


def test_typed_numbers_become_ordered_with_start():
    doc = run(para("3) 셋"), para("4) 넷"))
    lst = doc.content[0]
    assert isinstance(lst, pf.OrderedList) and lst.start == 3 and items(lst) == ["셋", "넷"]


def test_typed_numbers_continue_preceding_auto_list():
    doc = run(pf.OrderedList(item("하나")), para("2) 둘"), para("3) 셋"))
    assert len(doc.content) == 1 and items(doc.content[0]) == ["하나", "둘", "셋"]


def test_single_continuation_merges_but_lone_dash_does_not():
    doc = run(pf.OrderedList(item("하나")), para("2) 둘"), para("- 혼자인 문장"), para("본문"))
    assert items(doc.content[0]) == ["하나", "둘"] and pf.stringify(doc.content[1]).strip() == "- 혼자인 문장"


def test_items_between_continuing_numbers_nest_under_previous_item():
    doc = run(pf.OrderedList(item("하나")), para("2) 둘"), para("- a"), para("- b"), para("3) 셋"))
    assert len(doc.content) == 1
    lst = doc.content[0]
    assert items(lst) == ["하나", "둘", "셋"]
    sub = lst.content[1].content[1]
    assert isinstance(sub, pf.BulletList) and items(sub) == ["a", "b"]


def test_level_jump_is_clamped_to_one_deeper():
    doc = run(para("□ 가"), para("○ 나"), para("- 다"), para("본문"), para("□ 라"), para("- 마"))
    assert shape(doc)[1] == ("bullet", ["라", [("bullet", ["마"])]])


def test_chunk_starting_deeper_than_its_minimum_is_still_level_one():
    doc = run(para("□ 가"), para("○ 나"), para("본문"), para("○ 다"), para("□ 라"))
    assert len(doc.content) == 3 and items(doc.content[2]) == ["다", "라"]


def test_note_mark_is_not_a_list():
    doc = run(para("※ 주석"), para("※ 주석2"))
    assert all(isinstance(b, pf.Para) for b in doc.content)


def test_lists_inside_table_cells():
    cell = pf.TableCell(plain("○ 가"), plain("○ 나"))
    table = pf.Table(
        pf.TableBody(pf.TableRow(cell)), head=pf.TableHead(), colspec=[("AlignDefault", "ColWidthDefault")]
    )
    doc = run(table)
    lst = doc.content[0].content[0].content[0].content[0].content[0]
    assert isinstance(lst, pf.BulletList) and items(lst) == ["가", "나"]


def test_lists_inside_div_and_blockquote():
    doc = run(pf.Div(para("1) 가"), para("2) 나")), pf.BlockQuote(para("· 다"), para("· 라")))
    assert items(doc.content[0].content[0]) == ["가", "나"]
    assert items(doc.content[1].content[0]) == ["다", "라"]


def test_merged_items_keep_existing_block_type():
    doc = run(pf.OrderedList(pf.ListItem(para("하나"))), para("2) 둘"))
    assert isinstance(doc.content[0].content[1].content[0], pf.Para)


def test_marker_text_is_stripped_and_prefix_registered():
    r = Run(para("□ 가 나"), para("□ 다"))
    assert items(r.content[0]) == ["가 나", "다"]
    assert len(r.ctx.prefixes) == 1 and r.ctx.prefixes[0].match("□ x")


def test_report_counts():
    r = Run(para("○ 가"), para("○ 나"), para("본문"), para("1) 다"), para("2) 라"), para("본문"), para("- 혼자"))
    infos = r.events(Level.INFO)
    assert len(infos) == 1 and "목록 문단 4개" in infos[0].message


def test_no_event_without_lists():
    assert Run(para("본문"), para("- 혼자")).events(Level.INFO) == []
