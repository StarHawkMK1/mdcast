# M2b hwpx 표·이미지·각주 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** hwpx 출력에서 표(병합·테두리·머리행 반복·표 종류·캡션), 이미지(인라인·그림·크기·칸 안), 각주를 한글 고유 개체로 만든다.

**Architecture:** M2a 의 `src/mdcast/hwpx/` 독립 패키지를 넓힌다. 표 격자·폭은 `hwpx/table.py`, 그림 등록·크기는 `hwpx/picture.py`, XML 조립과 칸·각주·캡션 안 블록은 기존 `SectionWriter` 가 재귀로 만든다. 이미지를 읽고(WebP→PNG 포함) 템플릿 `tables`·`figures` 설정을 값 객체로 바꾸는 일은 어댑터 `writers/hwpx.py` 가 한다. XML 모양은 모두 스펙 부록 B 의 견본에서 가져온다.

**Tech Stack:** Python 3.11+, lxml, panflute 2.3.1 (pandoc AST), typst 0.15 (WebP→PNG), pytest. 한글 2020 COM (pywin32, `--run-hangul` 테스트만).

**Spec:** `docs/superpowers/specs/2026-10-20-mdcast-m2b-hwpx-design.md` (이하 "스펙"). 앞 단계 `docs/superpowers/specs/2026-10-16-mdcast-m2a-hwpx-design.md` ("M2a 스펙"). 구현자는 두 문서와 이 계획을 함께 읽는다. XML 조각의 정확한 속성은 스펙 부록 B 를 그대로 따른다.

## Global Constraints

- `src/mdcast/hwpx/` 는 mdcast 의 다른 모듈을 import 하지 않고 파일 입출력도 하지 않는다 (M2a §4). 이미지 읽기·변환·템플릿 해석은 `src/mdcast/writers/` 쪽.
- 거부 금지: 어떤 표·이미지·각주도 변환을 실패시키지 않는다. 못 만드는 것은 낮춰 쓰고 알린다 (스펙 §1 반목표).
- 견본(스펙 부록 B)에 없는 XML 을 추측해 쓰지 않는다. 부록 B 의 요소 순서·속성 이름·값을 그대로 쓴다.
- 길이 단위: 표·그림·여백은 HWPUNIT (`hwpx/units.py` 의 `hwpunit(mm)`), 문단 여백은 `para_unit` (M2a 그대로).
- 테두리 굵기 문자열은 이 16개만: `0.1 mm`, `0.12 mm`, `0.15 mm`, `0.2 mm`, `0.25 mm`, `0.3 mm`, `0.4 mm`, `0.5 mm`, `0.6 mm`, `0.7 mm`, `1.0 mm`, `1.5 mm`, `2.0 mm`, `3.0 mm`, `4.0 mm`, `5.0 mm` (부록 B-4).
- 그림 media-type: `image/png`, `image/jpg`, `image/gif`, `image/bmp`, `image/svg` (부록 B-9). WebP 는 PNG 로 바꿔 넣는다.
- 알림 문구는 한국어, 종류마다 문서당 한 번 (`Notices.add`). 이미지 실패는 docx·pdf 와 같은 `IMAGE_FETCH_FAILED`.
- 테스트 실행: `uv run python -m pytest -q` (전체), 한글 테스트는 `--run-hangul` 추가. 린트: `uv run ruff check src tests`.
- 커밋 메시지 끝에 저장소 규칙의 Co-Authored-By / Claude-Session 줄을 붙인다.

## Review Focus

1. **목록·인용 안의 표와 그림** — 들여쓴 만큼 쓸 수 있는 폭이 줄어야 한다. 줄지 않으면 표 오른쪽이 본문 밖으로 나간다. → Task 6 `test_table_in_list_item_is_narrower`, Task 7 `test_picture_in_quote_fits_the_indented_width`.
2. **열이 아주 많은 auto 표 (예: 12열)** — 열 최소폭 10mm × 12 가 본문 폭 170mm 를 넘어도 표 폭이 쓸 수 있는 폭을 넘지 않아야 한다. → Task 5 `test_auto_widths_never_exceed_available_even_with_minimums`.
3. **사용자 reference.hwpx 에 그림이 이미 있을 때** (`BinData/image1.png`, manifest id `image1`) — mdcast 그림이 그 이름·id 와 겹치면 그릇의 그림이 바뀐다. → Task 7 `test_pictures_do_not_clash_with_container_bindata`.
4. **같은 그림을 여러 번** (로고를 칸마다) — BinData 하나를 함께 써야 문서가 불어나지 않는다. → Task 7 `test_same_image_shares_one_bindata`.
5. **칸 안 각주와 각주 안 각주가 한 문서에** — 칸 안 각주는 한글 각주, 각주 안 각주만 `[주 n]` 으로 낮춰야 하고 번호가 섞이지 않아야 한다. → Task 8 `test_note_in_note_falls_back_with_its_own_numbers`.

---

## File Structure

| 파일 | 할 일 |
|---|---|
| `src/mdcast/filters/tables.py` (수정) | hwpx 대상일 때 표에 `mdcast-variant` 속성. 첫 열 굵게를 격자 0열 기준으로 |
| `src/mdcast/hwpx/look.py` (수정) | `Border`, `TableLook`, `Image` 값 객체와 `Settings` 의 새 필드 |
| `src/mdcast/hwpx/header.py` (수정) | `line_width()`, `Header.add_cell_border_fill()` |
| `src/mdcast/hwpx/table.py` (새) | 격자(span·가려진 자리·빈 칸), 열 너비, 칸별 테두리·배경 결정. XML 없음 |
| `src/mdcast/hwpx/picture.py` (새) | 그림 크기 계산, BinData·manifest 등록(`Pictures`), `hp:pic` 요소 |
| `src/mdcast/hwpx/section.py` (수정) | 표·그림·각주·캡션 XML, 칸·각주·캡션 안 블록 재귀, 쓸 수 있는 폭 추적 |
| `src/mdcast/hwpx/writer.py` (수정) | 본문 폭을 먼저 확정, `Pictures`·각주 번호 모양을 SectionWriter 에 넘김 |
| `src/mdcast/writers/images.py` (수정) | BMP 판별, `image_info()`, `webp_to_png()` |
| `src/mdcast/writers/hwpx.py` (수정) | 표 모양·그림 설정 변환, hwpx 용 이미지 읽기 |
| `tests/fixtures/md/tables-images.md`, `tests/fixtures/md/assets/wide.png`, `tests/fixtures/templates/submission/template.yaml` (새) | 스펙 §8.4 픽스처 |
| `tests/test_hwpx_table.py`, `tests/test_hwpx_picture.py`, `tests/test_hwpx_notes.py` (새) | 단위 테스트 |
| `tests/test_hwpx_degraded.py` (수정) | 표·이미지·각주 항목 삭제, 수식만 남김 |
| `tests/helpers.py`, `tests/test_hangul.py`, `tests/test_no_reject.py`, `tests/test_writer_hwpx.py`, `tests/test_images.py`, `tests/test_filter_tables.py`, `tests/test_hwpx_header.py` (수정) | 아래 Task 별 |
| `README.md` (수정) | 스펙 §9 의 README 항목 |

---

### Task 1: 표 필터 — hwpx 표 종류 속성과 격자 기준 첫 열

**Files:**
- Modify: `src/mdcast/filters/tables.py` (`_style`, `apply`)
- Test: `tests/test_filter_tables.py`

**Interfaces:**
- Produces: hwpx 대상에서 표 종류가 정해진 최상위 표의 `pf.Table.attributes["mdcast-variant"] == <이름>`. 다른 대상(docx·pdf)에는 붙이지 않는다.
- Produces: `first_column_cells(rows: list[pf.TableRow]) -> list[pf.TableCell]` (같은 파일): 앞 행의 rowspan 을 고려해 격자 0열에서 **시작하는** 칸만 돌려준다.

- [ ] **Step 1: Write the failing tests**

```python
def test_hwpx_tables_carry_their_variant():
    doc, _ = run(TWO_TABLES, target=Format.HWPX, overrides=VARIANTS)
    first, second = doc.content
    assert first.attributes["mdcast-variant"] == "plain"
    assert "mdcast-variant" not in second.attributes


def test_docx_tables_get_no_variant_attribute():
    doc, _ = run(TWO_TABLES, overrides=VARIANTS)
    assert all("mdcast-variant" not in t.attributes for t in doc.content)


ROWSPAN = (
    "+----+----+\n| 가 | 1  |\n+    +----+\n|    | 2  |\n+----+----+\n| 나 | 3  |\n+----+----+\n"
)


def test_first_column_bold_follows_the_grid_under_a_rowspan():
    doc, _ = run(ROWSPAN, overrides={"tables": {"first_column": {"bold": True}}})
    rows = [row for body in doc.content[0].content for row in body.content]
    texts = [[pf.stringify(c) for c in row.content] for row in rows]
    bold = [[isinstance(c.content[0].content[0], pf.Strong) for c in row.content] for row in rows]
    assert texts == [["가", "1"], ["2"], ["나", "3"]]
    assert bold == [[True, False], [False], [True, False]]
```

(ROWSPAN 은 헤더 없는 grid table 이다. pandoc 이 읽은 행 구조가 위 `texts` 와 다르면 표를 고쳐 같은 구조(두 번째 행이 0열을 덮인 상태)를 만든다.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_filter_tables.py -q`
Expected: 새 3개 FAIL (`KeyError: 'mdcast-variant'`, 두 번째 행 `2` 가 굵게 됨)

- [ ] **Step 3: Implement**

`apply()` 의 표 처리에서 `ctx.target is Format.HWPX and variant` 이면 `block.attributes["mdcast-variant"] = variant`. `_style()` 의 첫 열 굵게는 `for body in table.content: for cell in first_column_cells(list(body.content)): _embolden(cell)` 로 바꾼다. `first_column_cells` 는 열마다 "아직 덮인 남은 행 수" 배열로 격자를 따라가며, 행의 첫 칸이 0열에 놓이는 경우에만 그 칸을 넣는다.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_filter_tables.py tests/test_docx_tables.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mdcast/filters/tables.py tests/test_filter_tables.py
git commit -m "feat(tables): hwpx tables carry their variant; first column follows the grid"
```

---

### Task 2: 값 객체와 어댑터의 표·그림 설정

**Files:**
- Modify: `src/mdcast/hwpx/look.py`, `src/mdcast/hwpx/__init__.py` (`Border`, `TableLook`, `Image` 내보내기)
- Modify: `src/mdcast/writers/hwpx.py` (`_settings`)
- Test: `tests/test_writer_hwpx.py`

**Interfaces:**
- Produces (`hwpx/look.py`):

```python
@dataclass(frozen=True)
class Border:
    width: float = 0.5  # pt
    color: str = "#000000"


@dataclass(frozen=True)
class TableLook:
    width: str = "full"  # full | auto
    font_size: float | None = None  # pt; None: the body size
    line_height: float | None = None  # ratio
    padding: float = 1.5  # mm, every side of every cell
    border: Border = Border(0.5)
    border_outer: Border = Border(1.0)
    header_background: str | None = None
    header_valign: str = "middle"  # top | middle | bottom
    header_repeat: bool = True
    body_valign: str = "middle"
    zebra: str | None = None
    first_column_background: str | None = None


@dataclass(frozen=True)
class Image:
    data: bytes
    ext: str  # png | jpg | gif | bmp | svg
    width_px: int
    height_px: int
    dpi: float = 96.0
```

  `Settings` 에 더한다: `tables: dict[str | None, TableLook]` (기본 `{None: TableLook()}`), `images: dict[str, Image]` (기본 빈 dict), `figure_max_ratio: float | None = 1.0`, `figure_max_mm: float | None = None`, `figure_align: str = "center"`.
- Produces (`writers/hwpx.py`): `_table_look(values: dict) -> hwpx.TableLook` — `filters.tables.table_settings(config, variant)` 결과 하나를 바꾼다. 키: `width`, `font_size`(parse_pt), `line_height`(parse_ratio), `cell_padding`(parse_length_mm), `border.width`(parse_pt)·`border.color`, `border_outer.*`, `header.background`·`header.valign`·`header.repeat`, `body.valign`·`body.zebra`, `first_column.background`. 색은 `_color()`.
- `_settings()` 는 **사용자 그릇이어도 전체 config** 로 `tables` 를 채운다 (스펙 §4.4): 키 `None` + `config["tables"]["variants"]` 의 이름마다. `figures.max_width` 가 `%` 로 끝나면 `figure_max_ratio = parse_ratio(v)`, `figure_max_mm = None`; 아니면 `figure_max_ratio = None`, `figure_max_mm = parse_length_mm(v)`. `figure_align = figures.align`.

- [ ] **Step 1: Write the failing tests**

```python
def test_table_looks_come_from_the_full_config(tmp_path):
    doc, ctx = build(tmp_path, "| a |\n|---|\n| 1 |\n", Format.HWPX)
    settings = _settings(ctx, custom=False)
    look = settings.tables[None]
    assert look == hwpx.TableLook(width="full", font_size=10.0, line_height=1.3, padding=1.5,
                                  border=hwpx.Border(0.5, "#000000"), border_outer=hwpx.Border(1.0, "#000000"),
                                  header_background="#F2F2F2", header_valign="middle", header_repeat=True,
                                  body_valign="middle", zebra=None, first_column_background=None)
    assert settings.figure_max_ratio == 1.0 and settings.figure_max_mm is None
    assert settings.figure_align == "center"


def test_custom_container_still_gets_variant_table_looks(tmp_path):
    template = write_template(tmp_path, "t", """
        name: t
        tables: {variants: {제출양식: {border: {width: 0.34pt}, border_outer: {width: 0.34pt}, header: {background: "#E5E5E5"}}}}
        figures: {max_width: 120mm}
    """, {"reference.hwpx": builtin_hwpx()})
    doc, ctx = build(tmp_path, "본문\n", Format.HWPX, template=str(template))
    settings = _settings(ctx, custom=True)
    assert settings.tables["제출양식"].border == hwpx.Border(0.34, "#000000")
    assert settings.tables["제출양식"].header_background == "#E5E5E5"
    assert settings.tables[None].border_outer == hwpx.Border(1.0, "#000000")
    assert settings.figure_max_ratio is None and settings.figure_max_mm == 120.0
```

(`_settings` 는 `from mdcast.writers.hwpx import _settings` 로 가져온다. `build(..., template=...)` 가 경로를 받는 방식은 `tests/helpers.py` 의 기존 사용처를 따른다.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_writer_hwpx.py -q -k "table_looks or variant_table"`
Expected: FAIL (`AttributeError: ... TableLook` 또는 `tables`)

- [ ] **Step 3: Implement** the dataclasses, the `Settings` fields, `_table_look`, and the `_settings` additions above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_writer_hwpx.py -q`
Expected: PASS (기존 테스트 포함)

- [ ] **Step 5: Commit**

```bash
git add src/mdcast/hwpx/look.py src/mdcast/hwpx/__init__.py src/mdcast/writers/hwpx.py tests/test_writer_hwpx.py
git commit -m "feat(hwpx): table looks and figure limits as writer settings"
```

---

### Task 3: 이미지 형식·크기 읽기와 WebP→PNG

**Files:**
- Modify: `src/mdcast/writers/images.py`
- Modify: `src/mdcast/writers/hwpx.py` (`_load_images`, `_write` 에서 호출)
- Test: `tests/test_images.py`, `tests/test_writer_hwpx.py`

**Interfaces:**
- Produces (`writers/images.py`):
  - `_extension()` 가 BMP(`b"BM"` 시작)를 `.bmp` 로 판별한다. strict(PDF)에서는 지금처럼 거부되고 오류 문구는 그대로다 ("PNG, JPEG, GIF, WebP, SVG 만 지원").
  - `image_info(data: bytes) -> tuple[str, int, int, float]`: (형식 `png|jpg|gif|bmp|webp|svg`, 폭 px, 높이 px, dpi). 읽지 못하면 `ValueError`. PNG: `IHDR`, `pHYs`(단위 1=미터면 dpi = ppm × 0.0254, 반올림). JPEG: SOF0–SOF15(C4·C8·CC 제외) 의 높이·폭, JFIF APP0 밀도(단위 1=dpi, 2=dpcm×2.54). GIF: 논리 화면 크기. BMP: DIB 헤더 폭·높이(높이 음수면 절댓값), 가로 해상도(ppm). WebP: `VP8X`(24비트 w−1, h−1), `VP8L`(14비트), `VP8 `(키프레임 폭·높이 14비트). SVG: 루트 `width`·`height` (단위 없음·px=1, pt=96/72, mm=96/25.4, cm=96/2.54, in=96; `%` 는 없는 것으로 봄), 없으면 `viewBox` 셋째·넷째 값, 그것도 없으면 300×150. dpi 정보가 없거나 0 이면 96.0.
  - `webp_to_png(data: bytes, width_px: int, work_dir: Path) -> bytes`: `work_dir/webp/<n>.webp` 로 쓰고 `#set page(width: auto, height: auto, margin: 0pt)\n#image("<n>.webp", width: <width_px × 0.75>pt)` 를 `typst.compile(..., root=<그 폴더>, format="png", ppi=96.0, ignore_system_fonts=True)`. 결과 PNG 의 픽셀 크기가 원본과 같다 (계획 작성 중 400×200 으로 확인).
- Produces (`writers/hwpx.py`): `_load_images(doc: pf.Doc, ctx: WriterContext) -> tuple[pf.Doc, dict[str, hwpx.Image]]`. `localize_images(doc, ctx, check=check)` 를 쓰고, `check(path)` 가 파일을 읽어 `image_info` → WebP 면 `webp_to_png` 결과로 **파일을 덮어쓴다** → 형식이 `png|jpg|gif|bmp|svg` 가 아니면 이유 문자열(`"한글이 넣을 수 없는 이미지 형식입니다: <형식>"`), `ValueError`·`typst.TypstError` 면 `"크기를 읽을 수 없는 이미지입니다"`. 그 뒤 문서의 모든 `pf.Image` 의 `url`(`assets/imgN.ext`)에 대해 파일을 다시 읽어 `hwpx.Image` 를 만든다. 반환 dict 의 키는 그 `url`. `_write()` 는 `hwpx.write` 앞에서 이것을 호출해 `settings.images` 에 넣는다.

- [ ] **Step 1: Write the failing tests** (`tests/test_images.py`)

```python
def test_image_info_reads_sizes_and_dpi(tmp_path):
    from PIL import Image as PILImage
    cases = {}
    for name, kwargs in {"a.png": {"dpi": (300, 300)}, "b.png": {}, "c.jpg": {"dpi": (72, 72)},
                         "d.gif": {}, "e.bmp": {}, "f.webp": {}}.items():
        path = tmp_path / name
        PILImage.new("RGB", (40, 20), (1, 2, 3)).save(path, **kwargs)
        cases[name] = image_info(path.read_bytes())
    assert cases["a.png"] == ("png", 40, 20, 300.0)
    assert cases["b.png"] == ("png", 40, 20, 96.0)
    assert cases["c.jpg"] == ("jpg", 40, 20, 72.0)
    assert cases["d.gif"][:3] == ("gif", 40, 20)
    assert cases["e.bmp"][:3] == ("bmp", 40, 20)
    assert cases["f.webp"][:3] == ("webp", 40, 20)


@pytest.mark.parametrize("svg, size", [
    ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"/>', (400, 200)),
    ('<svg xmlns="http://www.w3.org/2000/svg" width="72pt" height="1in"/>', (96, 96)),
    ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 60"/>', (120, 60)),
    ('<svg xmlns="http://www.w3.org/2000/svg"/>', (300, 150)),
])
def test_image_info_reads_svg_sizes(svg, size):
    assert image_info(svg.encode()) == ("svg", *size, 96.0)


def test_image_info_rejects_unknown_bytes():
    with pytest.raises(ValueError):
        image_info(b"not an image")


def test_webp_becomes_a_png_of_the_same_pixels(tmp_path):
    from PIL import Image as PILImage
    path = tmp_path / "x.webp"
    PILImage.new("RGB", (40, 20), (1, 2, 3)).save(path)
    png = webp_to_png(path.read_bytes(), 40, tmp_path)
    assert image_info(png)[:3] == ("png", 40, 20)
```

  그리고 `tests/test_writer_hwpx.py`:

```python
def test_hwpx_images_are_loaded_converted_or_replaced(tmp_path):
    from PIL import Image as PILImage
    PILImage.new("RGB", (40, 20)).save(tmp_path / "w.webp")
    (tmp_path / "t.bmp").write_bytes(tiny_bmp())
    md = "![w](w.webp) ![b](t.bmp) ![x](none.png)\n"
    doc, ctx = build(tmp_path, md, Format.HWPX)
    doc, images = _load_images(doc, ctx)
    kinds = sorted(image.ext for image in images.values())
    assert kinds == ["bmp", "png"]
    assert [e.code for e in ctx.report.events].count(Codes.IMAGE_FETCH_FAILED) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_images.py tests/test_writer_hwpx.py -q -k "image_info or webp or loaded"`
Expected: FAIL (`ImportError: image_info`)

- [ ] **Step 3: Implement** `image_info`, `webp_to_png`, the BMP case in `_extension`, and `_load_images` as specified.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_images.py tests/test_writer_hwpx.py tests/test_no_reject.py -q`
Expected: PASS. 기존 `bmp-image` 무거부 사례는 PDF 에서 여전히 `IMAGE_FETCH_FAILED` 이다.

- [ ] **Step 5: Commit**

```bash
git add src/mdcast/writers/images.py src/mdcast/writers/hwpx.py tests/test_images.py tests/test_writer_hwpx.py
git commit -m "feat: image sizes without Pillow, BMP detection, WebP to PNG for hwpx"
```

---

### Task 4: 칸 테두리 fill

**Files:**
- Modify: `src/mdcast/hwpx/header.py`
- Test: `tests/test_hwpx_header.py`

**Interfaces:**
- Produces:
  - `LINE_WIDTHS: tuple[float, ...]` = `(0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0)` (mm).
  - `line_width(pt: float) -> str`: pt → mm 후 가장 가까운 값, 같은 거리면 굵은 쪽. 문자열은 `f"{v:g} mm"` 이되 1.0–5.0 은 `"1.0 mm"` 처럼 소수 한 자리 (부록 B-4 의 문자열 그대로).
  - `Header.add_cell_border_fill(sides: tuple[Border | None, Border | None, Border | None, Border | None], fill: str | None) -> str`: 순서 left, right, top, bottom. `None` 변은 `type="NONE" width="0.1 mm"`. 배경이 있으면 `hc:fillBrush/hc:winBrush faceColor=<대문자>`, 없으면 fillBrush 를 쓰지 않는다. 요소 순서·속성은 부록 B-4. 같은 내용이면 같은 id (`_add` 의 중복 제거 그대로). `Border` 는 `mdcast.hwpx.look` 에서 import.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("pt, expected", [(0.34, "0.12 mm"), (0.5, "0.2 mm"), (1.0, "0.4 mm"),
                                          (0.1, "0.1 mm"), (3.0, "1.0 mm"), (100.0, "5.0 mm")])
def test_line_width_snaps_to_hangul_widths(pt, expected):
    assert line_width(pt) == expected


def test_cell_border_fill_sides_and_background():
    header = Header(Package.read(builtin_hwpx()).xml("Contents/header.xml"))
    outer, inner = Border(1.0, "#000000"), Border(0.5, "#333333")
    fill_id = header.add_cell_border_fill((outer, inner, outer, None), "#f2f2f2")
    fill = header.item("borderFills", fill_id)
    sides = [(e.get("type"), e.get("width"), e.get("color")) for e in fill
             if e.tag.endswith(("leftBorder", "rightBorder", "topBorder", "bottomBorder"))]
    assert sides == [("SOLID", "0.4 mm", "#000000"), ("SOLID", "0.2 mm", "#333333"),
                     ("SOLID", "0.4 mm", "#000000"), ("NONE", "0.1 mm", "#000000")]
    assert fill.find(f".//{{{HC}}}winBrush").get("faceColor") == "#F2F2F2"
    assert header.add_cell_border_fill((outer, inner, outer, None), "#f2f2f2") == fill_id
    assert header.item("borderFills", header.add_cell_border_fill((None,) * 4, None)).find(f"{{{HC}}}fillBrush") is None
```

- [ ] **Step 2: Run** `uv run python -m pytest tests/test_hwpx_header.py -q` — Expected: FAIL (`ImportError: line_width`)
- [ ] **Step 3: Implement** `LINE_WIDTHS`, `line_width`, `add_cell_border_fill`.
- [ ] **Step 4: Run** the same command — Expected: PASS
- [ ] **Step 5: Commit**

```bash
git add src/mdcast/hwpx/header.py tests/test_hwpx_header.py
git commit -m "feat(hwpx): cell border fills with Hangul's line widths"
```

---

### Task 5: 표 격자·열 너비·칸 모양 (XML 없음)

**Files:**
- Create: `src/mdcast/hwpx/table.py`
- Test: `tests/test_hwpx_table.py`

**Interfaces:**
- Consumes: `TableLook`, `Border` (Task 2).
- Produces:

```python
@dataclass(frozen=True)
class Slot:
    row: int
    col: int
    rowspan: int
    colspan: int
    cell: pf.TableCell | None  # None: a filler for a short row
    part: str  # "head" (table.head rows) | "body" (body.head + body.content rows) | "foot"
    body_row: int  # 0-based index among body-part rows (zebra); -1 outside the body

@dataclass(frozen=True)
class Grid:
    rows: list[list[Slot]]  # slots that start in each row, left to right
    cols: int

def build_grid(table: pf.Table) -> Grid
def column_widths(table: pf.Table, grid: Grid, look: TableLook, available: float, size_pt: float) -> list[float]  # mm
def slot_sides(slot: Slot, grid: Grid, look: TableLook) -> tuple[Border, Border, Border, Border]  # left, right, top, bottom
def slot_fill(slot: Slot, look: TableLook) -> str | None
def slot_valign(slot: Slot, look: TableLook) -> str  # "TOP" | "CENTER" | "BOTTOM"
```

- 규칙 (스펙 §4.1–§4.4):
  - 행 순서: `table.head.content` → 본문마다 `body.head` + `body.content` → `table.foot.content`. 열 수 = `len(table.colspec)`, 0 이면 행 중 가장 긴 칸 합.
  - span 은 `max(1, …)` 후 표 끝에서 자른다. 가려진 자리는 건너뛰고, 칸이 모자란 행 끝은 `cell=None` 1×1 슬롯으로 채운다.
  - `column_widths`: colspec 의 `ColWidthDefault` 는 "없음". `full`: 모두 있으면 합이 1 이 되게 늘려 × available, 없으면 같은 폭, 섞이면 없는 열 = 있는 값의 평균 후 정규화. `auto`: 있는 열 = 비율 × available, 없는 열 = 1×1 칸들의 `text_em(pf.stringify(cell)) × size_pt × 25.4/72 + 2 × padding` 의 최댓값, 최소 10mm. 합이 available 을 넘으면 비율대로 줄인다 (최소 10mm 보다 우선).
  - `slot_sides`: 표 바깥에 닿는 변 = `border_outer`, 나머지 = `border`.
  - `slot_fill`: head → `header_background`; 아니면 `col == 0` 이고 `first_column_background` 가 있으면 그것; 아니면 body 이고 `zebra` 가 있고 `body_row % 2 == 1` 이면 `zebra`; 아니면 None.
  - `slot_valign`: head → `header_valign`, 그 밖 → `body_valign`. top/middle/bottom → TOP/CENTER/BOTTOM.

- [ ] **Step 1: Write the failing tests** (`tests/test_hwpx_table.py`; `md_to_doc` 로 표를 만든다)

```python
MERGED = (
    "+------+------------+--------------------------+\n"
    "| 구분 | 항목       | 성능 기준                |\n"
    "|      |            +--------+--------+--------+\n"
    "|      |            | 최소   | 권장   | 비고   |\n"
    "+======+============+========+========+========+\n"
    "| 1    | 응답 시간  | 3초    | 1초    | 평균   |\n"
    "+------+------------+--------+--------+--------+\n"
)

def table(md):
    return md_to_doc(md).content[0]

def test_merged_header_grid_skips_covered_places():
    grid = build_grid(table(MERGED))
    assert grid.cols == 5
    assert [[(s.row, s.col, s.rowspan, s.colspan, s.part) for s in row] for row in grid.rows] == [
        [(0, 0, 2, 1, "head"), (0, 1, 2, 1, "head"), (0, 2, 1, 3, "head")],
        [(1, 2, 1, 1, "head"), (1, 3, 1, 1, "head"), (1, 4, 1, 1, "head")],
        [(2, 0, 1, 1, "body"), (2, 1, 1, 1, "body"), (2, 2, 1, 1, "body"), (2, 3, 1, 1, "body"), (2, 4, 1, 1, "body")],
    ]

def test_short_rows_get_fillers_and_spans_are_clipped():
    t = table("| a | b | c |\n|---|---|---|\n| 1 | 2 | 3 |\n")
    t.content[0].content[0].content = t.content[0].content[0].content[:1]  # body row with one cell
    t.content[0].content[0].content[0].colspan = 9
    grid = build_grid(t)
    assert [(s.col, s.colspan, s.cell is None) for s in grid.rows[1]] == [(0, 3, False)]
    t2 = table("| a | b |\n|---|---|\n| 1 | 2 |\n")
    t2.content[0].content[0].content = t2.content[0].content[0].content[:1]
    assert [(s.col, s.cell is None) for s in build_grid(t2).rows[1]] == [(0, False), (1, True)]

def test_full_widths_stretch_grid_table_fractions_to_the_available_width():
    t = table(MERGED)
    widths = column_widths(t, build_grid(t), TableLook(), 170.0, 10.0)
    assert sum(widths) == pytest.approx(170.0)
    assert widths[1] / widths[0] == pytest.approx(0.18055555 / 0.09722222, rel=1e-3)

def test_auto_widths_follow_text_and_minimum():
    t = table("| 짧 | 조금 더 긴 칸 글자 |\n|---|---|\n| 1 | 2 |\n")
    widths = column_widths(t, build_grid(t), TableLook(width="auto"), 170.0, 10.0)
    assert widths[0] == pytest.approx(10.0)
    assert 20.0 < widths[1] < 60.0

def test_auto_widths_never_exceed_available_even_with_minimums():
    head = "|" + "|".join(f" c{i} " for i in range(12)) + "|\n|" + "---|" * 12 + "\n"
    t = table(head + "|" + " 1 |" * 12 + "\n")
    assert sum(column_widths(t, build_grid(t), TableLook(width="auto"), 100.0, 10.0)) == pytest.approx(100.0)

def test_outer_sides_and_fill_priority():
    look = TableLook(header_background="#H", first_column_background="#F", zebra="#Z")
    grid = build_grid(table("| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"))
    (h0, h1), (b0, b1), (c0, c1) = grid.rows
    assert slot_sides(h0, grid, look) == (look.border_outer, look.border, look.border_outer, look.border)
    assert slot_sides(c1, grid, look) == (look.border, look.border_outer, look.border, look.border_outer)
    assert [slot_fill(s, look) for s in (h0, h1, b0, b1, c0, c1)] == ["#H", "#H", "#F", None, "#F", "#Z"]
    assert slot_valign(h0, TableLook(header_valign="bottom")) == "BOTTOM"
```

- [ ] **Step 2: Run** `uv run python -m pytest tests/test_hwpx_table.py -q` — Expected: FAIL (module missing)
- [ ] **Step 3: Implement** `src/mdcast/hwpx/table.py` (imports only `panflute`, `dataclasses`, `mdcast.hwpx.look`, and `text_em` from `mdcast.hwpx.section`). If importing `section` would be circular later (Task 6 imports `table` from `section`), move `text_em` into `table.py` or a small `hwpx/text.py` and import it from both.
- [ ] **Step 4: Run** the same command — Expected: PASS
- [ ] **Step 5: Commit**

```bash
git add src/mdcast/hwpx/table.py tests/test_hwpx_table.py
git commit -m "feat(hwpx): table grid, column widths and cell looks"
```

---

### Task 6: 표 XML, 칸 안 블록, 캡션

**Files:**
- Modify: `src/mdcast/hwpx/section.py`, `src/mdcast/hwpx/writer.py`
- Modify: `tests/helpers.py` (`hwpx_render`), `tests/test_hwpx_degraded.py`
- Test: `tests/test_hwpx_table.py`

**Interfaces:**
- Consumes: Task 4 `add_cell_border_fill`, Task 5 `build_grid`/`column_widths`/`slot_*`, Task 2 `Settings.tables`.
- Produces (`section.py`):
  - `Context` 에 `width: float = 0.0` (지금 단의 폭, mm), `align: str | None = None` (칸 문단 정렬), `note: bool = False` (각주·캡션 안: 각주는 낮춰 쓴다, Task 8).
  - `SectionWriter.__init__(self, header, shapes, settings, notices, width: float, pictures: Pictures | None = None, note_format: etree._Element | None = None)`. `build()` 의 최상위 `Context(width=width)`. (`pictures`·`note_format` 은 Task 7·8 에서 쓴다. 지금은 받기만 한다.)
  - `Paragraph.object(char: str, element: etree._Element) -> None`: run 에 개체를 붙이고 바로 뒤에 빈 `hp:t` 를 둔다 (이어지는 글자는 그 `hp:t` 에 들어감, 부록 B-1).
  - `SectionWriter.available(ctx: Context, element: str) -> float`: `ctx.width - self._left(element, ctx)`, 최소 10mm.
  - `SectionWriter._collect()`: `self.paragraphs` 를 잠시 새 목록으로 바꿔 그 안에 만든 문단 요소들을 돌려주는 context manager (칸·캡션·각주 subList 용). `_page_break` 는 바깥 것을 유지한다.
  - `sub_list(paragraphs: list[etree._Element], valign: str) -> etree._Element`: 부록 B-1 의 `hp:subList`.
- 동작 (스펙 §4, 부록 B-1·B-2·B-5·B-6·B-8):
  - `table(table, ctx)`: 격자에 행·열이 없으면 캡션만 캡션 문단으로 (M2a 의 `_caption`). 아니면 `look = settings.tables.get(table.attributes.get("mdcast-variant"), settings.tables[None])`, `size = look.font_size or settings.body_size`, `available = self.available(ctx, ctx.element)`, 표 폭 = `full` 이면 available, `auto` 면 열 합. 열 폭을 HWPUNIT 으로 반올림하고 마지막 열에서 합을 맞춘다.
  - 칸 모양: `_cell_shapes(look) -> dict[str, Shape]` = `self.shapes` 사본에서 `body` 만 바꾼다: para = `add_para(body.para, ParaSpec(line_height=look.line_height, prev=0, next=0))`, char = `add_char(body.char, CharSpec(size=size))`. 칸 블록을 만드는 동안 `self.shapes` 를 이것으로 바꾼다.
  - 칸 문단: `Context(element="body", width=<칸 폭 − 2×padding>, align=<칸 정렬>, note=ctx.note)`. 칸 정렬 = `cell.alignment` 가 `AlignDefault` 가 아니면 그것, 아니면 `table.colspec[col]` 의 정렬; `AlignLeft/Center/Right` → `left/center/right`, 그 밖 → None. `_para_id` 는 `ctx.align` 이 있으면 `align=` 변경으로 넣는다. 블록이 없는 칸은 빈 문단 하나. 칸 안 `RawBlock` 쪽 나눔은 무시 (블록 처리 후 `_page_break = False` 로 되돌림).
  - XML: 부록 B-1 그대로. `hp:tbl` 의 `borderFillIDRef` = `add_cell_border_fill((None,)*4, None)`, `repeatHeader` = `look.header_repeat`, 머리 칸 `header="1"`, `inMargin`·모든 `cellMargin` = `hwpunit(look.padding)`, `hasMargin="0"`. 칸 `cellSz height` = `hwpunit(size × 25.4/72 × (look.line_height or 1.0)) + 2 × hwpunit(padding)`, 표 `sz height` = 행마다 그 값의 합. `id`·`zOrder` 는 SectionWriter 의 문서 단위 카운터(1부터).
  - 캡션: `<hp:caption side="TOP|BOTTOM" fullSz="0" width="8504" gap="850" lastWidth="<표 폭>">` + `sub_list(<캡션 문단>, "TOP")`, `outMargin` 다음·`inMargin` 앞. 캡션 문단은 `caption` 모양, Context `note=True`. side 는 `settings.table_caption_above`.
  - 표를 담는 문단은 `self.paragraph(ctx.element, ctx)` 이고 그 run 에 `object()` 로 넣는다.
  - `_DEGRADED["table"]` 와 행 문단으로 낮추던 코드를 지운다.
- `writer.write()`: `sec_pr` 를 찾은 직후 `apply_page(sec_pr, settings.page)` 와 `width = body_width(sec_pr)` 를 먼저 하고 SectionWriter 에 넘긴다 (`assemble` 이 다시 `apply_page` 해도 같은 값). `apply_page`, `body_width` 는 `hwpx/page.py` 에서 import.
- `tests/helpers.py` 의 `hwpx_render` 는 `SectionWriter(..., width=170.0)` 로 만든다. `test_hwpx_degraded.py` 의 표 두 테스트는 지운다.

- [ ] **Step 1: Write the failing tests** (`tests/test_hwpx_table.py` 에 추가; `hwpx_render` 결과 문단에서 `hp:tbl` 을 찾는 작은 도우미 `tbl(paragraphs)` 를 테스트 파일에 둔다)

```python
def test_table_xml_matches_the_sample_shape():
    header, shapes, paragraphs, notices = hwpx_render(MERGED)
    t = tbl(paragraphs)
    assert (t.get("rowCnt"), t.get("colCnt"), t.get("repeatHeader"), t.get("pageBreak")) == ("3", "5", "1", "CELL")
    assert [c.tag.split("}")[1] for c in t][:4] == ["sz", "pos", "outMargin", "inMargin"]
    assert t.find("hp:pos", NS).get("treatAsChar") == "1"
    assert int(t.find("hp:sz", NS).get("width")) == hwpunit(170.0)
    cells = t.findall("hp:tr/hp:tc", NS)
    assert len(cells) == 11  # 15 places in the 3x5 grid, 4 covered by the two spans
    assert [c.get("header") for c in cells[:6]] == ["1"] * 6
    first = cells[0]
    assert first.find("hp:cellSpan", NS).attrib == {"colSpan": "1", "rowSpan": "2"}
    assert first.find("hp:subList", NS).get("vertAlign") == "CENTER"
    assert first.find("hp:cellMargin", NS).get("left") == str(hwpunit(1.5))
    body = cells[6:]  # the five body cells, one per column
    assert sum(int(c.find("hp:cellSz", NS).get("width")) for c in body) == int(t.find("hp:sz", NS).get("width"))
    assert notices.items == []

def test_table_paragraph_ends_with_an_empty_text():
    _, _, paragraphs, _ = hwpx_render("| a |\n|---|\n| 1 |\n")
    run = tbl(paragraphs).getparent()
    assert [c.tag.split("}")[1] for c in run] == ["tbl", "t"]

def test_header_cells_get_the_header_background():
    header, _, paragraphs, _ = hwpx_render("| a | b |\n|---|---|\n| 1 | 2 |\n",
                                           hwpx_settings(tables={None: TableLook(header_background="#F2F2F2")}))
    cells = tbl(paragraphs).findall("hp:tr/hp:tc", NS)
    faces = [header.item("borderFills", c.get("borderFillIDRef")).find(".//hc:winBrush", NS) for c in cells]
    assert [f is not None and f.get("faceColor") for f in faces] == ["#F2F2F2", "#F2F2F2", False, False]

def test_variant_attribute_picks_the_variant_look():
    doc = md_to_doc("| a |\n|---|\n| 1 |\n")
    doc.content[0].attributes["mdcast-variant"] = "얇게"
    looks = {None: TableLook(), "얇게": TableLook(border=Border(0.34), border_outer=Border(0.34))}
    header, _, paragraphs, _ = hwpx_render("", hwpx_settings(tables=looks), doc=doc)
    fill = header.item("borderFills", tbl(paragraphs).find("hp:tr/hp:tc", NS).get("borderFillIDRef"))
    assert {e.get("width") for e in fill if e.tag.endswith("Border")} == {"0.12 mm"}

def test_caption_is_a_hangul_caption_without_autonum():
    _, shapes, paragraphs, _ = hwpx_render("Table: <표 1> 요약\n\n| a |\n|---|\n| 1 |\n")
    caption = tbl(paragraphs).find("hp:caption", NS)
    assert caption.get("side") == "TOP"
    p = caption.find("hp:subList/hp:p", NS)
    assert p.get("styleIDRef") == shapes["caption"].style
    assert p.find(".//hp:autoNum", NS) is None and "요약" in "".join(p.itertext())

def test_cell_paragraphs_use_the_table_size_and_cell_alignment():
    header, shapes, paragraphs, _ = hwpx_render("| a |\n|--:|\n| 1 |\n", hwpx_settings(tables={None: TableLook(font_size=9.0)}))
    p = tbl(paragraphs).find("hp:tr/hp:tc/hp:subList/hp:p", NS)
    char = header.item("charProperties", p.find("hp:run", NS).get("charPrIDRef"))
    para = header.item("paraProperties", p.get("paraPrIDRef"))
    assert char.get("height") == "900"
    assert para.find(".//hh:align", NS).get("horizontal") == "RIGHT"

def test_nested_table_uses_the_cell_inner_width():
    doc = md_to_doc("| 바깥 |\n|---|\n| x |\n")
    inner = md_to_doc("| 안 |\n|---|\n| y |\n").content[0]
    doc.content[0].content[0].content[0].content[0].content = [inner]
    _, _, paragraphs, _ = hwpx_render("", doc=doc)
    outer = tbl(paragraphs)
    nested = outer.find(".//hp:tc//hp:tbl", NS)
    assert abs(int(nested.find("hp:sz", NS).get("width")) - (hwpunit(170.0) - 2 * hwpunit(1.5))) <= 1

def test_table_in_list_item_is_narrower():
    _, _, paragraphs, _ = hwpx_render("- 항목\n\n    | a |\n    |---|\n    | 1 |\n")
    assert int(tbl(paragraphs).find("hp:sz", NS).get("width")) < hwpunit(170.0)

def test_empty_table_writes_only_its_caption():
    doc = md_to_doc("Table: 빈 표\n\n| a |\n|---|\n| 1 |\n")
    t = doc.content[0]
    t.head.content = []
    t.content[0].content = []
    _, _, paragraphs, _ = hwpx_render("", doc=doc)
    assert hwpx_texts(paragraphs) == ["빈 표"]
```

  (`NS` 는 `helpers.HWPX_NS`, `hwpunit` 은 `mdcast.hwpx.units`.)

- [ ] **Step 2: Run** `uv run python -m pytest tests/test_hwpx_table.py -q` — Expected: 새 테스트 FAIL (표가 행 문단으로 나옴)
- [ ] **Step 3: Implement** the `section.py` and `writer.py` changes above; update `hwpx_render` and `test_hwpx_degraded.py`.
- [ ] **Step 4: Run** `uv run python -m pytest tests/test_hwpx_*.py tests/test_writer_hwpx.py -q` — Expected: PASS. 그리고 `uv run python -m pytest tests/test_writer_hwpx.py -q -k pipeline` 로 `hwpx_integrity` 가 표 문서에서도 통과하는지 본다 (칸 문단의 `paraPrIDRef`·`charPrIDRef`·`borderFillIDRef` 가 모두 있어야 함). `helpers.hwpx_integrity` 에 `hp:tc` 의 `borderFillIDRef`, `hp:tbl` 의 `borderFillIDRef` 검사를 더한다.
- [ ] **Step 5: Commit**

```bash
git add src/mdcast/hwpx/section.py src/mdcast/hwpx/writer.py tests/helpers.py tests/test_hwpx_table.py tests/test_hwpx_degraded.py
git commit -m "feat(hwpx): real tables — merged cells, borders, header rows, captions, nested tables"
```

---

### Task 7: 그림

**Files:**
- Create: `src/mdcast/hwpx/picture.py`
- Modify: `src/mdcast/hwpx/section.py`, `src/mdcast/hwpx/writer.py`, `src/mdcast/writers/hwpx.py` (`_write`: `settings.images`), `tests/helpers.py` (`hwpx_render` 에 `Pictures`), `tests/test_hwpx_degraded.py`
- Test: `tests/test_hwpx_picture.py`

**Interfaces:**
- Consumes: `Image` (Task 2), `Paragraph.object`, `available`, `sub_list`, `_collect` (Task 6).
- Produces (`picture.py`):

```python
MEDIA = {"png": "image/png", "jpg": "image/jpg", "gif": "image/gif", "bmp": "image/bmp", "svg": "image/svg"}

def parse_length(value: str, available_mm: float) -> float | None  # "50%", "60mm", "6cm", "2in", "72pt", "300px", "300" (px at 96dpi); else None
def picture_size(image: Image, width: str | None, height: str | None, available_mm: float,
                 max_ratio: float | None, max_mm: float | None) -> tuple[float, float]  # mm

class Pictures:
    def __init__(self, package: Package, content: etree._Element) -> None
    def add(self, image: Image) -> str  # manifest item id

def picture_element(item_id: str, image: Image, width_mm: float, height_mm: float, alt: str,
                    number: int, caption: etree._Element | None) -> etree._Element
```

- 규칙 (스펙 §5, 부록 B-9):
  - `picture_size`: 원래 크기 = px / dpi × 25.4. 속성이 둘 다 있으면 그대로, 하나면 비율 유지. 상한 = `min(available, max_ratio × available)` 또는 `min(available, max_mm)` (둘 다 None 이면 available). 폭이 상한을 넘으면 비율 유지로 줄인다.
  - `Pictures.add`: 같은 바이트(sha256)면 같은 id. 새 이름은 `mdcastimg<n>.<ext>`, id 는 `mdcastimg<n>`, n 은 1 부터 그릇의 기존 엔트리 이름·manifest id 와 겹치지 않을 때까지 올린다. `package.set("BinData/<이름>", data)` (deflate), manifest 에 `<opf:item id=… href="BinData/<이름>" media-type=MEDIA[ext] isEmbeded="1"/>`.
  - `picture_element`: 부록 B-9 그대로. 비트맵 `orgSz` = round(px × 93.75), `imgDim` = round(px × 75); SVG `orgSz` = px × 75, `imgDim` = px × 60. W·H = `hwpunit(width_mm)`, `hwpunit(height_mm)`. `scaMatrix` e1 = W/OW, e5 = H/OH (소수 6자리). `id`·`zOrder`·`instid` = number. `shapeComment` = alt (XML 금지 문자 제거). `caption` 이 있으면 `outMargin` 다음·`shapeComment` 앞.
- SectionWriter (`section.py`):
  - 인라인 `pf.Image`: `image = settings.images.get(item.url)`; 없으면 지금의 `[이미지: …]` 글자 (알림 없음 — 어댑터가 이미 알렸다). 있으면 크기 = `picture_size(image, item.attributes.get("width"), item.attributes.get("height"), self.available(ctx…), settings.figure_max_ratio, settings.figure_max_mm)` 후 `paragraph.object(char, picture_element(…, caption=None))`. 인라인 처리에서 `ctx` 가 필요하므로 `inlines()`/`inline()` 에 지금 블록의 쓸 수 있는 폭 `width: float` 인자를 더한다 (호출부는 `self.available(ctx, element)` 를 넘긴다).
  - `pf.Figure`: 문단 하나를 `figure_align` 정렬(`_para_id(..., align=settings.figure_align)`)로 만들고 그림을 넣는다. 그림 안 `pf.Image` 가 정확히 하나면 캡션을 그 그림의 `hp:caption` (side = `figure_caption_above` 이면 TOP, 아니면 BOTTOM, `lastWidth` = 그림 폭, 캡션 문단 Context `note=True`), 아니면 M2a 방식 캡션 문단.
  - `_DEGRADED["image"]` 를 지운다. `test_hwpx_degraded.py` 의 이미지 테스트를 지운다.
- `writer.write()`: `Pictures(package, content)` 를 만들어 SectionWriter 에 넘긴다. `writers/hwpx.py` `_write()`: Task 3 의 `_load_images` 결과를 `dataclasses.replace(settings, images=images)` 로 넣는다.

- [ ] **Step 1: Write the failing tests** (`tests/test_hwpx_picture.py`)

```python
PNG400 = Image(data=b"png-bytes", ext="png", width_px=400, height_px=200, dpi=96.0)

def test_picture_size_rules():
    assert picture_size(PNG400, None, None, 170.0, 1.0, None) == pytest.approx((105.833, 52.917), rel=1e-3)
    assert picture_size(PNG400, "50%", None, 170.0, 1.0, None) == pytest.approx((85.0, 42.5))
    assert picture_size(PNG400, "60mm", "10mm", 170.0, 1.0, None) == pytest.approx((60.0, 10.0))
    assert picture_size(PNG400, None, None, 80.0, 1.0, None) == pytest.approx((80.0, 40.0))
    assert picture_size(PNG400, None, None, 170.0, None, 50.0) == pytest.approx((50.0, 25.0))
    assert picture_size(replace(PNG400, dpi=300.0), None, None, 170.0, 1.0, None)[0] == pytest.approx(33.867, rel=1e-3)

@pytest.mark.parametrize("value, mm", [("50%", 85.0), ("60mm", 60.0), ("6cm", 60.0), ("1in", 25.4),
                                       ("72pt", 25.4), ("96px", 25.4), ("96", 25.4), ("auto", None)])
def test_parse_length(value, mm):
    assert parse_length(value, 170.0) == (None if mm is None else pytest.approx(mm))

def test_picture_element_follows_the_sample():
    pic = picture_element("mdcastimg1", PNG400, 50.0, 25.0, "설명", 7, None)
    assert pic.find("hp:orgSz", NS).attrib == {"width": "37500", "height": "18750"}
    assert pic.find("hp:imgDim", NS).attrib == {"dimwidth": "30000", "dimheight": "15000"}
    assert pic.find("hp:sz", NS).get("width") == str(hwpunit(50.0))
    assert pic.find("hp:curSz", NS).get("width") == str(hwpunit(50.0))
    assert pic.find("hc:img", NS).get("binaryItemIDRef") == "mdcastimg1"
    assert pic.find("hp:pos", NS).get("treatAsChar") == "1"
    assert pic.find("hp:shapeComment", NS).text == "설명"
    svg = picture_element("x", replace(PNG400, ext="svg"), 50.0, 25.0, "", 1, None)
    assert svg.find("hp:orgSz", NS).get("width") == "30000" and svg.find("hp:imgDim", NS).get("dimwidth") == "24000"

def test_same_image_shares_one_bindata():
    package = Package.read(builtin_hwpx())
    content = package.xml("Contents/content.hpf")
    pictures = Pictures(package, content)
    assert pictures.add(PNG400) == pictures.add(replace(PNG400)) == "mdcastimg1"
    assert [n for n in package.names() if n.startswith("BinData/")] == ["BinData/mdcastimg1.png"]

def test_pictures_do_not_clash_with_container_bindata():
    package = Package.read(builtin_hwpx())
    package.set("BinData/mdcastimg1.png", b"old")
    content = package.xml("Contents/content.hpf")
    item_id = Pictures(package, content).add(PNG400)
    assert item_id == "mdcastimg2" and package.get("BinData/mdcastimg1.png") == b"old"
    items = [i for i in content.iter("{http://www.idpf.org/2007/opf/}item") if i.get("id") == "mdcastimg2"]
    assert items[0].attrib == {"id": "mdcastimg2", "href": "BinData/mdcastimg2.png",
                               "media-type": "image/png", "isEmbeded": "1"}

def test_inline_and_figure_pictures_in_the_section():
    images = {"a.png": PNG400}
    _, shapes, paragraphs, _ = hwpx_render("앞 ![작게](a.png){width=20mm} 뒤\n\n![그림 설명](a.png)\n",
                                           hwpx_settings(images=images))
    inline, figure = paragraphs
    assert hwpx_texts([inline]) == ["앞  뒤"]
    assert inline.find(".//hp:pic/hp:sz", NS).get("width") == str(hwpunit(20.0))
    caption = figure.find(".//hp:pic/hp:caption", NS)
    assert caption.get("side") == "BOTTOM" and "그림 설명" in "".join(caption.itertext())

def test_picture_in_quote_fits_the_indented_width():
    wide = Image(data=b"w", ext="png", width_px=4000, height_px=1000)
    _, _, paragraphs, _ = hwpx_render("> ![넓은 그림](w.png)\n", hwpx_settings(images={"w.png": wide}))
    assert int(paragraphs[0].find(".//hp:pic/hp:sz", NS).get("width")) == hwpunit(170.0 - 5.0)

def test_picture_in_a_cell_fits_the_cell():
    wide = Image(data=b"w", ext="png", width_px=4000, height_px=1000)
    _, _, paragraphs, _ = hwpx_render("| ![a](w.png) | b |\n|---|---|\n| 1 | 2 |\n", hwpx_settings(images={"w.png": wide}))
    cell = paragraphs[0].find(".//hp:tc", NS)
    pic = cell.find(".//hp:pic", NS)
    assert int(pic.find("hp:sz", NS).get("width")) <= int(cell.find("hp:cellSz", NS).get("width")) - 2 * hwpunit(1.5)

def test_write_registers_bindata_and_manifest(tmp_path):
    (tmp_path / "a.png").write_bytes(tiny_png())
    parts, ctx = render(tmp_path, "![그림](a.png)\n")  # helper from test_writer_hwpx (copy it here)
    pic = next(parts["Contents/section0.xml"].iter(f"{{{NS['hp']}}}pic"))
    item_id = pic.find("hc:img", NS).get("binaryItemIDRef")
    hrefs = {i.get("id"): i.get("href") for i in parts["Contents/content.hpf"].iter(f"{{{NS['opf']}}}item")}
    assert hrefs[item_id].startswith("BinData/mdcastimg")
```

  (`hwpx_render` 는 내장 그릇의 `Package`·`content.hpf` 로 `Pictures` 를 만들어 넘긴다. `test_hwpx_picture.py` 의 `render` 는 `test_writer_hwpx.py` 의 것과 같게 둔다. 인용 들여쓰기 5mm 는 `hwpx_settings()` 의 quote `indent_left=5`.)

- [ ] **Step 2: Run** `uv run python -m pytest tests/test_hwpx_picture.py -q` — Expected: FAIL (module missing)
- [ ] **Step 3: Implement** `picture.py` and the section/writer/adapter changes. `helpers.hwpx_integrity` 에 "모든 `binaryItemIDRef` 가 manifest id 이고 그 href 가 패키지에 있다" 검사를 더한다.
- [ ] **Step 4: Run** `uv run python -m pytest tests/test_hwpx_*.py tests/test_writer_hwpx.py tests/test_no_reject.py -q` — Expected: PASS
- [ ] **Step 5: Commit**

```bash
git add src/mdcast/hwpx/picture.py src/mdcast/hwpx/section.py src/mdcast/hwpx/writer.py src/mdcast/writers/hwpx.py tests/helpers.py tests/test_hwpx_picture.py tests/test_hwpx_degraded.py
git commit -m "feat(hwpx): embedded pictures — sizes, limits, figure captions, shared BinData"
```

---

### Task 8: 각주

**Files:**
- Modify: `src/mdcast/hwpx/section.py`, `src/mdcast/hwpx/writer.py`, `tests/test_hwpx_degraded.py`
- Test: `tests/test_hwpx_notes.py`

**Interfaces:**
- Consumes: `Context.note`, `_collect`, `sub_list` (Task 6), `note_format` 인자.
- 동작 (스펙 §6, 부록 B-12):
  - `writer.write()` 는 `note_format = sec_pr.find(f"{hp('footNotePr')}/{hp('autoNumFormat')}")` 를 SectionWriter 에 넘긴다.
  - `pf.Note` 이고 `ctx.note` 가 거짓이면 한글 각주: 번호 n = 문서의 실제 각주 순번(1부터). `paragraph.control(char)` 안에 `hp:footNote number=n suffixChar="41" instId=<카운터>` + `sub_list(<문단들>, "TOP")`. 첫 문단은 `footnote` 모양이고 run 이 `hp:ctrl/hp:autoNum num=n numType="FOOTNOTE"` + `autoNumFormat` (note_format 의 사본, 없으면 부록 B-12 의 DIGIT·`)` 기본) 로 시작한 뒤 `" "` 와 첫 Para/Plain 의 글자. 첫 블록이 Para/Plain 이 아니면 번호만 든 첫 문단 뒤에 블록들. 나머지 블록은 `Context(element="footnote", width=self.width, note=True)`.
  - `ctx.note` 가 참(각주 안·캡션 안)이면 낮춘다: 본문에 `[주 m]` (m 은 낮춘 각주끼리 1부터), 문서 끝에 `[주 m] 내용` 문단 (기존 `_note` 를 접두만 바꿔 씀), `notices.add("degraded", "footnote", "hwpx 는 각주 안·캡션 안에 각주를 넣을 수 없어 문서 끝에 [주 n] 으로 모아 썼습니다")`.
  - `_DEGRADED` 에는 `math` 와 위 `footnote` 문구만 남긴다. `test_hwpx_degraded.py` 의 각주 테스트를 지운다.

- [ ] **Step 1: Write the failing tests** (`tests/test_hwpx_notes.py`)

```python
def notes(paragraphs):
    return [n for p in paragraphs for n in p.iter(f"{{{NS['hp']}}}footNote")]

def test_footnotes_are_hangul_footnotes():
    _, shapes, paragraphs, notices = hwpx_render("본문[^1] 둘[^2]\n\n[^1]: 첫 각주\n[^2]: 둘째\n\n    둘째 문단\n")
    first, second = notes(paragraphs)
    assert [n.get("number") for n in (first, second)] == ["1", "2"]
    p = first.find("hp:subList/hp:p", NS)
    assert p.get("styleIDRef") == shapes["footnote"].style
    auto = p.find("hp:run/hp:ctrl/hp:autoNum", NS)
    assert (auto.get("num"), auto.get("numType")) == ("1", "FOOTNOTE")
    assert auto.find("hp:autoNumFormat", NS).get("suffixChar") == ")"
    assert "".join(p.itertext()).strip() == "첫 각주"
    assert len(second.findall("hp:subList/hp:p", NS)) == 2
    assert hwpx_texts(paragraphs) == ["본문 둘"]
    assert notices.items == []

def test_footnote_in_a_cell_is_a_footnote():
    _, _, paragraphs, notices = hwpx_render("| a |\n|---|\n| 칸[^1] |\n\n[^1]: 칸 각주\n")
    assert len(notes(paragraphs)) == 1 and notices.items == []

def test_note_in_note_falls_back_with_its_own_numbers():
    md = "가[^1] 나[^2]\n\n[^1]: 바깥[^3]\n[^2]: 둘째\n[^3]: 안쪽\n"
    doc = md_to_doc(md)
    _, _, paragraphs, notices = hwpx_render("", doc=doc)
    numbers = [n.get("number") for n in notes(paragraphs)]
    assert numbers == ["1", "2"]
    inner_text = "".join(notes(paragraphs)[0].itertext())
    assert "[주 1]" in inner_text
    assert hwpx_texts(paragraphs)[-1] == "[주 1] 안쪽"
    assert [(n.kind, n.element) for n in notices.items] == [("degraded", "footnote")]
```

  (pandoc 이 각주 안 각주 참조를 그대로 두지 않으면, 세 번째 테스트는 `doc` 의 첫 `pf.Note` 내용에 `pf.Note(pf.Para(pf.Str("안쪽")))` 를 직접 넣어 만든다.)

- [ ] **Step 2: Run** `uv run python -m pytest tests/test_hwpx_notes.py -q` — Expected: FAIL (문서 끝 `[1]` 문단이 나옴)
- [ ] **Step 3: Implement** the changes above.
- [ ] **Step 4: Run** `uv run python -m pytest -q` — Expected: 전체 PASS
- [ ] **Step 5: Commit**

```bash
git add src/mdcast/hwpx/section.py src/mdcast/hwpx/writer.py tests/test_hwpx_notes.py tests/test_hwpx_degraded.py
git commit -m "feat(hwpx): Hangul footnotes; notes inside notes or captions fall back to [주 n]"
```

---

### Task 9: 픽스처, 무거부, 한글 COM 검증, README, 시각 확인

**Files:**
- Create: `tests/fixtures/md/tables-images.md`, `tests/fixtures/md/assets/wide.png`, `tests/fixtures/templates/submission/template.yaml`
- Modify: `tests/test_hangul.py`, `tests/test_no_reject.py`, `tests/test_e2e.py` (픽스처 목록에 추가), `README.md`
- Modify: `docs/superpowers/specs/2026-10-20-mdcast-m2b-hwpx-design.md` (§9 체크 결과 한 줄)

**Interfaces:**
- Consumes: 전 Task 의 결과 전체.

- [ ] **Step 1: 픽스처 만들기**

`tests/fixtures/md/assets/wide.png`: `uv run python -c "from PIL import Image; Image.new('RGB', (2400, 600), (40, 120, 200)).save('tests/fixtures/md/assets/wide.png')"`.

`tests/fixtures/templates/submission/template.yaml`:

```yaml
schema: 1
name: submission
version: 1.0.0
extends: default
tables:
  variants:
    제출양식:
      border: { width: 0.34pt }
      border_outer: { width: 0.34pt }
      header: { background: "#E5E5E5" }
```

`tests/fixtures/md/tables-images.md` (스펙 §8.4 의 여섯 가지를 모두 담는다):

````markdown
---
title: 표·그림 시험 문서
---

# 성능 기준

Table: 성능 기준표

+------+------------+--------------------------+
| 구분 | 항목       | 성능 기준                |
|      |            +--------+--------+--------+
|      |            | 최소   | 권장   | 비고   |
+======+============+========+========+========+
| 1    | 응답 시간  | 3초    | 1초    | 평균   |
+------+------------+--------+--------+--------+
| 2    | 동시 접속  | 100    | 500    | 최대   |
+------+------------+--------+--------+--------+

# 화면 예시

| ![화면 1](assets/sample.png) | ![화면 2](assets/sample.png) |
|:---:|:---:|
| 로그인 화면 | 목록 화면[^cell] |

<!-- table: 제출양식 -->

| 번호 | 기능 | 설명 |
|---|---|---|
| 1 | 등록 | 신규 항목을 등록한다 |
| 2 | 조회 | 조건으로 찾는다 |

# 그림

본문 안 작은 그림 ![아이콘](assets/sample.png){width=8mm} 이 글자처럼 놓인다.

![넓은 그림은 본문 폭으로 줄어든다](assets/wide.png)

![폭 40%](assets/sample.png){width=40%}

# 각주

각주가 있는 문장[^1]과 목록이 든 각주[^2].

[^1]: 첫 각주 내용.
[^2]: 각주 안 목록:

    - 하나
    - 둘

[^cell]: 칸 안 각주.

# 긴 표

| 번호 | 항목 | 값 |
|---|---|---|
````

  그리고 마지막 표에 행 60개를 덧붙인다 (`| n | 항목 n | 값 n |`, n=1..60 — 파일에 직접 적는다. 쪽을 넘겨 머리행 반복을 보기 위함).

- [ ] **Step 2: 무거부 사례 추가** (`tests/test_no_reject.py` 의 `CONTENT_CASES`)

```python
    "merged-and-ragged-tables": (
        "+---+---+\n| a | b |\n+   +---+\n|   | c |\n+---+---+\n\n| a | b | c |\n|---|---|---|\n| 1 |\n",
        {}, None, ["a", "c"]),
    "webp-image": (_images_md("pic.webp"), {"pic.webp": _webp()}, None, ["앞 문단", "뒤 문단"]),
    "note-in-note-and-cell": (
        "가[^1]\n\n| 칸[^2] |\n|---|\n| x |\n\n[^1]: 바깥 각주\n[^2]: 칸 각주\n", {}, None, ["가", "칸"]),
```

  `_webp()` 는 Pillow 로 2×2 WebP 바이트를 만드는 작은 함수 (`tests/helpers.py` 의 `tiny_bmp` 와 같은 방식, 이름 `tiny_webp` 로 helpers 에 둔다). 이 사례들은 `_convert` 가 docx·hwpx·pdf 모두 만들므로 세 형식 모두 거부하지 않는지 본다.

  Run: `uv run python -m pytest tests/test_no_reject.py -q` — Expected: PASS

- [ ] **Step 3: e2e 에 픽스처 추가**

  `tests/test_e2e.py` 의 픽스처 목록에 `tables-images` 를 더하고, 템플릿 `tests/fixtures/templates/submission` 으로도 한 번 변환한다 (e2e 가 템플릿 인자를 받는 방식은 기존 코드를 따른다). hwpx 결과에 대해 `hwpx_integrity` 가 통과하고, section0.xml 에 `hp:tbl` 4개(성능 기준표, 화면 표, 제출양식 표, 긴 표), `hp:pic` 5개(본문 3 + 칸 안 2), `hp:footNote` 3개가 있는지 본다.

  Run: `uv run python -m pytest tests/test_e2e.py -q` — Expected: PASS

- [ ] **Step 4: 한글 COM 테스트** (`tests/test_hangul.py`)

  `test_hangul_opens_fixture` 의 parametrize 에 `"tables-images"` 를 더한다. 새 테스트:

```python
def top_controls(hwp) -> list[str]:
    ids, ctrl = [], hwp.HeadCtrl
    while ctrl is not None:
        ids.append(ctrl.CtrlID)
        ctrl = ctrl.Next
    return ids


def test_tables_pictures_footnotes_open_as_objects(hangul, tmp_path):
    md = (FIXTURES / "tables-images.md").read_text(encoding="utf-8")
    path, _ = convert(tmp_path, md, "tables-images")
    assert hangul.Open(str(path.resolve()), "HWPX", "")
    ids = top_controls(hangul)
    text = hangul.GetTextFile("UNICODE", "")
    pages = hangul.PageCount
    hangul.Clear(1)
    assert ids.count("tbl") == 4
    assert ids.count("gso") == 3       # inline icon, wide figure, 40% figure (the cell pictures sit inside a table)
    assert ids.count("fn") == 2        # body notes; the cell note sits inside a table
    for needle in ("성능 기준", "로그인 화면", "첫 각주 내용", "칸 안 각주", "항목 60"):
        assert needle in text
    assert pages >= 2
```

  `convert()` 는 이미지가 있는 픽스처를 위해 `base_dir=FIXTURES` 로 만들어야 한다 (지금은 `tmp_path`). `convert(tmp_path, md, name, base_dir=FIXTURES)` 인자를 더한다. CtrlID 문자열("tbl", "gso", "fn")은 이 테스트를 처음 돌릴 때 `print(ids)` 로 한 번 확인하고, 다르면 실제 값으로 고친 뒤 고친 이유를 커밋 메시지에 적는다.

  Run: `uv run python -m pytest tests/test_hangul.py --run-hangul -q` — Expected: PASS (한글이 설치된 이 PC 에서)

- [ ] **Step 5: README**

  `README.md` 의 "hwpx 출력 (M2a)" 절을 "hwpx 출력" 으로 바꾸고:
  - "낮춰 출력하는 요소" 에서 표·이미지·각주를 뺀다. 남는 것: 수식(LaTeX 원문), 각주 안·캡션 안 각주(`[주 n]` 으로 문서 끝에).
  - hwpx 표는 템플릿 `tables` 설정을 따르고, 사용자 reference.hwpx 를 써도 표 설정이 모두 적용된다 (docx 는 그릇의 표 스타일이 이김). 테두리 굵기는 한글 굵기 목록의 가장 가까운 값.
  - 이미지: PNG·JPEG·GIF·BMP·SVG 는 그대로, WebP 는 PNG 로 바꿔 넣는다. 크기는 DPI 기준(없으면 96)이고 `figures.max_width` 와 쓸 수 있는 폭을 넘지 않는다.
  - 예시 문서 같은 표 모양은 표 종류로 만든다 (`tests/fixtures/templates/submission/template.yaml` 의 `제출양식` 예).

- [ ] **Step 6: 시각 확인 자료 만들기**

  Run: `uv run python -m pytest tests/test_e2e.py -q` 후
  `uv run python scripts/render_pages.py .test-output/e2e/tables-images.hwpx .test-output/e2e/tables-images.docx .test-output/e2e/tables-images.pdf .test-output/e2e/kitchen-sink.hwpx`
  Expected: PNG 가 만들어진다. 구현자는 PNG 를 직접 열어 (1) 병합 머리행, (2) 칸 안 그림 2×2, (3) 제출양식 표의 가는 테두리·`#E5E5E5` 머리행, (4) 긴 표 2쪽 머리행 반복, (5) 각주가 쪽 아래에 있는지 확인하고, 결과를 사용자에게 보여 승인을 받는다 (스펙 §8.5). 승인 결과는 스펙 §9 아래에 날짜와 함께 한 줄로 적는다.

- [ ] **Step 7: 전체 확인과 커밋**

  Run: `uv run python -m pytest -q && uv run ruff check src tests`
  Expected: 모두 PASS, 린트 오류 없음

```bash
git add tests/fixtures tests/test_no_reject.py tests/test_e2e.py tests/test_hangul.py tests/helpers.py README.md docs/superpowers/specs/2026-10-20-mdcast-m2b-hwpx-design.md
git commit -m "test(hwpx): tables-images fixture, Hangul object checks, no-reject cases; README"
```
