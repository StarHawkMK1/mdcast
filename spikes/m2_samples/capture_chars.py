"""THROWAWAY: let Hangul write character shapes (bold, italic, strike, sup/sub, fonts)."""

import sys
from pathlib import Path

import win32com.client as win32

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.XHwpWindows.Item(0).Visible = True
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")


def text(s):
    pset = hwp.HParameterSet.HInsertText
    hwp.HAction.GetDefault("InsertText", pset.HSet)
    pset.Text = s
    hwp.HAction.Execute("InsertText", pset.HSet)


def toggled(action, label):
    ok = hwp.HAction.Run(action)
    text(label)
    hwp.HAction.Run(action)
    print(f"  {action} -> {ok}")
    text(" ")


def font(face, label):
    pset = hwp.HParameterSet.HCharShape
    hwp.HAction.GetDefault("CharShape", pset.HSet)
    for item in ("FaceNameHangul", "FaceNameLatin", "FaceNameHanja", "FaceNameJapanese", "FaceNameOther", "FaceNameSymbol", "FaceNameUser"):
        pset.HSet.SetItem(item, face)
    for item in ("FontTypeHangul", "FontTypeLatin", "FontTypeHanja", "FontTypeJapanese", "FontTypeOther", "FontTypeSymbol", "FontTypeUser"):
        pset.HSet.SetItem(item, 1)  # TTF
    print(f"  CharShape {face} ->", hwp.HAction.Execute("CharShape", pset.HSet))
    text(label + " ")


try:
    hwp.Clear(1)
    text("보통 ")
    toggled("CharShapeBold", "굵게")
    toggled("CharShapeItalic", "기울임")
    toggled("CharShapeUnderline", "밑줄")
    toggled("CharShapeCenterline", "취소선")
    toggled("CharShapeSuperscript", "위첨자")
    toggled("CharShapeSubscript", "아래첨자")
    font("맑은 고딕", "맑은고딕")
    font("Consolas", "code")
    print("SaveAs ->", hwp.SaveAs(str((OUT / "chars.hwpx").resolve()), "HWPX", ""))
finally:
    hwp.Clear(1)
    hwp.Quit()
