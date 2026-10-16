"""Dev-only: render mdcast outputs to PNG pages under .test-output/pages/ for manual review.

PDF is rendered with pypdfium2. docx is first exported to PDF with Microsoft Word via COM
(Windows only, optional) and then rendered the same way. hwpx is exported to PDF with Hancom
Office via COM the same way.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pypdfium2 as pdfium

OUT = Path(".test-output") / "pages"


class ConverterMissing(RuntimeError):
    pass


def render_pdf(pdf_path: Path, name: str, scale: float = 1.5) -> list[Path]:
    target = OUT / name
    target.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(pdf_path))
    written = []
    for index in range(len(pdf)):
        image = pdf[index].render(scale=scale).to_pil()
        path = target / f"p{index + 1}.png"
        image.save(path)
        written.append(path)
    return written


def docx_to_pdf_with_word(docx_path: Path) -> Path:
    try:
        import win32com.client as win32
    except ImportError as exc:
        raise ConverterMissing(
            "docx 렌더링에는 Windows 와 pywin32, Microsoft Word 가 필요합니다 "
            "(docx rendering needs Windows, pywin32 and Microsoft Word)"
        ) from exc

    out = Path(tempfile.mkdtemp(prefix="mdcast-word-")) / (docx_path.stem + ".pdf")
    try:
        word = win32.gencache.EnsureDispatch("Word.Application")
    except Exception as exc:  # COM errors are pywintypes.com_error, not importable everywhere
        raise ConverterMissing(
            f"Microsoft Word 를 실행할 수 없습니다 (cannot start Microsoft Word): {exc}"
        ) from exc
    try:
        document = word.Documents.Open(str(docx_path.resolve()), ReadOnly=True)
        document.ExportAsFixedFormat(str(out), 17)  # 17 = wdExportFormatPDF
        document.Close(False)
    finally:
        word.Quit()
    return out


def hwpx_to_pdf_with_hangul(hwpx_path: Path) -> Path:
    try:
        import win32com.client as win32
    except ImportError as exc:
        raise ConverterMissing(
            "hwpx 렌더링에는 Windows 와 pywin32, 한글이 필요합니다 "
            "(hwpx rendering needs Windows, pywin32 and Hancom Office)"
        ) from exc

    if not hwpx_path.is_file():  # Hangul would wait on a dialog instead of failing
        raise ConverterMissing(f"파일이 없습니다 (no such file): {hwpx_path}")
    out = Path(tempfile.mkdtemp(prefix="mdcast-hangul-")) / (hwpx_path.stem + ".pdf")
    try:
        hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    except Exception as exc:  # COM errors are pywintypes.com_error, not importable everywhere
        raise ConverterMissing(f"한글을 실행할 수 없습니다 (cannot start Hancom Office): {exc}") from exc
    try:
        hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        if not hwp.Open(str(hwpx_path.resolve()), "HWPX", ""):
            raise ConverterMissing(f"한글이 파일을 열지 못했습니다: {hwpx_path}")
        hwp.SaveAs(str(out), "PDF", "")
    finally:
        hwp.Clear(1)
        hwp.Quit()
    return out


def main(paths: list[str]) -> int:
    status = 0
    for raw in paths:
        path = Path(raw)
        try:
            if path.suffix.lower() == ".pdf":
                pages = render_pdf(path, path.stem + "-pdf")
            elif path.suffix.lower() == ".docx":
                pages = render_pdf(docx_to_pdf_with_word(path), path.stem + "-docx")
            elif path.suffix.lower() == ".hwpx":
                pages = render_pdf(hwpx_to_pdf_with_hangul(path), path.stem + "-hwpx")
            else:
                print("skip", path)
                continue
        except ConverterMissing as exc:
            print(f"skip {path}: {exc}", file=sys.stderr)
            status = 1
            continue
        print(path, "->", ", ".join(str(p) for p in pages))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
