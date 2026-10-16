"""THROWAWAY: let Hangul write sample hwpx files for M2a (spec 2026-10-16 section 3)."""

import sys
import traceback
from pathlib import Path

import win32com.client as win32

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.XHwpWindows.Item(0).Visible = True
try:
    print("RegisterModule ->", hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule"))
except Exception as exc:  # noqa: BLE001
    print("RegisterModule failed:", exc)


def text(s):
    pset = hwp.HParameterSet.HInsertText
    hwp.HAction.GetDefault("InsertText", pset.HSet)
    pset.Text = s
    return hwp.HAction.Execute("InsertText", pset.HSet)


def run(name):
    ok = hwp.HAction.Run(name)
    print(f"  Run({name}) -> {ok}")
    return ok


def save(name):
    ok = hwp.SaveAs(str((OUT / name).resolve()), "HWPX", "")
    print(f"SaveAs {name} -> {ok}")


def header_footer(kind):
    pset = hwp.HParameterSet.HHeaderFooter
    hwp.HAction.GetDefault("HeaderFooter", pset.HSet)
    pset.HSet.SetItem("Type", kind)
    ok = hwp.HAction.Execute("HeaderFooter", pset.HSet)
    print(f"  HeaderFooter({kind}) -> {ok}")
    return ok


def sample(name, build):
    print(f"== {name}")
    hwp.Clear(1)
    try:
        build()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    save(name)


def pagebreak():
    text("가")
    run("BreakPage")
    text("나")


def linebreak():
    text("가")
    run("BreakLine")
    text("나")


def headers():
    if header_footer(0):
        text("왼쪽")
        text("\t")
        text("쪽 ")
        run("InsertCpNo")
        text(" / ")
        run("InsertTpNo")
        run("CloseEx")
    if header_footer(1):
        text("꼬리말 ")
        run("InsertCpTpNo")
        run("CloseEx")
    text("본문")
    run("BreakPage")
    text("둘째 쪽")


def hyperlink():
    text("앞 ")
    pset = hwp.HParameterSet.HHyperLink
    hwp.HAction.GetDefault("InsertHyperlink", pset.HSet)
    pset.HSet.SetItem("Text", "링크글")
    pset.HSet.SetItem("Command", "https://example.com/a?b=1;1;0;0;")
    print("  InsertHyperlink ->", hwp.HAction.Execute("InsertHyperlink", pset.HSet))
    text(" 뒤")


def outline():
    hwp.HAction.Run("StyleShortcut2")  # 개요 1 (Ctrl+2)
    text("제목 하나")
    run("BreakPara")
    text("본문")


try:
    sample("pagebreak.hwpx", pagebreak)
    sample("linebreak.hwpx", linebreak)
    sample("headers.hwpx", headers)
    sample("hyperlink.hwpx", hyperlink)
    sample("outline.hwpx", outline)
finally:
    hwp.Clear(1)
    hwp.Quit()
