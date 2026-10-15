"""Dev-only: render mdcast outputs to PNG pages under .test-output/pages/ for manual review.

PDF is rendered with pypdfium2. docx is first exported to PDF with Microsoft Word via COM
(Windows only, optional) and then rendered the same way.
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


def main(paths: list[str]) -> int:
    status = 0
    for raw in paths:
        path = Path(raw)
        try:
            if path.suffix.lower() == ".pdf":
                pages = render_pdf(path, path.stem + "-pdf")
            elif path.suffix.lower() == ".docx":
                pages = render_pdf(docx_to_pdf_with_word(path), path.stem + "-docx")
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
