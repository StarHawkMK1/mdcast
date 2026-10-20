"""THROWAWAY: open each variant in Hangul, dump text, save PDF and a round-trip hwpx."""

import sys
from pathlib import Path

import win32com.client as win32

DIR = Path(sys.argv[1])
names = sys.argv[2:]

hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.XHwpWindows.Item(0).Visible = True
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
try:
    for name in names:
        src = (DIR / name).resolve()
        ok = hwp.Open(str(src), "HWPX", "")
        print(f"== {name}: Open -> {ok}, pages -> {hwp.PageCount}")
        if not ok:
            continue
        print("  text:", repr(hwp.GetTextFile("UNICODE", "")[:200]))
        print("  pdf:", hwp.SaveAs(str(src.with_suffix(".pdf")), "PDF", ""))
        print("  rt:", hwp.SaveAs(str(src.with_name(src.stem + ".rt.hwpx")), "HWPX", ""))
        hwp.Clear(1)
finally:
    hwp.Clear(1)
    hwp.Quit()
