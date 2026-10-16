"""Dev-only: write the built-in hwpx container (Hangul's blank document) without personal metadata.

    uv run python scripts/make_reference_hwpx.py                 # Hangul via COM (Windows + Hangul)
    uv run python scripts/make_reference_hwpx.py --from x.hwpx   # a blank document Hangul saved
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mdcast.hwpx.container import Package  # noqa: E402

TARGET = ROOT / "src/mdcast/builtin_templates/default/reference.hwpx"
OPF = "{http://www.idpf.org/2007/opf/}"
HA = "{http://www.hancom.co.kr/hwpml/2011/app}"
CLEARED = ("creator", "subject", "description", "CreatedDate", "ModifiedDate", "date", "keyword")


def normalize(data: bytes) -> bytes:
    """Clear the author, dates and preview text Hangul writes into a saved document (public repo)."""
    package = Package.read(data)
    content = package.xml("Contents/content.hpf")
    title = content.find(f"{OPF}metadata/{OPF}title")
    if title is not None:
        title.text = None
    for meta in content.iter(f"{OPF}meta"):
        if meta.get("name") in CLEARED:
            meta.text = None
    package.set_xml("Contents/content.hpf", content)
    if "Preview/PrvText.txt" in package.names():
        package.set("Preview/PrvText.txt", b"")
    if "settings.xml" in package.names():
        app = package.xml("settings.xml")
        for caret in app.iter(f"{HA}CaretPosition"):
            caret.set("listIDRef", "0")
            caret.set("paraIDRef", "0")
            caret.set("pos", "0")
        package.set_xml("settings.xml", app)
    return package.write()


def save_blank_with_hangul() -> bytes:
    import win32com.client as win32

    out = Path(tempfile.mkdtemp(prefix="mdcast-hwpx-")) / "blank.hwpx"
    hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    try:
        hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        if not hwp.SaveAs(str(out), "HWPX", ""):
            raise RuntimeError("한글이 빈 문서를 저장하지 못했습니다")
    finally:
        hwp.Clear(1)
        hwp.Quit()
    return out.read_bytes()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="내장 reference.hwpx 만들기")
    parser.add_argument("--from", dest="source", type=Path, help="한글이 저장한 빈 hwpx")
    args = parser.parse_args(argv)
    data = args.source.read_bytes() if args.source else save_blank_with_hangul()
    TARGET.write_bytes(normalize(data))
    print(TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
