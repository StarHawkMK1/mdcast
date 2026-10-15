"""THROWAWAY spike S1: create a blank .hwpx with Hancom Office via COM."""

import sys
from pathlib import Path

import win32com.client as win32


def main(out: Path) -> None:
    hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    try:
        hwp.XHwpWindows.Item(0).Visible = True
        try:
            hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        except Exception as exc:  # noqa: BLE001 - spike: report and continue
            print("RegisterModule failed (security prompts may appear):", exc)
        ok = hwp.SaveAs(str(out.resolve()), "HWPX", "")
        print("SaveAs ->", ok)
    finally:
        hwp.Clear(1)
        hwp.Quit()


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "seed.hwpx"))
