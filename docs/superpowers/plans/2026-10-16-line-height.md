# line_height 의미 통일 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `line_height: N%` 를 "줄 하나의 높이 = 글자 크기 × N/100" 으로 정의하고, docx(Word "고정" 줄 간격)와 PDF(Typst 줄 상자 모델)가 같은 줄 피치를 내게 한다.

**Architecture:** 템플릿 값(내장 default 의 모든 요소 + 새 키 `tables.line_height`)을 정한 뒤, PDF 는 설정 JSON 에 비율을 넘기고 `pdf.typ` 가 `text(top-edge, bottom-edge)` + `par(leading: 0em)` 로 줄 상자 높이를 정확히 맞춘다. docx 는 스타일·표 셀에 `lineRule="exact"` 를 쓰고, 이미지·수식이 든 문단만 `atLeast` 로 풀어 잘리지 않게 한다. 마지막에 Word 로 docx 를 PDF 로 내보내 두 형식의 줄 피치를 비교하는 선택 실행 테스트를 둔다.

**Tech Stack:** Python 3.12, uv, pytest, python-docx 1.2, lxml, typst-py 0.15, pypdfium2, pywin32(Word COM, 선택 테스트만)

**Spec:** `docs/superpowers/specs/2026-10-16-line-height-design.md`

## Global Constraints

- 정의: 줄 피치 = 글자 크기 × N/100. 한 줄짜리 문단도 그 높이를 차지하고 `space_before`·`space_after` 는 바깥에 더한다.
- 내장 default 값: heading1–6·code·caption·footnote `130%`, body·quote `160%`, `tables.line_height: 130%`.
- docx 적용 범위: 내장 그릇이면 전부, 사용자 reference.docx 면 `ResolvedTemplate.explicit` 에 있는 값만.
- PDF 에서 값이 없으면 130%.
- 무거부(no-reject): 어떤 입력이든 출력을 만들고 문제는 경고로 알린다. `tests/test_no_reject.py` 가 계속 통과해야 한다.
- 사용자에게 보이는 메시지는 한국어. 새 이벤트 코드는 만들지 않는다.
- 줄바꿈 LF. 커밋 메시지 끝에 저장소 규칙의 Co-Authored-By/Claude-Session 줄을 붙인다.
- 테스트 명령: `uv run python -m pytest ...` (Windows 에서 `uv run pytest` 실행 파일이 가끔 "Failed to canonicalize script path" 로 실패한다).

## Review Focus

1. 문단 안에 인라인 이미지나 수식이 있는 docx — "고정" 줄 간격에서 잘리면 안 된다(Task 5 테스트).
2. `line_height` 를 쓰지 않은 사용자 reference.docx — 그 문서의 줄 간격이 그대로여야 한다(Task 3·4 테스트).
3. 표 종류(`tables.variants.<이름>.line_height`)로 덮어쓴 값 — docx·PDF 모두 그 값이어야 한다(Task 2·4 테스트).
4. 여러 줄 코드 블록 — 한 문단 안 줄바꿈이라도 줄마다 같은 피치여야 한다(Task 2 테스트).
5. 극단 값(50%, 2000%) — 글자가 겹치거나 넓어도 PDF 컴파일이 실패하지 않아야 한다(Task 2 테스트).

---

### Task 1: 템플릿 값과 `tables.line_height` 키

**Files:**
- Modify: `src/mdcast/builtin_templates/default/template.yaml` (elements, tables)
- Test: `tests/test_template_schema.py`

**Interfaces:**
- Produces: 내장 config 의 `elements.<요소>.line_height` 가 모두 문자열 비율, `tables.line_height == "130%"`. 스키마는 기본값의 모양을 기준으로 검증하므로 `tables.line_height` 와 `tables.variants.<이름>.line_height` 가 이 변경만으로 허용된다(`RATIO_KEYS` 에 이미 `line_height` 가 있다).

- [ ] **Step 1: Write the failing test** — `tests/test_template_schema.py` 끝에 추가

```python
def test_builtin_line_heights_are_all_set():
    default = load_builtin_default()
    expected = {f"heading{i}": "130%" for i in range(1, 7)} | {
        "body": "160%", "quote": "160%", "code": "130%", "caption": "130%", "footnote": "130%",
    }
    assert {k: v["line_height"] for k, v in default["elements"].items()} == expected
    assert default["tables"]["line_height"] == "130%"


def test_table_line_height_validates_and_variants_may_override():
    default = load_builtin_default()
    r = new_report()
    clean = validate_against(
        {"tables": {"line_height": "150%", "variants": {"dense": {"line_height": "100%"}}}}, default, r
    )
    assert clean["tables"]["line_height"] == "150%"
    assert clean["tables"]["variants"]["dense"]["line_height"] == "100%"
    assert codes(r) == []
    config = deep_merge(default, {"tables": {"line_height": "-5%"}})
    r = new_report()
    assert sanitize(config, default, r)["tables"]["line_height"] == "130%"
    assert codes(r) == [Codes.TEMPLATE_INVALID]
```

(`load_builtin_default`, `validate_against`, `sanitize`, `deep_merge`, `new_report`, `codes`, `Codes` 는 이 파일이 이미 import/정의하고 있다. 없으면 파일 상단의 import 를 확인해 맞춘다.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_template_schema.py -q -k "line_height"`
Expected: FAIL — 첫 테스트는 heading 값이 `None`, 둘째는 `알 수 없는 템플릿 키 'tables.line_height'` 경고로 `codes(r)` 가 비어 있지 않음.

- [ ] **Step 3: Implement** — `template.yaml` 수정

`elements:` 의 각 줄에서 `line_height: null` 을 다음 값으로 바꾼다(다른 값은 그대로):
- heading1–heading6: `line_height: 130%`
- quote: `line_height: 160%`
- code: `line_height: 130%`
- caption: `line_height: 130%`
- footnote: `line_height: 130%`
- body 는 이미 `160%`.

`tables:` 에 `cell_padding` 다음 줄로 추가:

```yaml
  line_height: 130%
```

- [ ] **Step 4: Run tests**

Run: `uv run python -m pytest tests/test_template_schema.py tests/test_template_resolve.py tests/test_template_inspect.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mdcast/builtin_templates/default/template.yaml tests/test_template_schema.py
git commit -m "feat: built-in line heights for every element and tables.line_height"
```

---

### Task 2: PDF 줄 상자 모델

**Files:**
- Modify: `src/mdcast/writers/pdf/config.py` (`_leading` 삭제, `_element`, `_table`)
- Modify: `src/mdcast/builtin_templates/default/pdf.typ` (머리 주석, `_lines` 추가, `mdcast-table`, `conf`)
- Modify: `tests/helpers.py` (`line_pitch` 추가)
- Modify: `tests/test_pdf_writer.py` (`_line_pitch` → helpers 로 이동, 기존 표 테스트 교체, 새 테스트)
- Modify: `tests/test_pdf_config.py` (`leading` 단언)
- Modify: `docs/superpowers/specs/2026-10-16-line-height-design.md` §6.2 (목록 간격 문장)

**Interfaces:**
- Consumes: Task 1 의 config 값.
- Produces: 설정 JSON `elements.<요소>.line_height: float`(1.6 = 160%), `tables.<이름>.line_height: float`. `elements.<요소>.leading` 은 사라진다. 테스트 도우미 `helpers.line_pitch(data: bytes, needle: str) -> float` (첫 쪽에서 `needle` 로 시작하는 문단의 첫 두 줄 사이 거리, pt).

- [ ] **Step 1: Move the pitch helper** — `tests/helpers.py` 에 추가하고 `tests/test_pdf_writer.py` 의 `_line_pitch` 를 지운다

```python
def line_pitch(data: bytes, needle: str) -> float:
    """Distance (pt) between the first two text lines from ``needle`` on page 1 of a PDF."""
    import pypdfium2 as pdfium

    textpage = pdfium.PdfDocument(data)[0].get_textpage()
    text = textpage.get_text_range()
    tops: list[float] = []
    for i in range(text.index(needle), len(text)):
        if not "가" <= text[i] <= "힣":  # Hangul syllables share one top edge
            continue
        top = round(textpage.get_charbox(i)[3], 1)
        if not tops or abs(top - tops[-1]) > 2:
            tops.append(top)
        if len(tops) == 2:
            return round(tops[0] - tops[1], 2)
    raise AssertionError(f"{needle!r} does not wrap")
```

- [ ] **Step 2: Write the failing tests** — `tests/test_pdf_writer.py`

`from helpers import build, write_template` 를 `from helpers import build, line_pitch, write_template` 로 바꾸고, `test_table_cells_are_single_spaced_while_body_is_wider` 를 지운 뒤 다음을 추가한다.

```python
LONG = "줄 간격을 보기 위해 충분히 긴 문장을 씁니다. " * 6


@pytest.mark.parametrize(
    ("md", "needle", "pitch"),
    [
        (f"본문{LONG}\n", "본문", 11 * 1.6),
        ("- 목록 하나\n- 목록 둘\n", "목록 하나", 11 * 1.6),
        (f"# 제목{LONG}\n", "제목", 16 * 1.3),
        (f"| 칸 |\n|---|\n| 셀{LONG} |\n", "셀", 10 * 1.3),
        ("```\n코드 첫째 줄\n코드 둘째 줄\n```\n", "코드 첫째", 9.5 * 1.3),
    ],
)
def test_line_pitch_is_size_times_line_height(tmp_path, md, needle, pitch):
    assert line_pitch(render(tmp_path, md)[0], needle) == pytest.approx(pitch, abs=0.3)


def test_table_variant_line_height(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\ntables: {variants: {dense: {line_height: 100%}}}\n")
    md = f"<!-- table: dense -->\n\n| 칸 |\n|---|\n| 셀{LONG} |\n"
    assert line_pitch(render(tmp_path, md, str(tpl))[0], "셀") == pytest.approx(10.0, abs=0.3)


@pytest.mark.parametrize("ratio", ["50%", "2000%"])
def test_extreme_line_heights_still_compile(tmp_path, ratio):
    tpl = write_template(tmp_path, "t", f"name: t\nelements: {{body: {{line_height: {ratio}}}}}\n")
    data, _ = render(tmp_path, f"본문{LONG}\n", str(tpl))
    assert data.startswith(b"%PDF")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_pdf_writer.py -q -k "line_pitch or line_height"`
Expected: 본문(17.6)과 극단 값은 통과할 수 있지만, 목록·제목·셀·코드·표 종류 케이스는 FAIL(현재 근사식과 셀 0.65em 때문에 값이 다름). 적어도 셀·제목·표 종류가 실패해야 한다.

- [ ] **Step 4: Implement config** — `src/mdcast/writers/pdf/config.py`

`_leading` 함수를 지우고 그 자리에:

```python
DEFAULT_LINE_HEIGHT = 1.3  # spec 2026-10-16 §7: a PDF element with no line_height


def _line_height(value: Any) -> float:
    """``line_height`` as a ratio of the font size (1.6 = 160%); see spec 2026-10-16 §2."""
    return DEFAULT_LINE_HEIGHT if value is None else round(parse_ratio(value), 4)
```

`_element` 의 `"leading": _leading(look.get("line_height")),` 를 `"line_height": _line_height(look.get("line_height")),` 로, `_table` 의 반환 딕셔너리에 `"line_height": _line_height(s.get("line_height")),` 를 `"cell_padding"` 다음에 추가한다.

`tests/test_pdf_config.py` 의 `assert cfg["elements"]["body"]["leading"] == pytest.approx(0.92)` 를 다음으로 바꾼다:

```python
    assert cfg["elements"]["body"]["line_height"] == pytest.approx(1.6)
    assert "leading" not in cfg["elements"]["body"]
    assert cfg["tables"]["_default"]["line_height"] == pytest.approx(1.3)
```

- [ ] **Step 5: Implement pdf.typ** — `src/mdcast/builtin_templates/default/pdf.typ`

머리 주석의 계약 목록 아래에 다음 두 줄을 추가한다:

```
// Line heights: cfg.elements.<el>.line_height and cfg.tables.<name>.line_height are ratios of the
// font size (1.6 = 160%): every line box is that tall and paragraphs set no extra leading.
```

`_text-args` 정의 바로 아래에 추가:

```
// A line box exactly r em tall (half the extra above, half below), so the line pitch and a
// paragraph's height are r × the font size, like Word's "exact" line spacing.
#let _lines(r) = (
  top-edge: (0.8 + (r - 1) / 2) * 1em,
  bottom-edge: -(0.2 + (r - 1) / 2) * 1em,
)
```

`mdcast-table` 안:
- `set text(size: t.font_size * 1pt)` → `set text(size: t.font_size * 1pt, .._lines(t.line_height))`
- `set par(leading: 0.65em)  // single line spacing in cells, as in the docx tables` 줄을 지운다.

`conf` 안:
- `set text(font: cfg.fonts.body, lang: "ko", .._text-args(el.body))` → `set text(font: cfg.fonts.body, lang: "ko", .._text-args(el.body), .._lines(el.body.line_height))`
- `leading: el.body.leading * 1em,` → `leading: 0em,`
- `show figure.caption: set text(.._text-args(el.caption))` → `show figure.caption: set text(.._text-args(el.caption), .._lines(el.caption.line_height))`
- code 블록의 `text(.._text-args(el.code), it),` → `text(.._text-args(el.code), .._lines(el.code.line_height), it),`
- quote 의 `text(.._text-args(el.quote), it.body),` → `text(.._text-args(el.quote), .._lines(el.quote.line_height), it.body),`
- `show footnote.entry: set text(.._text-args(el.footnote))` → `show footnote.entry: set text(.._text-args(el.footnote), .._lines(el.footnote.line_height))`
- 제목 반복문의 `show heading.where(level: lv): set text(.._text-args(e))` → `show heading.where(level: lv): set text(.._text-args(e), .._lines(e.line_height))`

좁은 목록은 Typst 기본(`list.spacing: auto` → 좁은 목록은 `par.leading` = 0)으로 항목 사이 간격이 0 이 되므로 `list`/`enum` 설정은 바꾸지 않는다. 넓은 목록은 `par.spacing`(본문 space_after)을 쓴다 — docx 의 넓은 목록(Body Text, space_after)과 같다.

스펙 §6.2 의 마지막 문장 "좁은 목록의 항목 사이는 `list.spacing`·`enum.spacing` 을 0 으로 한다." 를 다음으로 바꾼다: "좁은 목록의 항목 사이는 Typst 기본(`spacing: auto` 가 좁은 목록에 `par.leading` = 0 을 씀)으로 0 이 된다. 넓은 목록은 `par.spacing` 을 쓴다."

- [ ] **Step 6: Run tests**

Run: `uv run python -m pytest tests/test_pdf_writer.py tests/test_pdf_config.py tests/test_no_reject.py -q`
Expected: PASS. 코드 블록 케이스가 실패하면 Consolas 에 한글이 없어 대체 글꼴로 측정된 것인지 확인하고(피치는 글꼴과 무관해야 함), 실제 피치를 출력해 원인을 본다 — 단언을 느슨하게 바꾸지 않는다.

- [ ] **Step 7: Commit**

```bash
git add src/mdcast/writers/pdf/config.py src/mdcast/builtin_templates/default/pdf.typ tests/helpers.py tests/test_pdf_writer.py tests/test_pdf_config.py docs/superpowers/specs/2026-10-16-line-height-design.md
git commit -m "feat: PDF line boxes are exactly line_height x font size"
```

---

### Task 3: docx 스타일 "고정" 줄 간격

**Files:**
- Modify: `src/mdcast/writers/docx/xml.py` (`line_twips` 추가)
- Modify: `src/mdcast/writers/docx/styles.py` (`_effective_size_pt`, `apply_look`, `apply_elements`, `tighten_compact`)
- Modify: `src/mdcast/writers/docx/__init__.py` (`write_docx`)
- Test: `tests/test_docx_styles.py`

**Interfaces:**
- Consumes: Task 1 의 config 값.
- Produces: `xml.line_twips(ratio: float, size_pt: float) -> int` (= `round(ratio * size_pt * 20)`). `styles.apply_elements(d, config, used, *, fallback_pt: float)` — 키워드 인자 추가. `styles.tighten_compact(d) -> None`. Task 4·5 가 `line_twips` 를 쓴다.

- [ ] **Step 1: Write the failing tests** — `tests/test_docx_styles.py` 끝에 추가

```python
def _spacing(style) -> tuple[str | None, str | None]:
    ppr = style.element.pPr
    spacing = None if ppr is None else ppr.find(qn("w:spacing"))
    return (None, None) if spacing is None else (spacing.get(qn("w:line")), spacing.get(qn("w:lineRule")))


def test_builtin_styles_use_exact_line_height(tmp_path):
    d, _ = render(tmp_path, "# 제목\n\n본문\n\nTable: 캡션\n\n| a |\n|---|\n| 1 |\n")
    styles = styles_by_name(d)
    assert _spacing(styles["Body Text"]) == ("352", "exact")  # 11pt × 160% × 20
    assert _spacing(styles["First Paragraph"]) == ("352", "exact")
    assert _spacing(styles["Heading 1"]) == ("416", "exact")  # 16pt × 130%
    assert _spacing(styles["Table Caption"]) == ("247", "exact")  # 9.5pt × 130%
    assert _spacing(styles["Footnote Text"]) == ("234", "exact")  # 9pt × 130%


def test_builtin_compact_has_no_gaps_and_inherits_the_body_line(tmp_path):
    d, _ = render(tmp_path, "- 하나\n- 둘\n")
    compact = styles_by_name(d)["Compact"]
    assert compact.paragraph_format.space_before == 0 and compact.paragraph_format.space_after == 0
    assert _spacing(compact)[0] is None  # line height comes from Body Text


def _size_pt(d, style) -> float:
    """Effective font size: the style, its bases, then the document defaults (as the writer does)."""
    while style is not None:
        if style.font.size is not None:
            return style.font.size.pt
        style = style.base_style
    sz = d.styles.element.find(f"{qn('w:docDefaults')}/{qn('w:rPrDefault')}/{qn('w:rPr')}/{qn('w:sz')}")
    return int(sz.get(qn("w:val"))) / 2


def test_custom_container_sets_only_the_written_line_heights(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nelements: {body: {line_height: 150%, size: 12pt}, heading1: {line_height: 120%}}\n")
    make_reference_docx(tpl / "reference.docx")
    d, _ = render(tmp_path, "# 제목\n\n본문\n", str(tpl))
    styles = styles_by_name(d)
    assert _spacing(styles["Body Text"]) == ("360", "exact")  # 12pt × 150%
    h1 = styles["Heading 1"]
    assert _spacing(h1) == (str(round(1.2 * _size_pt(d, h1) * 20)), "exact")  # the reference's own size
    assert _spacing(styles["Heading 2"])[1] != "exact"  # not written: the reference's own
    assert styles["Compact"].paragraph_format.space_after != 0  # tightening is built-in only
```

(`styles_by_name`, `render`, `qn`, `write_template`, `make_reference_docx` 는 이 파일에 이미 있다.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_docx_styles.py -q -k "exact or compact or written_line"`
Expected: FAIL — 현재는 `line_spacing = 1.6`(배수, `lineRule="auto"`, `line="384"`).

- [ ] **Step 3: Implement**

`src/mdcast/writers/docx/xml.py` 의 `mm_to_twips` 아래에:

```python
def line_twips(ratio: float, size_pt: float) -> int:
    """Exact line height in twips for ``line_height`` (a ratio of the font size, spec 2026-10-16 §2)."""
    return round(ratio * size_pt * 20)
```

`src/mdcast/writers/docx/styles.py`:
- import 를 `from mdcast.writers.docx.xml import PPR_ORDER, line_twips, upsert` 로 바꾼다.
- `_by_name` 아래에 추가:

```python
def _effective_size_pt(d, style) -> float | None:
    """The style's font size in pt, following basedOn and then the document defaults."""
    seen: set[str] = set()
    while style is not None and style.name not in seen:
        seen.add(style.name)
        if style.font.size is not None:
            return style.font.size.pt
        style = style.base_style
    sz = d.styles.element.find(f"{qn('w:docDefaults')}/{qn('w:rPrDefault')}/{qn('w:rPr')}/{qn('w:sz')}")
    return None if sz is None else int(sz.get(qn("w:val"))) / 2


def tighten_compact(d) -> None:
    """Tight list items sit at the body's line height with no gaps, as in the PDF (built-in only)."""
    style = _by_name(d).get("Compact")
    if style is not None:
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after = Pt(0)
```

- `apply_look` 시그니처를 `def apply_look(style, look: dict[str, Any], *, character_only: bool = False, size_pt: float | None = None) -> None:` 로 바꾸고, 다음 블록을

```python
    if look.get("line_height") is not None:
        fmt.line_spacing = parse_ratio(look["line_height"])
```

다음으로 바꾼다:

```python
    if look.get("line_height") is not None and size_pt is not None:
        # "exact": Word's "multiple" scales the font's own single line (1.73 × size for Malgun Gothic)
        spacing = upsert(style.element.get_or_add_pPr(), "w:spacing", PPR_ORDER)
        spacing.set(qn("w:line"), str(line_twips(parse_ratio(look["line_height"]), size_pt)))
        spacing.set(qn("w:lineRule"), "exact")
```

- `apply_elements` 시그니처를 `def apply_elements(d, config: dict[str, Any], used: dict[str, list[str]], *, fallback_pt: float) -> None:` 로 바꾸고, 반복문의 `apply_look(style, look, character_only=name in CHARACTER_ONLY)` 를 다음으로 바꾼다:

```python
            size_pt = parse_pt(look["size"]) if look.get("size") is not None else _effective_size_pt(d, style)
            apply_look(style, look, character_only=name in CHARACTER_ONLY, size_pt=size_pt or fallback_pt)
```

`src/mdcast/writers/docx/__init__.py`:
- import 에 `tighten_compact` 를 추가하고 `from mdcast.units import parse_pt` 를 추가한다.
- `write_docx` 에서:

```python
    if container_source != "custom":
        disable_autospace(d)
        tighten_compact(d)
    apply_page(d, looks)
    used = remap_styles(d, config, ctx.report)
    apply_elements(d, looks, used, fallback_pt=parse_pt(config["elements"]["body"]["size"]))
```

- [ ] **Step 4: Run tests**

Run: `uv run python -m pytest tests/test_docx_styles.py tests/test_docx_numbering.py tests/test_docx_headers.py tests/test_no_reject.py -q`
Expected: PASS. 기존 `test_default_element_looks` 의 `assert body.paragraph_format.line_spacing == 1.6` 은 이제 실패한다 — 그 줄을 `assert _spacing(body) == ("352", "exact")` 로 바꾼다(`_spacing` 은 같은 파일 아래쪽에 정의되므로 모듈 수준이라 사용 가능).

- [ ] **Step 5: Commit**

```bash
git add src/mdcast/writers/docx/xml.py src/mdcast/writers/docx/styles.py src/mdcast/writers/docx/__init__.py tests/test_docx_styles.py
git commit -m "feat: docx styles use exact line height = line_height x font size"
```

---

### Task 4: docx 표 셀 줄 높이

**Files:**
- Modify: `src/mdcast/writers/docx/tables.py` (`_single_spaced` → `_cell_line_height`, `apply_tables` 루프)
- Test: `tests/test_docx_tables.py`

**Interfaces:**
- Consumes: Task 3 의 `xml.line_twips`. Task 1 의 `tables.line_height`.
- Produces: 셀 안 모든 문단에 직접 서식 `w:spacing before=0 after=0 line=<twips> lineRule=exact`. Task 5 가 이 값을 읽어 이미지·수식 문단만 `atLeast` 로 바꾼다.

- [ ] **Step 1: Write the failing tests** — `tests/test_docx_tables.py`

`cell_line_spacings` 도우미를 다음으로 바꾸고(네 값 반환), 기존 `test_builtin_cells_use_single_line_spacing` 과 `test_custom_container_cells_keep_their_spacing` 를 지운 뒤 아래를 추가한다.

```python
def cell_line_spacings(data: bytes) -> list[tuple[str | None, ...]]:
    body = part(data, "word/document.xml").find(qn("w:body"))
    out = []
    for p in body.iter(qn("w:p")):
        if next((a for a in p.iterancestors() if a.tag == qn("w:tc")), None) is None:
            continue
        ppr = p.find(qn("w:pPr"))
        spacing = None if ppr is None else ppr.find(qn("w:spacing"))
        keys = ("line", "lineRule", "before", "after")
        out.append(tuple(None if spacing is None else spacing.get(qn(f"w:{k}")) for k in keys))
    return out


TABLE = "| a | b |\n|---|---|\n| 1 | 2 |\n"


def test_builtin_cells_use_exact_table_line_height(tmp_path):
    assert cell_line_spacings(render(tmp_path, TABLE)) == [("260", "exact", "0", "0")] * 4  # 10pt × 130%


def test_variant_line_height_overrides_the_cells(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\ntables: {variants: {dense: {line_height: 100%}}}\n")
    data = render(tmp_path, "<!-- table: dense -->\n\n" + TABLE, str(tpl))
    assert cell_line_spacings(data) == [("200", "exact", "0", "0")] * 4


def test_custom_container_cells_change_only_when_written(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\n")
    make_reference_docx(tpl / "reference.docx")
    assert cell_line_spacings(render(tmp_path, TABLE, str(tpl))) == [(None, None, None, None)] * 4
    tpl2 = write_template(tmp_path, "t2", "name: t2\ntables: {line_height: 150%}\n")
    make_reference_docx(tpl2 / "reference.docx")
    assert cell_line_spacings(render(tmp_path, TABLE, str(tpl2))) == [("300", "exact", "0", "0")] * 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_docx_tables.py -q -k "line_height or written"`
Expected: FAIL — 현재 셀은 `("240", "auto", None, None)`.

- [ ] **Step 3: Implement** — `src/mdcast/writers/docx/tables.py`

import 에 `line_twips` 를 추가하고 `from mdcast.units import normalize_color, parse_length_mm, parse_pt` 를 `..., parse_pt, parse_ratio` 로 바꾼다. `_single_spaced` 함수 전체를 다음으로 바꾼다:

```python
def _cell_line_height(tbl, twips: int) -> None:
    """Exact line height and no paragraph gaps in the cells, as in the PDF's tables.

    Direct formatting: the cells' paragraph style (Compact, based on the body) would beat a
    table style's spacing.
    """
    for p in tbl.iter(qn("w:p")):
        ppr = p.find(qn("w:pPr"))
        if ppr is None:
            ppr = OxmlElement("w:pPr")
            p.insert(0, ppr)
        upsert(ppr, "w:spacing", PPR_ORDER, before=0, after=0, line=twips, lineRule="exact")
```

`apply_tables` 루프의

```python
        if explicit is None:
            _single_spaced(tbl)
```

를 다음으로 바꾼다(`look` 은 내장 그릇이면 전체 설정, 사용자 그릇이면 명시값+종류 덮어쓰기다):

```python
        if look.get("line_height") is not None:
            _cell_line_height(tbl, line_twips(parse_ratio(look["line_height"]), parse_pt(s["font_size"])))
```

- [ ] **Step 4: Run tests**

Run: `uv run python -m pytest tests/test_docx_tables.py tests/test_no_reject.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mdcast/writers/docx/tables.py tests/test_docx_tables.py
git commit -m "feat: docx table cells use exact tables.line_height"
```

---

### Task 5: 이미지·수식이 든 문단은 `atLeast`

**Files:**
- Create: `src/mdcast/writers/docx/inline.py`
- Modify: `src/mdcast/writers/docx/__init__.py` (`write_docx` 끝에서 호출)
- Test: `tests/test_docx_inline.py` (새 파일)

**Interfaces:**
- Consumes: Task 3·4 가 쓴 `lineRule="exact"` (스타일 또는 문단 직접 서식).
- Produces: `inline.loosen_inline_objects(d) -> None`. 본문과 각주·미주에서 `w:drawing`·`w:pict`·`w:object`·`m:oMath` 가 든 문단 중, 실효 줄 간격이 `exact` 인 문단에 같은 `w:line` 값을 `lineRule="atLeast"` 로 직접 서식으로 준다. 실효 값이 `exact` 가 아니면(사용자 그릇에서 줄 높이를 안 쓴 경우) 건드리지 않는다.

- [ ] **Step 1: Write the failing tests** — `tests/test_docx_inline.py`

```python
import io
import zipfile

from docx.oxml.ns import qn
from helpers import build, tiny_png
from lxml import etree

from mdcast.types import Format
from mdcast.writers.docx import write_docx


def render(tmp_path, md):
    doc, ctx = build(tmp_path, md, Format.DOCX)
    return write_docx(doc, ctx)


def spacing_by_text(data: bytes, part: str) -> dict[str, tuple[str | None, str | None]]:
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read(part))
    out = {}
    for p in root.iter(qn("w:p")):
        text = "".join(t.text or "" for t in p.iter(qn("w:t"))).strip()
        if not text:
            continue
        ppr = p.find(qn("w:pPr"))
        spacing = None if ppr is None else ppr.find(qn("w:spacing"))
        out[text] = (None, None) if spacing is None else (spacing.get(qn("w:line")), spacing.get(qn("w:lineRule")))
    return out


def test_inline_image_paragraph_grows_instead_of_clipping(tmp_path):
    (tmp_path / "a.png").write_bytes(tiny_png())
    found = spacing_by_text(render(tmp_path, "앞 ![](a.png){width=3cm} 뒤\n\n그냥 문단\n"), "word/document.xml")
    assert found["앞  뒤"] == ("352", "atLeast")
    assert found["그냥 문단"] == (None, None)  # the style's exact line applies


def test_inline_math_paragraph_grows(tmp_path):
    found = spacing_by_text(render(tmp_path, "식 $\\frac{a}{b}$ 끝\n"), "word/document.xml")
    assert found["식  끝"] == ("352", "atLeast")


def test_math_in_a_table_cell_grows(tmp_path):
    found = spacing_by_text(render(tmp_path, "| 칸 |\n|---|\n| 셀 $\\frac{a}{b}$ |\n"), "word/document.xml")
    assert found["셀"] == ("260", "atLeast")


def test_math_in_a_footnote_grows(tmp_path):
    found = spacing_by_text(render(tmp_path, "본문[^1]\n\n[^1]: 각주 $\\frac{a}{b}$\n"), "word/footnotes.xml")
    assert found["각주"] == ("234", "atLeast")  # Footnote Text: 9pt × 130%
```

(키 문자열은 `w:t` 텍스트만 이은 값이다. 이미지·수식 자리는 텍스트가 없어 공백 두 칸이 남는다. 실제 키가 다르면 테스트 실패 메시지의 dict 를 보고 키만 맞춘다 — 기대 spacing 값은 바꾸지 않는다.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_docx_inline.py -q`
Expected: FAIL — 이미지·수식 문단에 직접 spacing 이 없음(`(None, None)`), 셀은 `("260", "exact")`.

- [ ] **Step 3: Implement** — `src/mdcast/writers/docx/inline.py`

```python
from __future__ import annotations

from typing import Any

from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

from mdcast.writers.docx.xml import PPR_ORDER, upsert

_MATH = "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"
_OBJECTS = (qn("w:drawing"), qn("w:pict"), qn("w:object"), _MATH)


def _exact_in_style_chain(style_id: str | None, styles: dict[str, Any]) -> str | None:
    seen: set[str] = set()
    while style_id is not None and style_id not in seen and style_id in styles:
        seen.add(style_id)
        element = styles[style_id]
        spacing = element.find(f"{qn('w:pPr')}/{qn('w:spacing')}")
        if spacing is not None and spacing.get(qn("w:line")) is not None:
            return spacing.get(qn("w:line")) if spacing.get(qn("w:lineRule")) == "exact" else None
        based = element.find(qn("w:basedOn"))
        style_id = None if based is None else based.get(qn("w:val"))
    return None


def _exact_line(p, styles: dict[str, Any], default_id: str | None) -> str | None:
    """The paragraph's exact line height in twips, or None when its line rule is not exact."""
    ppr = p.find(qn("w:pPr"))
    if ppr is not None:
        spacing = ppr.find(qn("w:spacing"))
        if spacing is not None and spacing.get(qn("w:line")) is not None:
            return spacing.get(qn("w:line")) if spacing.get(qn("w:lineRule")) == "exact" else None
        p_style = ppr.find(qn("w:pStyle"))
        if p_style is not None:
            return _exact_in_style_chain(p_style.get(qn("w:val")), styles)
    return _exact_in_style_chain(default_id, styles)


def _loosen(root, styles: dict[str, Any], default_id: str | None) -> bool:
    changed = False
    for p in root.iter(qn("w:p")):
        if not any(next(p.iter(tag), None) is not None for tag in _OBJECTS):
            continue
        line = _exact_line(p, styles, default_id)
        if line is None:
            continue
        ppr = p.find(qn("w:pPr"))
        if ppr is None:
            ppr = OxmlElement("w:pPr")
            p.insert(0, ppr)
        upsert(ppr, "w:spacing", PPR_ORDER, line=line, lineRule="atLeast")
        changed = True
    return changed


def loosen_inline_objects(d) -> None:
    """Let paragraphs holding images or equations grow: an "exact" line would clip them."""
    styles = {s.get(qn("w:styleId")): s for s in d.styles.element.findall(qn("w:style"))}
    default = next(
        (s for s in styles.values() if s.get(qn("w:type")) == "paragraph" and s.get(qn("w:default")) in ("1", "true")),
        None,
    )
    default_id = None if default is None else default.get(qn("w:styleId"))
    _loosen(d.element.body, styles, default_id)
    for rel in d.part.rels.values():
        if rel.is_external or rel.reltype not in (RT.FOOTNOTES, RT.ENDNOTES):
            continue
        part = rel.target_part
        if hasattr(part, "element"):
            _loosen(part.element, styles, default_id)
            continue
        # python-docx loads the notes as plain parts: edit the XML and put it back
        root = etree.fromstring(part.blob)
        if _loosen(root, styles, default_id):
            part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
```

notes 의 `root` 는 python-docx 요소가 아닌 순수 lxml 트리지만, `OxmlElement` 도 lxml 요소라 거기에 넣어 직렬화해도 된다.

`src/mdcast/writers/docx/__init__.py`: `from mdcast.writers.docx.inline import loosen_inline_objects` 를 추가하고, `write_docx` 의 `apply_tables(...)` 다음 줄에 `loosen_inline_objects(d)` 를 넣는다(표 셀 값까지 정해진 뒤여야 한다).

- [ ] **Step 4: Run tests**

Run: `uv run python -m pytest tests/test_docx_inline.py tests/test_docx_tables.py tests/test_docx_styles.py tests/test_images.py tests/test_no_reject.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mdcast/writers/docx/inline.py src/mdcast/writers/docx/__init__.py tests/test_docx_inline.py
git commit -m "feat: docx paragraphs with images or equations use at-least line height"
```

---

### Task 6: Word 대조 테스트, 문서, 시각 골든

**Files:**
- Modify: `tests/conftest.py` (`--run-word`)
- Modify: `pyproject.toml` (`markers` 에 `word`)
- Create: `tests/test_word_parity.py`
- Modify: `README.md` (테스트 명령, 템플릿 줄 높이 설명, 미룬 항목의 S1 줄 삭제)
- Modify: `tests/golden/pdf/korean-report-p1.png` (재생성, 사용자 승인 후)
- Modify: `docs/superpowers/spikes/2026-10-15-m0-results.md` (줄 간격 차이 해결 기록)

**Interfaces:**
- Consumes: Task 2 의 `helpers.line_pitch`, Task 2–5 의 writer 동작.

- [ ] **Step 1: Add the opt-in option** — `tests/conftest.py` 전체를 다음으로 바꾼다

```python
import pytest

OPT_IN = {"visual": "--run-visual", "word": "--run-word"}


def pytest_addoption(parser):
    parser.addoption("--run-visual", action="store_true", help="run visual golden-image tests")
    parser.addoption("--run-word", action="store_true", help="run Microsoft Word parity tests (Windows + Word)")


def pytest_collection_modifyitems(config, items):
    for marker, option in OPT_IN.items():
        if config.getoption(option):
            continue
        skip = pytest.mark.skip(reason=f"{marker} test: pass {option}")
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)
```

`pyproject.toml` 의 `markers = [` 목록에 추가:

```toml
  "word: Microsoft Word export compared with the PDF writer (run with --run-word)",
```

- [ ] **Step 2: Write the parity test** — `tests/test_word_parity.py`

```python
import sys

import pytest
from helpers import build, line_pitch

from mdcast.types import Format
from mdcast.writers.docx import write_docx
from mdcast.writers.pdf import write_pdf

pytestmark = [pytest.mark.word, pytest.mark.skipif(sys.platform != "win32", reason="needs Microsoft Word")]

LONG = "줄 간격을 보기 위해 충분히 긴 문장을 씁니다. " * 6
MD = f"본문{LONG}\n\n- 목록 하나\n- 목록 둘\n\n# 제목{LONG}\n\n| 칸 |\n|---|\n| 셀{LONG} |\n"


def _word_pdf(docx_path, pdf_path) -> bytes:
    win32 = pytest.importorskip("win32com.client")
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    try:
        document = word.Documents.Open(str(docx_path), ReadOnly=True)
        document.ExportAsFixedFormat(str(pdf_path), 17)  # wdExportFormatPDF
        document.Close(False)
    finally:
        word.Quit()
    return pdf_path.read_bytes()


@pytest.fixture(scope="module")
def pdfs(tmp_path_factory):
    root = tmp_path_factory.mktemp("parity")
    doc, ctx = build(root, MD, Format.DOCX)
    docx_path = root / "out.docx"
    docx_path.write_bytes(write_docx(doc, ctx))
    word = _word_pdf(docx_path, root / "word.pdf")
    doc, ctx = build(root, MD, Format.PDF)
    return word, write_pdf(doc, ctx)


@pytest.mark.parametrize("needle", ["본문", "목록 하나", "제목", "셀"])
def test_word_and_pdf_line_pitch_match(pdfs, needle):
    word, typst = pdfs
    assert line_pitch(word, needle) == pytest.approx(line_pitch(typst, needle), rel=0.05)
```

- [ ] **Step 3: Run it**

Run: `uv run python -m pytest tests/test_word_parity.py --run-word -q`
Expected: 4 passed. (에이전트 셸이 샌드박스 안이면 Word COM 이 `CO_E_SERVER_EXEC_FAILURE` 로 실패한다 — 샌드박스 밖에서 실행한다.) 실패하면 두 값을 출력해 차이를 보고 원인을 찾는다. 허용 오차를 넓히지 않는다. 옵션 없이 `uv run python -m pytest tests/test_word_parity.py -q` 를 돌려 4 skipped 인지도 본다.

- [ ] **Step 4: README** — `README.md`

`## 테스트` 코드 블록에 한 줄 추가:

```
    uv run pytest tests/test_word_parity.py --run-word   # Word 로 내보낸 docx 와 PDF 의 줄 간격 비교 (Windows + Word, 선택)
```

`## M1 에서 미룬 항목` 앞에 새 절 추가:

```markdown
## 템플릿: 줄 높이

`line_height: 160%` 는 그 요소의 줄 하나가 글자 크기의 1.6배 높이를 차지한다는 뜻입니다(한글의 "글자에 따라 160%" 와 같음). 문단 앞뒤 간격은 그 바깥에 더합니다.

- `elements.<요소>.line_height`: 제목·본문·인용·코드·캡션·각주. 내장 템플릿은 모두 값을 가집니다(본문·인용 160%, 나머지 130%).
- `tables.line_height`: 표 셀 안 줄 높이(기본 130%, 글자 크기는 `tables.font_size`). 표 종류(`tables.variants.<이름>`)에서 덮어쓸 수 있습니다.
- docx 는 Word 의 "고정" 줄 간격으로 씁니다. 이미지나 수식이 든 문단만 "최소" 로 두어 잘리지 않게 합니다.
- 사용자 reference.docx 를 쓰면 yaml 에 적은 줄 높이만 적용하고, 적지 않은 요소는 그 문서의 설정을 따릅니다. 이때 PDF 는 상속받은 값(내장 기본값)을 쓰므로, 두 형식을 맞추려면 값을 적어 주세요.
- 사용자 `pdf.typ` 는 `cfg.elements.<요소>.line_height`, `cfg.tables.<이름>.line_height` (비율, 1.6 = 160%)를 읽습니다. 예전의 `leading` 키는 없어졌습니다.
```

`## M1 에서 미룬 항목` 목록에서 `- hwpx 스파이크 S1 실행은 보류 중이며 M2 이전에 수행해야 함` 줄을 지운다(2026-10-16 실행, PASS).

- [ ] **Step 5: Full verification**

Run: `uv run ruff check src tests` → All checks passed
Run: `uv run python -m pytest -q` → 모두 통과(+ visual·word 는 skip)
Run: `uv run python -m pytest tests/test_visual.py --run-visual -q`
Expected: FAIL — 1쪽 머리말·제목·목록 위치가 바뀌었으므로 골든과 다르다. 이것이 정상이다.

- [ ] **Step 6: Regenerate the golden and get the user's approval**

Run: `MDCAST_UPDATE_GOLDEN=1 uv run python -m pytest tests/test_visual.py --run-visual -q` (PowerShell: `$env:MDCAST_UPDATE_GOLDEN='1'; uv run python -m pytest tests/test_visual.py --run-visual -q; Remove-Item Env:MDCAST_UPDATE_GOLDEN`)

새 `tests/golden/pdf/korean-report-p1.png` 를 열어 확인하고, **사용자에게 보여 주고 승인을 받는다.** 확인할 점: 머리말 오른쪽 `2026년 4분기 사업계획` 과 그 아래 선, 1쪽에 `Ⅰ.` 없이 `추진 배경` 과 □ ○ 목록만, 목록 줄 사이가 본문 160% 피치, 꼬리말 `1 / 3`. 승인 전에는 골든을 커밋하지 않는다.

그다음 `uv run python -m pytest tests/test_e2e.py -q` 와 `uv run python scripts/render_pages.py .test-output/e2e/korean-report.docx .test-output/e2e/korean-report.pdf` 로 docx·pdf 1–2쪽을 나란히 놓고 줄 간격이 같아 보이는지 확인한다(샌드박스 밖).

- [ ] **Step 7: Record and commit**

`docs/superpowers/spikes/2026-10-15-m0-results.md` 의 "남은 줄 간격 차이의 원인" 항목 끝에 한 문장 추가: "2026-10-16 `line_height` 의미 통일(스펙 `2026-10-16-line-height-design.md`)로 해결 — docx 는 '고정' 줄 간격, PDF 는 줄 상자 모델, `--run-word` 테스트가 두 형식의 피치를 5% 안으로 지킨다."

```bash
git add tests/conftest.py pyproject.toml tests/test_word_parity.py README.md tests/golden/pdf/korean-report-p1.png docs/superpowers/spikes/2026-10-15-m0-results.md
git commit -m "test: Word parity for line pitch; docs for line_height; new PDF golden"
```
