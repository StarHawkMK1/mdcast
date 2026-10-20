"""THROWAWAY: let Hangul write sample hwpx files for M2b (spec 2026-10-20 section 2)."""

import io
import sys
import traceback
from pathlib import Path

import win32com.client as win32
from PIL import Image

OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
IMG = OUT / "img"
IMG.mkdir(exist_ok=True)


def make_images():
    base = Image.new("RGB", (400, 200), (40, 120, 200))
    base.save(IMG / "a96.png", dpi=(96, 96))
    base.save(IMG / "a300.png", dpi=(300, 300))
    Image.new("RGB", (400, 200), (200, 120, 40)).save(IMG / "nodpi.png")
    base.save(IMG / "a.jpg", dpi=(72, 72))
    base.save(IMG / "a.gif")
    base.save(IMG / "a.bmp")
    base.save(IMG / "a.webp")
    (IMG / "a.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">'
        '<rect width="400" height="200" fill="#2878C8"/></svg>', encoding="utf-8")


make_images()
hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.XHwpWindows.Item(0).Visible = True
print("RegisterModule ->", hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule"))


def text(s):
    pset = hwp.HParameterSet.HInsertText
    hwp.HAction.GetDefault("InsertText", pset.HSet)
    pset.Text = s
    return hwp.HAction.Execute("InsertText", pset.HSet)


def run(name):
    ok = hwp.HAction.Run(name)
    print(f"  Run({name}) -> {ok}")
    return ok


def table(rows, cols):
    pset = hwp.HParameterSet.HTableCreation
    hwp.HAction.GetDefault("TableCreate", pset.HSet)
    pset.Rows = rows
    pset.Cols = cols
    pset.WidthType = 2  # fit to the column
    pset.HeightType = 0
    ok = hwp.HAction.Execute("TableCreate", pset.HSet)
    print(f"  TableCreate({rows}x{cols}) -> {ok}")
    return ok


def fill_cells(values):
    for index, value in enumerate(values):
        if index:
            run("TableRightCell")
        text(value)


def leave_table():
    run("Cancel")
    run("MoveDocEnd")


def picture(name, embedded=True):
    try:
        ctrl = hwp.InsertPicture(str(IMG / name), embedded, 0, False, False, 0)
        print(f"  InsertPicture({name}) -> {ctrl is not None}")
    except Exception as exc:  # noqa: BLE001
        print(f"  InsertPicture({name}) failed: {exc}")


def save(name):
    ok = hwp.SaveAs(str(OUT / name), "HWPX", "")
    print(f"SaveAs {name} -> {ok}")


def sample(name, build):
    print(f"== {name}")
    hwp.Clear(1)
    try:
        build()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    save(name)


def table_basic():
    text("앞 문단")
    run("BreakPara")
    table(2, 3)
    fill_cells(["가", "나", "다", "1", "2", "3"])
    leave_table()
    text("뒤 문단")


def table_merge():
    table(3, 3)
    fill_cells(["a", "b", "c", "d", "e", "f", "g", "h", "i"])
    # merge the first row's b and c
    run("TableUpperCell"); run("TableUpperCell")
    run("TableColBegin")
    run("TableRightCell")
    run("TableCellBlock"); run("TableCellBlockExtend"); run("TableRightCell")
    run("TableMergeCell")
    run("Cancel")
    # merge a over d (vertical)
    run("TableColBegin")
    run("TableCellBlock"); run("TableCellBlockExtend"); run("TableLowerCell")
    run("TableMergeCell")
    leave_table()


def table_caption():
    table(2, 2)
    fill_cells(["가", "나", "다", "라"])
    run("Cancel")
    run("TableCellBlock")
    run("ShapeObjAttachCaption")
    text("표 캡션 글자")
    leave_table()


def footnotes():
    text("본문 하나")
    run("InsertFootnote")
    text("첫 각주")
    run("CloseEx")
    text(" 본문 둘")
    run("InsertFootnote")
    text("둘째 각주 첫 문단")
    run("BreakPara")
    text("둘째 각주 둘째 문단")
    # a footnote inside a footnote: expected to fail
    run("InsertFootnote")
    run("CloseEx")
    text(" 끝")


def footnote_in_cell():
    table(1, 2)
    text("칸")
    run("InsertFootnote")
    text("칸 안 각주")
    run("CloseEx")
    leave_table()


def pictures():
    for name in ("a96.png", "a300.png", "nodpi.png", "a.jpg", "a.gif", "a.bmp", "a.webp", "a.svg"):
        text(f"{name}: ")
        picture(name)
        run("BreakPara")


def picture_twice():
    picture("a96.png")
    run("BreakPara")
    picture("a96.png")


def picture_in_cell():
    table(2, 2)
    picture("a96.png")
    run("TableRightCell")
    picture("a300.png")
    run("TableRightCell")
    text("설명 1")
    run("TableRightCell")
    text("설명 2")
    leave_table()


def picture_caption():
    picture("a96.png")
    run("SelectCtrlFront")
    run("ShapeObjAttachCaption")
    text("그림 캡션 글자")
    run("MoveDocEnd")


def nested():
    table(2, 2)
    table(2, 2)
    fill_cells(["안1", "안2", "안3", "안4"])
    leave_table()


def footnote_table():
    text("본문")
    run("InsertFootnote")
    text("각주 안 표:")
    table(1, 2)
    fill_cells(["x", "y"])
    run("Cancel")
    run("CloseEx")


try:
    for name, build in [
        ("table_basic.hwpx", table_basic),
        ("table_merge.hwpx", table_merge),
        ("table_caption.hwpx", table_caption),
        ("footnotes.hwpx", footnotes),
        ("footnote_in_cell.hwpx", footnote_in_cell),
        ("footnote_table.hwpx", footnote_table),
        ("pictures.hwpx", pictures),
        ("picture_twice.hwpx", picture_twice),
        ("picture_in_cell.hwpx", picture_in_cell),
        ("picture_caption.hwpx", picture_caption),
        ("nested.hwpx", nested),
    ]:
        sample(name, build)
finally:
    hwp.Clear(1)
    hwp.Quit()
