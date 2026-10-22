from __future__ import annotations

import io
from dataclasses import dataclass, field

import panflute as pf
from click.testing import CliRunner
from pdf_builder import typst_pdf
from PIL import Image

from mdcast.cli import main
from mdcast.pipeline import convert
from mdcast.readers.md import read_md
from mdcast.readers.pdf import images, read_pdf
from mdcast.readers.pdf.body import read_page
from mdcast.readers.pdf.images import image_boxes, is_small
from mdcast.readers.pdf.model import Box
from mdcast.readers.pdf.repeats import skipped_message
from mdcast.report import Codes, Level, Report
from mdcast.types import Format, Source

# a paragraph wrapping over several lines, so the layout is measured on real body text
_BODY = "본문 글은 여러 줄에 걸쳐 이어지는 한 문단입니다. " * 8 + "끝."


def png(width: int = 200, height: int = 120, colour: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, format="PNG")
    return out.getvalue()


def pdf(body: str, *, page: str = 'paper: "a4"', **files: bytes) -> bytes:
    return typst_pdf(body, page=page, files=files or {"a.png": png()})


def pages(*bodies: str) -> str:
    return "\n#pagebreak()\n".join(bodies)


def pdf_source(data: bytes, name: str = "x.pdf") -> Source:
    return Source(data, name, Format.PDF)


def imported(data: bytes):
    return read_pdf(pdf_source(data), Report("x.pdf", Format.PDF), "x_assets")


def events(result, code: str) -> list:
    return [e for e in result.report.events if e.code == code]


def opens(blob: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(blob)) as im:
        im.load()
        return im.size


def test_image_extracted_and_linked():
    data = pdf('첫 문단입니다.\n\n#image("a.png", width: 5cm)\n\n둘째 문단입니다.')
    result = convert(pdf_source(data), [Format.MD])
    out = result.outputs[0]
    md = out.data.decode("utf-8")
    assert "![그림](x_assets/image1.png)" in md
    assert list(out.assets) == ["x_assets/image1.png"]
    width, height = opens(out.assets["x_assets/image1.png"])
    assert abs(width - 5 / 2.54 * images.RESOLUTION) <= 2 and height > 0  # 5 cm at RESOLUTION dpi
    assert md.index("첫 문단") < md.index("![그림]") < md.index("둘째 문단")
    doc = imported(data).doc
    assert [type(b) for b in doc.content] == [pf.Para, pf.Para, pf.Para]
    [img] = doc.content[1].content
    assert isinstance(img, pf.Image) and img.url == "x_assets/image1.png"
    assert pf.stringify(img) == "그림"
    assert result.report.coverage == 1.0


def test_image_breaks_a_paragraph():
    """Lines either side of a picture would join as one paragraph without it."""
    data = pdf('위 글\n#image("a.png", width: 3cm)\n아래 글')
    doc = imported(data).doc
    assert [pf.stringify(b).strip() for b in doc.content] == ["위 글", "그림", "아래 글"]


def test_small_image_dropped():
    data = pdf(f'{_BODY}\n\n#image("a.png", width: 0.5cm)\n\n#image("a.png", width: 0.5cm)')
    result = convert(pdf_source(data), [Format.MD])
    out = result.outputs[0]
    assert out.assets == {} and "![" not in out.data.decode("utf-8")
    [event] = events(result, Codes.IMPORT_OBJECT_SKIPPED)
    assert event.level is Level.INFO
    assert event.message == "장식으로 보이는 작은 그림 2개를 가져오지 않습니다"


def test_image_in_cell():
    data = pdf('#table(columns: 2, [머리], [둘], [#image("a.png", width: 2cm)], [글\n\n#image("a.png", width: 2cm)])')
    doc = imported(data).doc
    [table] = [b for b in doc.content if isinstance(b, pf.Table)]
    only, mixed = table.content[0].content[0].content
    [plain] = only.content
    assert isinstance(plain, pf.Plain) and isinstance(plain.content[0], pf.Image)
    assert [type(b) for b in mixed.content] == [pf.Para, pf.Para]
    assert pf.stringify(mixed.content[0]).strip() == "글"
    assert isinstance(mixed.content[1].content[0], pf.Image)
    assert not [b for b in doc.content if not isinstance(b, pf.Table)]  # nothing leaks into the body

    md = convert(pdf_source(data), [Format.MD]).outputs[0].data
    [back] = [b for b in read_md(Source(md, "x.md", Format.MD), Report("x.md", Format.MD)).doc.content
              if isinstance(b, pf.Table)]
    only, mixed = back.content[0].content[0].content
    assert [type(b) for b in only.content] == [pf.Plain] and [type(b) for b in mixed.content] == [pf.Para, pf.Para]


def test_pictures_only_pdf():
    """Review Focus 1: pages holding nothing but a page-sized picture give an MD of pictures alone;
    the same picture on every page is never a running header."""
    page = 'paper: "a4", margin: 0pt'
    data = pdf(pages(*['#image("a.png", width: 100%, height: 100%)'] * 4), page=page)
    result = convert(pdf_source(data), [Format.MD])
    out = result.outputs[0]
    assert out.data is not None
    assert not [e for e in result.report.events if e.level is Level.ERROR]
    assert list(out.assets) == ["x_assets/image1.png"]
    assert out.data.decode("utf-8").count("![그림](x_assets/image1.png)") == 4
    assert not events(result, Codes.IMPORT_HEADER_SKIPPED)


def test_image_in_table_outline_but_no_cell_is_body():
    @dataclass
    class FakeTable:
        bbox: tuple[float, float, float, float]
        cells: list[tuple[float, float, float, float]]

    @dataclass
    class FakePage:
        tables: list[FakeTable]
        images: list[dict]
        chars: list[dict] = field(default_factory=list)
        height: float = 842.0
        bbox: tuple[float, float, float, float] = (0, 0, 595, 842)
        curves: tuple[dict, ...] = ()
        edges: tuple[dict, ...] = ()  # no ruling lines: no side is closed

        def find_tables(self) -> list[FakeTable]:
            return self.tables

    # an L-shaped table: its outline is 0..100 × 0..40 but no cell covers 50..100 × 20..40
    cells = [(0, 0, 50, 20), (50, 0, 100, 20), (0, 20, 50, 40)]
    pictures = [{"x0": 10, "top": 2, "x1": 40, "bottom": 18}, {"x0": 60, "top": 22, "x1": 90, "bottom": 38}]
    page = read_page(0, FakePage([FakeTable((0, 0, 100, 40), cells)], pictures))
    assert [p.box for p in page.pictures] == [Box(60, 22, 90, 38)]
    assert [p.box for ps in page.cell_pictures.values() for p in ps] == [Box(10, 2, 40, 18)]


def test_repeated_logo_removed():
    logo = 'header: image("a.png", height: 1cm)'
    data = pdf(pages("본문 하나", "본문 둘", "본문 셋", "본문 넷"), page=f'paper: "a4", {logo}')
    result = convert(pdf_source(data), [Format.MD])
    out = result.outputs[0]
    md = out.data.decode("utf-8")
    assert out.assets == {} and "![" not in md and "본문 넷" in md
    [event] = events(result, Codes.IMPORT_HEADER_SKIPPED)
    assert event.level is Level.INFO
    assert event.message == "쪽마다 반복되는 머리말·꼬리말 그림 4개를 가져오지 않습니다"
    assert result.report.coverage == 1.0


def test_repeated_logo_and_header_line_in_one_message():
    header = 'header: [#box(image("a.png", height: 0.8cm)) #h(1fr) 보고서 머리말]'
    data = pdf(pages("본문 하나", "본문 둘", "본문 셋", "본문 넷"), page=f'paper: "a4", {header}')
    result = convert(pdf_source(data), [Format.MD])
    assert result.outputs[0].assets == {}
    [event] = events(result, Codes.IMPORT_HEADER_SKIPPED)
    assert event.message == "쪽마다 반복되는 머리말·꼬리말 4줄과 그림 4개를 가져오지 않습니다 (예: '보고서 머리말')"


def test_logo_on_two_pages_kept():
    logo = 'header: image("a.png", height: 1cm)'
    data = pdf(pages("본문 하나", "본문 둘"), page=f'paper: "a4", {logo}')
    result = convert(pdf_source(data), [Format.MD])
    assert list(result.outputs[0].assets) == ["x_assets/image1.png"]  # the same picture twice is one file
    assert result.outputs[0].data.decode("utf-8").count("![그림](x_assets/image1.png)") == 2
    assert not events(result, Codes.IMPORT_HEADER_SKIPPED)


def test_logo_beside_page_number_does_not_count_with_it():
    """A picture keys as text "" like a bare page number; the two are told apart all the same."""
    footer = 'footer: align(center)[#context counter(page).display()]'
    # a strip centred over the number, in the bottom band but over a line and a half above it
    first = '#place(bottom + center)[#image("a.png", width: 1cm)]\n본문 하나'
    data = pdf(pages(first, "본문 둘", "본문 셋", "본문 넷"), page=f'paper: "a4", {footer}', **{"a.png": png(400, 100)})
    result = convert(pdf_source(data), [Format.MD])
    assert list(result.outputs[0].assets) == ["x_assets/image1.png"]
    [event] = events(result, Codes.IMPORT_HEADER_SKIPPED)
    assert "4줄" in event.message and "그림" not in event.message


def test_same_picture_twice_is_one_file_and_different_ones_two():
    files = {"a.png": png(), "b.png": png(colour=(30, 30, 200))}
    body = '#image("a.png", width: 4cm)\n\n#image("b.png", width: 4cm)\n\n#image("a.png", width: 4cm)'
    doc = imported(typst_pdf(body, files=files))
    urls = [b.content[0].url for b in doc.doc.content]
    assert urls == ["x_assets/image1.png", "x_assets/image2.png", "x_assets/image1.png"]
    assert list(doc.media) == ["image1.png", "image2.png"]


def test_image_past_page_edge():
    """Review Focus 3: a picture running off the page is clipped to the page before it is drawn."""
    data = pdf('#place(dx: -4cm)[#image("a.png", width: 5cm)]\n\n글')
    result = convert(pdf_source(data), [Format.MD])
    out = result.outputs[0]
    assert list(out.assets) == ["x_assets/image1.png"]
    width, _ = opens(out.assets["x_assets/image1.png"])
    # from 2.5 cm (the margin) − 4 cm to 3.5 cm: only the 3.5 cm on the page is drawn
    assert abs(width - 3.5 / 2.54 * images.RESOLUTION) <= 2
    assert not events(result, Codes.IMPORT_OBJECT_SKIPPED)
    assert not [e for e in result.report.events if e.level is Level.ERROR]


def test_image_boxes_clip_to_the_page_and_drop_empty_ones():
    @dataclass
    class FakePage:
        images: list[dict]
        bbox: tuple[float, float, float, float] = (0, 0, 600, 800)

    found = image_boxes(FakePage([
        {"x0": -40, "top": 700, "x1": 100, "bottom": 900},  # off the left and the bottom
        {"x0": 610, "top": 10, "x1": 700, "bottom": 50},  # wholly off the page
        {"x0": 100, "top": 100, "x1": 100, "bottom": 200},  # no width
    ]))
    assert found == [Box(0, 700, 100, 800)]


def test_is_small_needs_both_sides_short():
    assert is_small(Box(0, 0, 19, 19))
    assert not is_small(Box(0, 0, 19, 40))  # a thin rule as long as a line is not decoration
    assert not is_small(Box(0, 0, 20, 10))


def test_picture_that_cannot_be_drawn_is_reported(monkeypatch):
    def fail(page, box):
        raise RuntimeError("cannot draw")

    monkeypatch.setattr("mdcast.readers.pdf.body.render", fail)
    data = pdf(pages("첫 쪽", '둘째 쪽\n\n#image("a.png", width: 5cm)'))
    result = convert(pdf_source(data), [Format.MD])
    out = result.outputs[0]
    assert out.data is not None and out.assets == {} and "둘째 쪽" in out.data.decode("utf-8")
    [event] = events(result, Codes.IMPORT_OBJECT_SKIPPED)
    assert event.level is Level.WARN and event.where == {"page": 2}


def test_skipped_message_counts_pictures():
    assert skipped_message(4, ["- 1 -"]) == "쪽마다 반복되는 머리말·꼬리말 4줄을 가져오지 않습니다 (예: '- 1 -')"
    assert skipped_message(0, [], 3) == "쪽마다 반복되는 머리말·꼬리말 그림 3개를 가져오지 않습니다"
    assert skipped_message(2, ["a"], 1) == "쪽마다 반복되는 머리말·꼬리말 2줄과 그림 1개를 가져오지 않습니다 (예: 'a')"


def test_spaced_hangul_file_name(tmp_path, monkeypatch):
    """Review Focus 4: `보고서 최종.pdf` → CLI; the links into `보고서 최종_assets/` are found again."""
    data = pdf(f'{_BODY}\n\n#image("a.png", width: 5cm)\n\n#table(columns: 2, [머리], [둘], '
               f'[#image("b.png", width: 2cm)], [글])', **{"a.png": png(), "b.png": png(colour=(0, 120, 0))})
    monkeypatch.chdir(tmp_path)
    (tmp_path / "보고서 최종.pdf").write_bytes(data)
    r = CliRunner().invoke(main, ["convert", str(tmp_path / "보고서 최종.pdf")])
    assert r.exit_code == 0, r.output
    assert sorted(f.name for f in (tmp_path / "보고서 최종_assets").iterdir()) == ["image1.png", "image2.png"]
    md = (tmp_path / "보고서 최종.md").read_bytes()

    back = read_md(Source(md, "보고서 최종.md", Format.MD, base_dir=tmp_path), Report("보고서 최종.md", Format.MD)).doc
    urls: list[str] = []
    back.walk(lambda e, _d: urls.append(e.url) if isinstance(e, pf.Image) else None)
    assert urls == ["보고서 최종_assets/image1.png", "보고서 최종_assets/image2.png"]
    assert all((tmp_path / url).is_file() for url in urls)

    exported = convert(Source(md, "보고서 최종.md", Format.MD, base_dir=tmp_path), [Format.DOCX])
    assert exported.outputs[0].data is not None
    assert not [e for e in exported.report.events if e.code == Codes.IMAGE_FETCH_FAILED]
