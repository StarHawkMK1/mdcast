"""THROWAWAY spike S1: open a hwpx in Hancom Office via COM and dump its text."""

import sys
from pathlib import Path

import win32com.client as win32


def main(path: Path) -> int:
    hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    try:
        hwp.XHwpWindows.Item(0).Visible = True
        try:
            hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        except Exception as exc:  # noqa: BLE001
            print("RegisterModule failed:", exc)
        ok = hwp.Open(str(path.resolve()), "HWPX", "")
        print("Open ->", ok)
        print("--- text ---")
        print(hwp.GetTextFile("TEXT", ""))
        return 0 if ok else 1
    finally:
        hwp.Clear(1)
        hwp.Quit()


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
