from __future__ import annotations

from pathlib import Path

import panflute as pf
from hwpx_builder import cell as hcell
from hwpx_builder import hwpx_bytes, p, run, tbl

from mdcast.filters.importing import ImportContext, forms, run_import_filters
from mdcast.pipeline import convert
from mdcast.readers.md import read_md
from mdcast.report import Codes, Level, Report
from mdcast.types import Format, Source

LONG = "가" * 100


def inlines(text: str) -> list[pf.Inline]:
    out: list[pf.Inline] = []
    for i, word in enumerate(text.split(" ")):
        if i:
            out.append(pf.Space())
        out.append(pf.Str(word))
    return out


def para(text: str) -> pf.Para:
    return pf.Para(*inlines(text))


def plain(text: str) -> pf.Plain:
    return pf.Plain(*inlines(text))


def bold(text: str) -> pf.Plain:
    return pf.Plain(pf.Strong(*inlines(text)))


def cell(*blocks: pf.Block, colspan: int = 1, rowspan: int = 1) -> pf.TableCell:
    return pf.TableCell(*blocks, colspan=colspan, rowspan=rowspan)


def wide(*blocks: pf.Block) -> pf.TableCell:
    return cell(*blocks, colspan=2)


def table(
    *rows: list[pf.TableCell], cols: int = 2, head: int = 0, caption: str | None = None
) -> pf.Table:
    trs = [pf.TableRow(*cells) for cells in rows]
    cap = pf.Caption(para(caption)) if caption else pf.Caption()
    return pf.Table(
        pf.TableBody(*trs[head:]),
        head=pf.TableHead(*trs[:head]),
        caption=cap,
        colspec=[("AlignDefault", "ColWidthDefault")] * cols,
    )


def two_paras(tag: str) -> list[pf.Para]:
    return [para(f"{tag} 첫 문단"), para(f"{tag} 둘째 문단")]


def side_by_side(*labels: str, head: int = 1) -> pf.Table:
    return table(*[[cell(plain(label)), cell(*two_paras(label))] for label in labels], head=head)


class Run:
    def __init__(self, *blocks: pf.Block, frontmatter=None, pipeline: bool = False):
        self.report = Report("a.docx", Format.DOCX)
        self.ctx = ImportContext(self.report, dict(frontmatter or {}), {}, Path("."), Path("."))
        doc = pf.Doc(*blocks)
        self.doc = run_import_filters(doc, self.ctx) if pipeline else forms.apply(doc, self.ctx)

    @property
    def shape(self) -> list[tuple]:
        out: list[tuple] = []
        for b in self.doc.content:
            if isinstance(b, pf.Header):
                out.append(("Header", b.level, pf.stringify(b).strip()))
            else:
                out.append((type(b).__name__, pf.stringify(b).strip()))
        return out

    def events(self, code: str, level: Level | None = None):
        return [
            e for e in self.report.events if e.code == code and (level is None or e.level is level)
        ]


def _has_strong(elem: pf.Element) -> bool:
    found: list = []
    elem.walk(lambda e, _d: found.append(e) if isinstance(e, pf.Strong) else None)
    return bool(found)


# --- unwrapping ---------------------------------------------------------------------------------


def test_side_by_side_form_unwraps_in_order():
    # first row in TableHead, as hwpx gives it without header marks
    r = Run(side_by_side("이름", "주소"))
    assert r.shape == [
        ("Header", 1, "이름"),
        ("Para", "이름 첫 문단"),
        ("Para", "이름 둘째 문단"),
        ("Header", 1, "주소"),
        ("Para", "주소 첫 문단"),
        ("Para", "주소 둘째 문단"),
    ]
    infos = r.events(Codes.IMPORT_TABLE_UNWRAPPED)
    assert [(e.level, e.message) for e in infos] == [
        (Level.INFO, "서식 표 1개를 제목과 본문으로 풀었습니다")
    ]


def test_stacked_form_unwraps_and_empty_content_keeps_label():
    # bold split over runs
    label = pf.Plain(pf.Strong(pf.Str("제품")), pf.Space(), pf.Strong(pf.Str("설명")))
    t = table(
        [wide(bold("제품명"))],
        [wide(*two_paras("제품"))],
        [wide(label)],
        [wide(plain(LONG))],
        [wide(bold("사진"))],
        [wide(pf.Plain())],  # an empty paragraph leaves nothing behind
        head=1,
    )
    r = Run(t)
    assert r.shape == [
        ("Header", 1, "제품명"),
        ("Para", "제품 첫 문단"),
        ("Para", "제품 둘째 문단"),
        ("Header", 1, "제품 설명"),
        ("Para", LONG),
        ("Header", 1, "사진"),
    ]
    assert not any(_has_strong(b) for b in r.doc.content if isinstance(b, pf.Header))


def test_stacked_form_whose_last_row_is_a_label():
    t = table([wide(bold("가"))], [wide(*two_paras("가"))], [wide(bold("나"))])
    assert [kind for kind, _, _ in forms.classify(t)] == ["stack", "stack"]
    assert forms.classify(t)[1][2] is None
    assert Run(t).shape[-1] == ("Header", 1, "나")


def test_side_by_side_then_stacked_rows_unwrap_together():
    t = table(
        [cell(plain("개요")), cell(*two_paras("개요"))],
        [wide(bold("세부"))],
        [wide(*two_paras("세부"))],
        head=1,
    )
    assert [kind for kind, _, _ in forms.classify(t)] == ["pair", "stack"]
    assert [s for s in Run(t).shape if s[0] == "Header"] == [
        ("Header", 1, "개요"),
        ("Header", 1, "세부"),
    ]


def test_label_level_is_one_below_preceding_header():
    r = Run(pf.Header(*inlines("개요"), level=2), side_by_side("가", "나"))
    assert [s for s in r.shape if s[0] == "Header"] == [
        ("Header", 2, "개요"),
        ("Header", 3, "가"),
        ("Header", 3, "나"),
    ]
    deep = Run(pf.Header(pf.Str("깊음"), level=6), side_by_side("가", "나"))
    assert [s[1] for s in deep.shape if s[0] == "Header"] == [6, 6, 6]


def test_sibling_forms_share_the_level_of_the_heading_above():
    r = Run(pf.Header(pf.Str("개요"), level=1), side_by_side("가", "나"), side_by_side("다", "라"))
    assert [s[1] for s in r.shape if s[0] == "Header"] == [1, 2, 2, 2, 2]


def test_content_table_becomes_top_level_and_is_rejudged():
    inner_form = side_by_side("안 가", "안 나", head=0)
    grid = table(
        [cell(plain("열1")), cell(plain("열2")), cell(plain("열3"))],
        [cell(plain("1")), cell(plain("2")), cell(plain("3"))],
        cols=3,
        head=1,
    )
    outer = table(
        [wide(bold("구성"))],
        [wide(para("앞 글"), inner_form)],
        [wide(bold("표"))],
        [wide(grid)],
    )
    r = Run(pf.Header(pf.Str("문서"), level=1), outer)
    assert r.shape[:7] == [
        ("Header", 1, "문서"),
        ("Header", 2, "구성"),
        ("Para", "앞 글"),
        ("Header", 3, "안 가"),
        ("Para", "안 가 첫 문단"),
        ("Para", "안 가 둘째 문단"),
        ("Header", 3, "안 나"),
    ]
    assert r.shape[9] == ("Header", 2, "표")
    assert isinstance(r.doc.content[10], pf.Table) and len(r.doc.content) == 11
    assert "서식 표 2개" in r.events(Codes.IMPORT_TABLE_UNWRAPPED)[0].message


def test_plain_content_becomes_para_but_cells_of_kept_tables_stay_plain():
    t = table([cell(plain("가")), cell(plain(LONG))], [cell(plain("나")), cell(plain(LONG))])
    r = Run(t)
    assert [type(b).__name__ for b in r.doc.content] == ["Header", "Para", "Header", "Para"]


def test_header_inside_content_stays_below_its_label():
    t = table(
        [cell(plain("가")), cell(pf.Header(pf.Str("칸 제목"), level=1), para(LONG))],
        [cell(plain("나")), cell(*two_paras("나"))],
    )
    r = Run(pf.Header(pf.Str("위"), level=1), t)
    assert [s for s in r.shape if s[0] == "Header"][:3] == [
        ("Header", 1, "위"),
        ("Header", 2, "가"),
        ("Header", 3, "칸 제목"),
    ]


def test_line_break_in_label_becomes_space():
    label = pf.Plain(pf.Str("제품"), pf.LineBreak(), pf.Str("이름"))
    r = Run(
        table([cell(label), cell(*two_paras("가"))], [cell(plain("나")), cell(*two_paras("나"))])
    )
    first = r.doc.content[0]
    assert isinstance(first, pf.Header) and pf.stringify(first) == "제품 이름"
    assert not any(isinstance(i, (pf.LineBreak, pf.SoftBreak)) for i in first.content)


def test_caption_and_foot_rows_are_not_lost():
    t = side_by_side("가", "나")
    t.caption = pf.Caption(para("표 이름"))
    t.foot = pf.TableFoot(pf.TableRow(cell(plain("다")), cell(*two_paras("다"))))
    r = Run(t)
    texts = [s[-1] for s in r.shape]
    assert "표 이름" in texts and ("Header", 1, "다") in r.shape


# --- tables that stay -----------------------------------------------------------------------------


def test_grid_with_column_names_stays():
    t = table(
        [cell(plain("평가 항목")), cell(plain("주요내용")), cell(plain("배점"))],
        [cell(plain("기술성")), cell(*two_paras("가")), cell(plain("30"))],
        cols=3,
        head=1,
    )
    assert forms.classify(t) is None
    r = Run(t)
    assert [type(b).__name__ for b in r.doc.content] == ["Table"]
    assert r.events(Codes.IMPORT_TABLE_UNWRAPPED) == []


def test_short_value_two_column_table_stays():
    t = table(
        *[[cell(plain(name)), cell(plain("짧은 값"))] for name in ("이름", "주소", "전화", "담당")]
    )
    assert forms.classify(t) is None


def test_mixed_rows_table_stays():
    t = table(
        [wide(bold("통짜 제목"))],
        [cell(plain("가")), cell(*two_paras("가"))],
        [cell(plain("나")), cell(*two_paras("나"))],
    )
    assert forms.classify(t) is None


def test_rowspan_label_table_stays():
    t = table(
        [cell(plain("가"), rowspan=2), cell(*two_paras("가"))],
        [cell(*two_paras("가 아래"))],
        [cell(plain("나")), cell(*two_paras("나"))],
    )
    assert forms.classify(t) is None


def test_label_rules_reject():
    def pair_table(label: pf.TableCell) -> pf.Table:
        return table([label, cell(*two_paras("가"))], [cell(plain("나")), cell(*two_paras("나"))])

    assert forms.classify(pair_table(cell(plain("가" * 41)))) is None  # too long
    assert (
        forms.classify(pair_table(cell(plain("가" * 20 + " " + "나" * 20)))) is not None
    )  # spaces not counted
    assert forms.classify(pair_table(cell(plain("□ 항목")))) is None  # list marker
    assert forms.classify(pair_table(cell(plain("가"), plain("나")))) is None  # two blocks
    assert forms.classify(pair_table(cell())) is None  # empty label
    one = table([cell(plain("가")), cell(*two_paras("가"))])
    assert forms.classify(one) is None  # a single label
    stacked_not_bold = table(
        [wide(plain("가"))], [wide(*two_paras("가"))], [wide(plain("나"))], [wide(*two_paras("나"))]
    )
    assert forms.classify(stacked_not_bold) is None


def test_column_name_row_table_stays():
    # first row is all bold short names over both columns: a header row, not label | content
    names = [cell(bold("구분")), cell(bold("내용"))]
    t = table(names, *[[cell(plain(n)), cell(plain(LONG))] for n in ("가", "나", "다")], head=1)
    assert forms.classify(t) is None
    # a bold label beside non-bold content is still a form row
    t2 = table(
        [cell(bold("구분")), cell(plain(LONG))],
        *[[cell(plain(n)), cell(plain(LONG))] for n in ("가", "나")],
    )
    assert forms.classify(t2) is not None


def test_two_column_table_without_rows_stays():
    t = table([cell(plain("가")), cell(*two_paras("가"))])
    t.content[0].content.clear()  # an hwpx table with no rows (panflute checks columns only when built)
    assert forms.classify(t) is None
    r = Run(t)
    assert [type(b).__name__ for b in r.doc.content] == ["Table"]


def test_mdcast_document_tables_are_never_unwrapped():
    """R21: a table in an mdcast-made document was an MD table; its header bold is gone by now."""
    t = side_by_side("이름", "주소")
    assert forms.classify(t) is not None  # a form anywhere else
    report = Report("a.hwpx", Format.HWPX)
    ctx = ImportContext(report, {}, {"mdcast.generator": "mdcast 0.1"}, Path("."), Path("."))
    doc = forms.apply(pf.Doc(t), ctx)
    assert [type(b).__name__ for b in doc.content] == ["Table"]
    assert [e for e in report.events if e.code == Codes.IMPORT_TABLE_UNWRAPPED] == []


def test_picture_cell_is_not_a_label():
    pic = pf.Plain(pf.Image(pf.Str("그림"), url="a.png"))
    t = table(
        [cell(pic), cell(*two_paras("가"))],
        [cell(plain("나")), cell(*two_paras("나"))],
        [cell(plain("다")), cell(*two_paras("다"))],
    )
    assert forms.classify(t) is None


def test_labels_without_content_stay():
    t = table([wide(bold("가"))], [wide()], [wide(bold("나"))], [wide()])
    assert forms.classify(t) is None


def test_image_only_content_counts_as_long():
    pic = pf.Plain(pf.Image(url="a.png"))
    t = table([cell(plain("사진")), cell(pic)], [cell(plain("설명")), cell(plain("짧음"))])
    assert forms.classify(t) is not None


# --- with the other filters -------------------------------------------------------------------------


def test_no_heading_warning_when_form_made_headings():
    r = Run(para("본문"), side_by_side("가", "나"), pipeline=True)
    assert r.events(Codes.IMPORT_HEADING_INFERRED, Level.WARN) == []
    assert len(r.events(Codes.IMPORT_TABLE_UNWRAPPED, Level.INFO)) == 1


def test_document_without_headings_still_warns_once():
    short = table(*[[cell(plain(name)), cell(plain("값"))] for name in ("이름", "주소")])
    r = Run(para("편지 본문"), short, pipeline=True)
    assert r.events(Codes.IMPORT_TABLE_UNWRAPPED) == []
    assert [e.level for e in r.events(Codes.IMPORT_HEADING_INFERRED)] == [Level.WARN]


def test_bold_line_before_form_is_not_made_document_title():
    r = Run(pf.Para(pf.Strong(pf.Str("안내문"))), side_by_side("가", "나"), pipeline=True)
    assert r.shape[0] == ("Para", "안내문")
    assert [s[1] for s in r.shape if s[0] == "Header"] == [1, 1]
    assert "title" not in r.ctx.frontmatter


def test_labels_sit_below_an_inferred_heading():
    r = Run(pf.Para(pf.Strong(*inlines("1. 개요"))), side_by_side("가", "나"), pipeline=True)
    assert [s for s in r.shape if s[0] == "Header"] == [
        ("Header", 1, "1. 개요"),
        ("Header", 2, "가"),
        ("Header", 2, "나"),
    ]


def test_hand_numbered_content_stays_list_and_body():
    content = cell(
        para("□ 첫째"), para("□ 둘째"), pf.Para(pf.Strong(*inlines("1. 세부 사항"))), para(LONG)
    )
    t = table([cell(plain("가")), content], [cell(plain("나")), cell(*two_paras("나"))])
    r = Run(t, pipeline=True)
    assert [s[0] for s in r.shape] == [
        "Header",
        "BulletList",
        "Para",
        "Para",
        "Header",
        "Para",
        "Para",
    ]
    assert r.shape[2] == ("Para", "1. 세부 사항")
    assert [s[1] for s in r.shape if s[0] == "Header"] == [1, 1]


# --- end to end ---------------------------------------------------------------------------------------


def _hwpx_form() -> bytes:
    inner = tbl(
        [
            [
                hcell(p(run("머리 가")), col=0, row=0),
                hcell(p(run("머리 나")), col=1, row=0),
                hcell(p(run("머리 다")), col=2, row=0),
            ],
            [
                hcell(p(run("일")), col=0, row=1),
                hcell(p(run("이")), col=1, row=1),
                hcell(p(run("삼")), col=2, row=1),
            ],
        ],
        cols=3,
    )
    rows = [
        [
            hcell(p(run("개요")), col=0, row=0),
            hcell(p(run("개요 첫 문단")), p(run("개요 둘째 문단")), col=1, row=0),
        ],
        [hcell(p(run("세부 항목", "1")), col=0, row=1, colspan=2)],
        [hcell(p(run("세부 설명")), p(inner), col=0, row=2, colspan=2)],
        [hcell(p(run("빈 항목", "1")), col=0, row=3, colspan=2)],
        [hcell(p(), col=0, row=4, colspan=2)],
    ]
    return hwpx_bytes(p(run("앞 글")), p(tbl(rows, cols=2)), p(run("뒤 글")))


def test_hwpx_form_converts_without_loss_and_reads_back():
    result = convert(Source(_hwpx_form(), "a.hwpx", Format.HWPX), [Format.MD])
    assert result.report.coverage == 1.0
    assert len([e for e in result.report.events if e.code == Codes.IMPORT_TABLE_UNWRAPPED]) == 1
    md = result.outputs[0].data
    back = read_md(Source(md, "a.md", Format.MD), Report("a.md", Format.MD)).doc.content
    shape = [(type(b).__name__, getattr(b, "level", None)) for b in back]
    assert shape == [
        ("Para", None),
        ("Header", 1),
        ("Para", None),
        ("Para", None),
        ("Header", 1),
        ("Para", None),
        ("Table", None),
        ("Header", 1),
        ("Para", None),
    ]
    assert [pf.stringify(b).strip() for b in back if isinstance(b, pf.Header)] == [
        "개요",
        "세부 항목",
        "빈 항목",
    ]
