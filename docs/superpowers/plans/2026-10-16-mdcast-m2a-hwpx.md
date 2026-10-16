# M2a hwpx 내보내기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** MD → hwpx 출력. 한글 빈 문서를 그릇으로 재사용하고, 같은 template.yaml 로 docx·pdf 와 같은 모양을 낸다 (M2a 범위: 표·이미지·각주는 낮춰 출력).

**Architecture:** 독립 패키지 `src/mdcast/hwpx/`(lxml + panflute 만, mdcast 의 다른 모듈 import 금지)가 pandoc AST 와 `Settings` 를 받아 그릇(reference.hwpx)의 header.xml 에 모양을 추가하고 section0.xml 본문을 새로 쓴다. 어댑터 `src/mdcast/writers/hwpx.py` 가 템플릿 설정을 `Settings` 로 바꾸고 알림을 리포트 이벤트로 옮긴다. 한글 COM 은 검증(`--run-hangul`)에만 쓴다.

**Tech Stack:** Python 3.11+, lxml, panflute 2.3.1, pypandoc(기존), pytest, pypdfium2(테스트), pywin32 + 한글(로컬 검증 전용).

**Spec:** `docs/superpowers/specs/2026-10-16-mdcast-m2a-hwpx-design.md` (부록 A 의 측정값이 XML 표현의 근거다). 상위: `docs/superpowers/specs/2026-10-15-mdcast-design.md`, 줄 높이: `docs/superpowers/specs/2026-10-16-line-height-design.md`.

## Global Constraints

- `src/mdcast/hwpx/` 의 모듈은 `mdcast.hwpx.*` 외의 mdcast 모듈을 import 하지 않는다 (상위 스펙 §2). 의존성 추가 없음 (lxml, panflute 는 이미 있음).
- 길이 단위 (부록 A-4, A-12): paraPr `margin`(left·right·intent·prev·next)과 tabItem `pos` 는 **HWPUNIT × 2**, `pagePr` 크기·여백, paraPr `border offset*`, subList `textWidth/textHeight` 는 HWPUNIT 그대로. 이 변환은 `mdcast.hwpx.units` 의 함수로만 한다.
- 사용자에게 보이는 메시지(리포트, 예외 메시지)는 한국어.
- 거부 금지: 어떤 입력·템플릿이든 hwpx 파일을 만든다. 깨진 사용자 그릇은 `TEMPLATE_INVALID`(warn) 후 내장 그릇.
- 사용자 그릇(reference.hwpx)에는 yaml 에 적힌 값(`ResolvedTemplate.explicit`)만 반영, 내장 그릇에는 전체 + 빈 값은 PDF 값(spec §4.3).
- 공개 저장소: reference.hwpx 에 작성자·날짜 메타데이터를 남기지 않는다. 사내 호스트 이름을 코드·문서에 쓰지 않는다.
- 테스트 명령: `uv run python -m pytest -q` (Windows 에서 `uv run pytest` 는 경로 오류가 날 수 있음). ruff line-length 100.
- 한글 COM 실행은 `dangerouslyDisableSandbox: true` 가 필요하고, 보안 모듈을 등록하지 않았으면 사용자가 "접근 허용" 대화상자를 눌러야 한다. 실행 전에 사용자에게 알린다.
- 커밋 트레일러:
  ```
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_017w5xcKPkVVNsSkDtLjNZni
  ```

## Review Focus

1. 다른 한글 버전이 만든 사용자 reference.hwpx: paraPr 의 `hh:margin`·`hh:lineSpacing` 이 `hp:switch/hp:case|default` 안에 있을 수 있다 → 모든 사본을 고쳐야 한다 (Task 2 테스트 `test_margin_inside_switch_is_updated`).
2. 빈 문서·머리말만 있는 문서: 문단이 하나도 없어도 secPr 를 담은 문단 하나가 있어야 한글이 연다 (Task 8 `test_empty_document_keeps_the_section_settings`).
3. 붙여 넣은 글에 XML 에 쓸 수 없는 제어 문자(`\x0b`, `\x01` …): 버려야 하고, 남으면 파일이 깨진다 (Task 4 `test_control_characters_are_dropped`).
4. 중첩 구조: 코드 블록으로 시작하는 목록 항목, 인용 안 목록 안 목록 — 기호 문단과 들여쓰기가 어긋나지 않아야 한다 (Task 5 `test_item_starting_with_code_block`, `test_list_inside_quote`).
5. 링크 URL 의 `:` `;` `\` 와 한글: `Command` escape 가 빠지면 한글이 필드를 잘못 나눈다 (Task 4 `test_link_field`).

## File Structure

| 파일 | 책임 |
|---|---|
| `src/mdcast/hwpx/__init__.py` | 공개 API 재수출 (`write`, `Settings`, `Look`, …) |
| `src/mdcast/hwpx/units.py` | HWPUNIT / 문단 단위 변환 |
| `src/mdcast/hwpx/look.py` | 입력 값 객체(`Look`, `PageSetup`, `Slots`, `PageNumber`, `Metadata`, `Settings`)와 `Notice`/`Notices` |
| `src/mdcast/hwpx/container.py` | zip 패키지 읽기·쓰기, `ContainerError` |
| `src/mdcast/hwpx/header.py` | header.xml 편집 (`Header`, `CharSpec`, `ParaSpec`) |
| `src/mdcast/hwpx/shapes.py` | 요소별 스타일·문단 모양·글자 모양 (`Shape`, `build_shapes`) |
| `src/mdcast/hwpx/section.py` | AST → 문단 (`SectionWriter`, `Paragraph`, `append_text`) |
| `src/mdcast/hwpx/page.py` | 쪽 설정, 여백 나누기, 머리말·꼬리말, 첫 문단 조립 (`assemble`, `layout`) |
| `src/mdcast/hwpx/meta.py` | content.hpf 메타데이터, 미리보기 글, 커서, 추가 구역 제거 |
| `src/mdcast/hwpx/writer.py` | `write()` 진입점 |
| `src/mdcast/writers/generator.py` | 생성 정보 키-값 (`generator_values`, docx 와 공유) |
| `src/mdcast/writers/hwpx.py` | 어댑터 `write_hwpx` |
| `src/mdcast/builtin_templates/default/reference.hwpx` | 내장 그릇 (한글 빈 문서) |
| `scripts/make_reference_hwpx.py` | 내장 그릇 만들기 (한글 COM 또는 `--from`) |
| `tests/test_hwpx_container.py`, `test_hwpx_header.py`, `test_hwpx_shapes.py`, `test_hwpx_section.py`, `test_hwpx_lists.py`, `test_hwpx_degraded.py`, `test_hwpx_page.py`, `test_hwpx_write.py`, `test_writer_hwpx.py`, `test_hangul.py` | 테스트 |

---

### Task 1: 단위, 값 객체, 패키지, 내장 그릇

**Files:**
- Create: `src/mdcast/hwpx/__init__.py`, `src/mdcast/hwpx/units.py`, `src/mdcast/hwpx/look.py`, `src/mdcast/hwpx/container.py`
- Create: `scripts/make_reference_hwpx.py`, `src/mdcast/builtin_templates/default/reference.hwpx` (생성물)
- Modify: `src/mdcast/templates/resolve.py:52-56` (`builtin_container`)
- Modify: `tests/test_template_resolve.py:209-215`
- Modify: `tests/helpers.py` (hwpx 도우미 추가)
- Test: `tests/test_hwpx_container.py`

**Interfaces:**
- Produces:
  - `units.hwpunit(mm: float) -> int`, `units.hwpunit_pt(pt: float) -> int`, `units.para_unit(mm: float) -> int`, `units.para_unit_pt(pt: float) -> int`
  - `look.Look`, `look.PageNumber(kind)`, `look.Piece = str | PageNumber`, `look.Slots(left, center, right, line)`, `look.PageSetup(width, height, landscape, top, bottom, left, right)`, `look.Metadata(title, author, keywords, created, extra)`, `look.Notice(kind, element, message)`, `look.Notices.add(kind, element, message)` / `.items`, `look.Settings(...)`, `look.ELEMENTS`
  - `container.ContainerError`, `container.Package.read(data) -> Package`, `.names()`, `.get(name)`, `.set(name, data)`, `.remove(name)`, `.xml(name) -> _Element`, `.set_xml(name, root)`, `.write() -> bytes`
  - `ResolvedTemplate.builtin_container("hwpx").path` = 내장 reference.hwpx
  - `tests/helpers.py`: `HWPX_NS`, `builtin_hwpx() -> bytes`, `hwpx_integrity(data) -> dict[str, _Element]`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_hwpx_container.py`

```python
import importlib.util
import io
import zipfile
from pathlib import Path

import pytest
from helpers import HWPX_NS, builtin_hwpx, hwpx_integrity

from mdcast.hwpx.container import ContainerError, Package
from mdcast.hwpx.units import hwpunit, hwpunit_pt, para_unit, para_unit_pt
from mdcast.report import Report
from mdcast.templates import resolve_template
from mdcast.types import Format

ROOT = Path(__file__).resolve().parents[1]
OPF_META = f"{{{HWPX_NS['opf']}}}meta"


def test_units_follow_hangul_measurements():
    assert hwpunit(15.0) == 4252  # page margins: plain HWPUNIT (appendix A-9)
    assert hwpunit_pt(10) == 1000
    assert para_unit(5.0) == 2835  # paragraph margins and tab positions: twice (A-4, A-12)
    assert para_unit_pt(10) == 2000


def test_builtin_container_is_sound_and_anonymous():
    parts = hwpx_integrity(builtin_hwpx())
    values = {m.get("name"): (m.text or "") for m in parts["Contents/content.hpf"].iter(OPF_META)}
    assert values.get("creator", "") == ""
    assert values.get("CreatedDate", "") == ""


def test_builtin_container_path(tmp_path):
    tpl = resolve_template(None, cwd=tmp_path, home=tmp_path, report=Report("d.md", Format.MD))
    path = tpl.builtin_container("hwpx").path
    assert path.name == "reference.hwpx" and path.is_file()


def test_round_trip_keeps_entries():
    package = Package.read(builtin_hwpx())
    out = Package.read(package.write())
    assert out.names()[0] == "mimetype"
    assert sorted(out.names()) == sorted(package.names())
    hwpx_integrity(package.write())


def test_mimetype_is_written_first_and_stored():
    package = Package.read(builtin_hwpx())
    data = package.get("mimetype")
    package.remove("mimetype")
    package.set("mimetype", data)
    assert package.names()[-1] == "mimetype"
    first = zipfile.ZipFile(io.BytesIO(package.write())).infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED


@pytest.mark.parametrize("data", [b"not a zip", b""])
def test_unreadable_container(data):
    with pytest.raises(ContainerError):
        Package.read(data)


def test_container_missing_section():
    package = Package.read(builtin_hwpx())
    package.remove("Contents/section0.xml")
    with pytest.raises(ContainerError, match="section0"):
        Package.read(package.write())


def test_container_with_broken_xml():
    package = Package.read(builtin_hwpx())
    package.set("Contents/header.xml", b"<hh:head")
    with pytest.raises(ContainerError):
        Package.read(package.write())


def test_xml_with_doctype_is_rejected():
    package = Package.read(builtin_hwpx())
    package.set("Contents/header.xml", b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>')
    with pytest.raises(ContainerError):
        Package.read(package.write())


def test_reference_script_clears_personal_metadata():
    spec = importlib.util.spec_from_file_location("make_ref", ROOT / "scripts" / "make_reference_hwpx.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    package = Package.read(builtin_hwpx())
    content = package.xml("Contents/content.hpf")
    for meta in content.iter(OPF_META):
        if meta.get("name") in ("creator", "CreatedDate"):
            meta.text = "someone"
    package.set_xml("Contents/content.hpf", content)
    cleaned = Package.read(module.normalize(package.write())).xml("Contents/content.hpf")
    assert all(not (m.text or "") for m in cleaned.iter(OPF_META) if m.get("name") in ("creator", "CreatedDate"))
```

- [ ] **Step 2: `tests/helpers.py` 에 hwpx 도우미 추가** (파일 끝에 덧붙임; 맨 위 import 에 `import io`, `import zipfile`, `from lxml import etree` 가 없으면 추가)

```python
HWPX_NS = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "opf": "http://www.idpf.org/2007/opf/",
}
BUILTIN_HWPX = Path(__file__).resolve().parents[1] / "src/mdcast/builtin_templates/default/reference.hwpx"


def builtin_hwpx() -> bytes:
    return BUILTIN_HWPX.read_bytes()


def hwpx_integrity(data: bytes) -> dict:
    """Parse a hwpx and assert what Hangul relies on: package order, counts, unique ids, references."""
    hh = lambda tag: f"{{{HWPX_NS['hh']}}}{tag}"  # noqa: E731
    hp = lambda tag: f"{{{HWPX_NS['hp']}}}{tag}"  # noqa: E731
    archive = zipfile.ZipFile(io.BytesIO(data))
    first = archive.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    assert archive.read("mimetype") == b"application/hwp+zip"
    parts = {
        name: etree.fromstring(archive.read(name))
        for name in archive.namelist()
        if name.endswith((".xml", ".hpf"))
    }
    head = parts["Contents/header.xml"]
    for element in head.iter():
        if element.get("itemCnt") is not None:
            assert int(element.get("itemCnt")) == len(element), element.tag

    def ids(tag: str) -> set:
        values = [e.get("id") for e in head.iter(hh(tag))]
        assert len(values) == len(set(values)), f"duplicate {tag} id"
        return set(values)

    fonts = {}
    for face in head.iter(hh("fontface")):
        items = face.findall(hh("font"))
        assert int(face.get("fontCnt")) == len(items), face.get("lang")
        font_ids = [f.get("id") for f in items]
        assert len(font_ids) == len(set(font_ids))
        fonts[face.get("lang").lower()] = set(font_ids)
    chars, paras, fills, tabs, styles = (ids(t) for t in ("charPr", "paraPr", "borderFill", "tabPr", "style"))
    for char in head.iter(hh("charPr")):
        assert char.get("borderFillIDRef") in fills
        ref = char.find(hh("fontRef"))
        for lang, font_ids in fonts.items():
            assert ref.get(lang) in font_ids, (char.get("id"), lang)
    for para in head.iter(hh("paraPr")):
        assert para.get("tabPrIDRef") in tabs
        for border in para.iter(hh("border")):
            assert border.get("borderFillIDRef") in fills
    for style in head.iter(hh("style")):
        assert style.get("paraPrIDRef") in paras and style.get("charPrIDRef") in chars
        assert style.get("nextStyleIDRef") in styles
    section = parts["Contents/section0.xml"]
    for p in section.iter(hp("p")):
        assert p.get("paraPrIDRef") in paras and p.get("styleIDRef") in styles
    for run in section.iter(hp("run")):
        assert run.get("charPrIDRef") in chars
    begins = {b.get("id") for b in section.iter(hp("fieldBegin"))}
    for end in section.iter(hp("fieldEnd")):
        assert end.get("beginIDRef") in begins
    sec_prs = list(section.iter(hp("secPr")))
    assert len(sec_prs) == 1
    assert sec_prs[0].getparent().getparent() is section[0]
    return parts
```

- [ ] **Step 3: 테스트 실행 — 실패 확인**

Run: `uv run python -m pytest tests/test_hwpx_container.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mdcast.hwpx'`

- [ ] **Step 4: `src/mdcast/hwpx/units.py`**

```python
"""OWPML lengths (spec 2026-10-16 m2a §5.1, appendix A-4, A-12).

HWPUNIT is 1/7200 inch (1pt = 100). Hangul reads paragraph margins (left, right, intent, prev,
next) and tab positions at twice that unit; page sizes, page margins, border offsets and
header/footer list sizes are plain HWPUNIT.
"""

from __future__ import annotations


def hwpunit(mm: float) -> int:
    return round(mm * 7200 / 25.4)


def hwpunit_pt(pt: float) -> int:
    return round(pt * 100)


def para_unit(mm: float) -> int:
    return round(mm * 14400 / 25.4)


def para_unit_pt(pt: float) -> int:
    return round(pt * 200)
```

- [ ] **Step 5: `src/mdcast/hwpx/look.py`**

```python
"""Input values of the hwpx writer (spec §4.3) and its notices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

ELEMENTS = ("body", "quote", "code", "caption", "footnote", *(f"heading{i}" for i in range(1, 7)))


@dataclass(frozen=True)
class Look:
    """One element's look. ``None`` keeps the container's value."""

    font: str | None = None
    size: float | None = None  # pt
    bold: bool | None = None
    italic: bool | None = None
    color: str | None = None  # "#RRGGBB"
    align: str | None = None  # left | center | right | justify
    line_height: float | None = None  # ratio of the font size, 1.8 = 180%
    space_before: float | None = None  # pt
    space_after: float | None = None  # pt
    indent_left: float | None = None  # mm
    background: str | None = None  # "#RRGGBB"
    keep_with_next: bool | None = None


@dataclass(frozen=True)
class PageNumber:
    kind: str  # "page" | "pages"


Piece = str | PageNumber


@dataclass(frozen=True)
class Slots:
    left: tuple[Piece, ...] = ()
    center: tuple[Piece, ...] = ()
    right: tuple[Piece, ...] = ()
    line: str = "none"  # below | above | none


@dataclass(frozen=True)
class PageSetup:
    """Paper (portrait dimensions) and margins in mm; ``None`` keeps the container's value."""

    width: float | None = None
    height: float | None = None
    landscape: bool | None = None
    top: float | None = None
    bottom: float | None = None
    left: float | None = None
    right: float | None = None


@dataclass(frozen=True)
class Metadata:
    title: str = ""
    author: str = ""
    keywords: str = ""
    created: str = ""  # UTC "YYYY-MM-DDThh:mm:ssZ"
    extra: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Notice:
    kind: str  # "degraded" | "style-missing"
    element: str
    message: str


class Notices:
    """Notices, at most one per kind and element (spec §5.6: once per document)."""

    def __init__(self) -> None:
        self.items: list[Notice] = []
        self._seen: set[tuple[str, str]] = set()

    def add(self, kind: str, element: str, message: str) -> None:
        if (kind, element) not in self._seen:
            self._seen.add((kind, element))
            self.items.append(Notice(kind, element, message))


@dataclass
class Settings:
    looks: dict[str, Look] = field(default_factory=dict)
    styles: dict[str, str] = field(default_factory=dict)  # element -> container style name
    page: PageSetup = field(default_factory=PageSetup)
    header: Slots | None = None  # None: keep the container's header (source: reference)
    footer: Slots | None = None
    fill: Callable[[str], list[Piece]] = lambda text: [text]  # "{{key}}" text in kept headers
    list_marker: Callable[[bool, int, int], str] = lambda ordered, level, n: f"{n}." if ordered else "-"
    list_indent: float = 5.0  # mm per list level
    body_size: float = 11.0  # pt: list hanging indents, header placement
    body_line_height: float = 1.3
    table_caption_above: bool = True
    figure_caption_above: bool = False
    metadata: Metadata = field(default_factory=Metadata)
```

- [ ] **Step 6: `src/mdcast/hwpx/container.py`**

```python
"""hwpx (zip) package: read, edit parts, write with ``mimetype`` first and stored."""

from __future__ import annotations

import io
import zipfile

from lxml import etree

REQUIRED = ("mimetype", "Contents/header.xml", "Contents/section0.xml", "Contents/content.hpf")
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
_EPOCH = (1980, 1, 1, 0, 0, 0)


class ContainerError(Exception):
    """The container is not a usable hwpx."""


class Package:
    def __init__(self, entries: list[tuple[str, bytes, int]]) -> None:
        self._entries = entries

    @classmethod
    def read(cls, data: bytes) -> Package:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = [
                    (info.filename, archive.read(info), info.compress_type)
                    for info in archive.infolist()
                    if not info.is_dir()
                ]
        except (zipfile.BadZipFile, OSError, ValueError, RuntimeError, NotImplementedError, EOFError) as exc:
            raise ContainerError(f"hwpx(zip) 로 읽을 수 없습니다: {exc}") from exc
        package = cls(entries)
        missing = [name for name in REQUIRED if name not in package.names()]
        if missing:
            raise ContainerError(f"hwpx 에 필요한 파일이 없습니다: {', '.join(missing)}")
        for name in REQUIRED[1:]:
            package.xml(name)
        return package

    def names(self) -> list[str]:
        return [name for name, _, _ in self._entries]

    def get(self, name: str) -> bytes:
        for entry, data, _ in self._entries:
            if entry == name:
                return data
        raise KeyError(name)

    def set(self, name: str, data: bytes) -> None:
        for index, (entry, _, compress) in enumerate(self._entries):
            if entry == name:
                self._entries[index] = (name, data, compress)
                return
        self._entries.append((name, data, zipfile.ZIP_DEFLATED))

    def remove(self, name: str) -> None:
        self._entries = [entry for entry in self._entries if entry[0] != name]

    def xml(self, name: str) -> etree._Element:
        try:
            root = etree.fromstring(self.get(name), _PARSER)
        except etree.XMLSyntaxError as exc:
            raise ContainerError(f"{name} 의 XML 이 올바르지 않습니다: {exc}") from exc
        if root.getroottree().docinfo.internalDTD is not None:
            raise ContainerError(f"{name} 에 DTD 가 들어 있습니다")
        return root

    def set_xml(self, name: str, root: etree._Element) -> None:
        self.set(name, etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))

    def write(self) -> bytes:
        ordered = sorted(self._entries, key=lambda entry: entry[0] != "mimetype")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, data, compress in ordered:
                info = zipfile.ZipInfo(name, date_time=_EPOCH)
                info.compress_type = zipfile.ZIP_STORED if name == "mimetype" else compress
                archive.writestr(info, data)
        return buffer.getvalue()
```

- [ ] **Step 7: `src/mdcast/hwpx/__init__.py`** (Task 8 에서 `write` 등을 더한다)

```python
"""Standalone OWPML (hwpx) writer: pandoc AST in, hwpx bytes out.

Imports nothing from mdcast outside this package (spec 2026-10-15 §2).
"""

from mdcast.hwpx.container import ContainerError, Package
from mdcast.hwpx.look import ELEMENTS, Look, Metadata, Notice, PageNumber, PageSetup, Piece, Settings, Slots

__all__ = [
    "ELEMENTS",
    "ContainerError",
    "Look",
    "Metadata",
    "Notice",
    "Package",
    "PageNumber",
    "PageSetup",
    "Piece",
    "Settings",
    "Slots",
]
```

- [ ] **Step 8: `scripts/make_reference_hwpx.py`**

```python
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
```

- [ ] **Step 9: 내장 그릇 만들기** — 사용자에게 "한글 창이 뜨고 접근 허용 대화상자가 나오면 [모두 허용]" 을 알린 뒤 실행 (`dangerouslyDisableSandbox: true`):

Run: `uv run python scripts/make_reference_hwpx.py`
Expected: `...\src\mdcast\builtin_templates\default\reference.hwpx` 출력. 한글을 쓸 수 없으면 사용자에게 한글로 새 빈 문서를 hwpx 로 저장해 달라고 한 뒤 `--from <그 파일>` 로 실행한다.

- [ ] **Step 10: `builtin_container` 수정** — `src/mdcast/templates/resolve.py` 의 메서드를 다음으로 바꾼다:

```python
    def builtin_container(self, fmt: str) -> Container:
        """The built-in container for ``fmt``; ``path=None`` means the engine's own default."""
        if fmt in ("pdf", "hwpx"):
            return Container(BUILTIN_DIR / DEFAULT_NAME / DEFAULT_FILES[fmt], "builtin")
        return Container(None, "builtin")
```

`tests/test_template_resolve.py` 의 `test_builtin_container_ignores_custom_files` 에서
`assert tpl.builtin_container("hwpx") == tpl.builtin_container("docx")` 를 다음으로 바꾼다:

```python
    hwpx = tpl.builtin_container("hwpx")
    assert hwpx.source == "builtin" and hwpx.path.name == "reference.hwpx" and hwpx.path.is_file()
```

- [ ] **Step 11: 테스트 실행 — 통과 확인**

Run: `uv run python -m pytest tests/test_hwpx_container.py tests/test_template_resolve.py -q`
Expected: PASS

- [ ] **Step 12: 커밋**

```bash
git add src/mdcast/hwpx scripts/make_reference_hwpx.py src/mdcast/builtin_templates/default/reference.hwpx src/mdcast/templates/resolve.py tests/helpers.py tests/test_hwpx_container.py tests/test_template_resolve.py
git commit -m "feat(hwpx): package, units, input values and the built-in container"
```

---

### Task 2: header.xml 편집

**Files:**
- Create: `src/mdcast/hwpx/header.py`
- Test: `tests/test_hwpx_header.py`

**Interfaces:**
- Consumes: `Package`, `ContainerError` (Task 1), `units.*`
- Produces:
  - `CharSpec(font, size, color, bold, italic, underline, strike, script)` — `script` 은 `"sup" | "sub" | ""`
  - `ParaSpec(align, line_height, prev, next, left, right, hanging, keep_with_next, border_fill, offsets, connect, tab_pr)` — 길이 mm, 간격 pt, `offsets=(left, right, top, bottom)` mm
  - `Header(root)`: `.root`, `.item(list_tag, id) -> _Element`, `.style_id(name) -> str | None`, `.style(id)`, `.first_style_id() -> str`, `.para_left(para_id) -> float`(mm), `.font_refs(face) -> dict[lang, id]`, `.add_char(base_id, CharSpec) -> str`, `.add_para(base_id, ParaSpec) -> str`, `.add_border_fill(*, fill=None, top=False, bottom=False) -> str`, `.add_tabs(list[(mm, "LEFT"|"CENTER"|"RIGHT")]) -> str`, `.auto_tab() -> str`, `.blank_numbering(numbering_id)`
  - 같은 내용의 정의는 같은 id 를 돌려준다.

- [ ] **Step 1: 실패하는 테스트** — `tests/test_hwpx_header.py`

```python
import copy

from helpers import HWPX_NS as NS
from helpers import builtin_hwpx, hwpx_integrity
from lxml import etree

from mdcast.hwpx.container import Package
from mdcast.hwpx.header import CharSpec, Header, ParaSpec
from mdcast.hwpx.units import hwpunit, para_unit

HH = f"{{{NS['hh']}}}"


def header() -> Header:
    return Header(Package.read(builtin_hwpx()).xml("Contents/header.xml"))


def test_style_lookup_by_korean_name():
    h = header()
    assert h.style_id("바탕글") == "0"
    assert h.style_id("개요 1") == "2"
    assert h.style_id("없는 스타일") is None
    assert h.first_style_id() == "0"


def test_char_shape_values():
    h = header()
    cid = h.add_char("0", CharSpec(font="맑은 고딕", size=11, color="#1f3864", bold=True, italic=False))
    char = h.item("charProperties", cid)
    assert char.get("height") == "1100" and char.get("textColor") == "#1F3864"
    assert char.find("hh:bold", NS) is not None and char.find("hh:italic", NS) is None
    ref = char.find("hh:fontRef", NS)
    for face in h.root.iter(f"{HH}fontface"):
        fonts = face.findall("hh:font", NS)
        chosen = next(f for f in fonts if f.get("id") == ref.get(face.get("lang").lower()))
        assert chosen.get("face") == "맑은 고딕"
        assert chosen.find("hh:typeInfo", NS).get("weight") == "5"  # Hangul's own, appendix A-16
        assert int(face.get("fontCnt")) == len(fonts)


def test_unknown_font_has_no_type_info():
    h = header()
    ref = h.item("charProperties", h.add_char("0", CharSpec(font="Consolas"))).find("hh:fontRef", NS)
    face = next(h.root.iter(f"{HH}fontface"))
    font = next(f for f in face.findall("hh:font", NS) if f.get("id") == ref.get("hangul"))
    assert font.get("face") == "Consolas" and font.find("hh:typeInfo", NS) is None


def test_same_definition_is_reused():
    h = header()
    first = h.add_char("0", CharSpec(size=11))
    assert h.add_char("0", CharSpec(size=11)) == first
    assert h.add_char("0", CharSpec(size=12)) != first


def test_char_flags_follow_hangul_order():
    h = header()
    cid = h.add_char("0", CharSpec(bold=True, italic=True, underline=True, strike=True, script="sup"))
    tags = [etree.QName(child).localname for child in h.item("charProperties", cid)]
    assert tags[-5:] == ["italic", "bold", "underline", "strikeout", "supscript"]
    cleared = h.add_char(cid, CharSpec(bold=False, script=""))
    tags = [etree.QName(child).localname for child in h.item("charProperties", cleared)]
    assert "bold" not in tags and "supscript" not in tags and "italic" in tags


def test_para_shape_units():
    h = header()
    pid = h.add_para(
        "0",
        ParaSpec(align="justify", line_height=1.8, prev=4, next=6, left=5, hanging=3, keep_with_next=True),
    )
    para = h.item("paraProperties", pid)
    margin = {etree.QName(c).localname: c.get("value") for c in para.find("hh:margin", NS)}
    assert margin["left"] == "2835" and margin["intent"] == str(-para_unit(3))
    assert margin["prev"] == "800" and margin["next"] == "1200"
    assert para.find("hh:lineSpacing", NS).get("value") == "180"
    assert para.find("hh:lineSpacing", NS).get("type") == "PERCENT"
    assert para.find("hh:align", NS).get("horizontal") == "JUSTIFY"
    assert para.find("hh:breakSetting", NS).get("keepWithNext") == "1"
    assert abs(h.para_left(pid) - 5.0) < 0.01


def test_margin_inside_switch_is_updated():
    h = header()
    base = h.item("paraProperties", "0")
    margin = base.find("hh:margin", NS)
    base.remove(margin)
    hp = f"{{{NS['hp']}}}"
    switch = etree.SubElement(base, f"{hp}switch")
    etree.SubElement(switch, f"{hp}case").append(copy.deepcopy(margin))
    etree.SubElement(switch, f"{hp}default").append(margin)
    pid = h.add_para("0", ParaSpec(left=5))
    values = [m.find("hc:left", NS).get("value") for m in h.item("paraProperties", pid).iter(f"{HH}margin")]
    assert values == ["2835", "2835"]


def test_border_fills():
    h = header()
    fill = h.item("borderFills", h.add_border_fill(fill="#f6f8fa"))
    assert fill.find("hc:fillBrush/hc:winBrush", NS).get("faceColor") == "#F6F8FA"
    assert fill.find("hh:bottomBorder", NS).get("type") == "NONE"
    rule = h.item("borderFills", h.add_border_fill(bottom=True))
    assert rule.find("hh:bottomBorder", NS).get("type") == "SOLID"
    assert rule.find("hc:fillBrush/hc:winBrush", NS).get("faceColor") == "none"


def test_paragraph_border_offsets_are_plain_hwpunit():
    h = header()
    rule = h.add_border_fill(bottom=True)
    pid = h.add_para("0", ParaSpec(border_fill=rule, offsets=(2, 2, 0, 1.5), connect=False))
    border = h.item("paraProperties", pid).find("hh:border", NS)
    assert border.get("borderFillIDRef") == rule
    assert border.get("offsetLeft") == str(hwpunit(2)) and border.get("offsetBottom") == str(hwpunit(1.5))
    assert border.get("connect") == "0"


def test_tab_positions_are_doubled():
    h = header()
    tab = h.item("tabProperties", h.add_tabs([(75.0, "CENTER"), (150.0, "RIGHT")]))
    assert [(i.get("pos"), i.get("type")) for i in tab] == [
        (str(para_unit(75.0)), "CENTER"),
        (str(para_unit(150.0)), "RIGHT"),
    ]


def test_auto_tab_reuses_the_container_definition():
    assert header().auto_tab() == "1"


def test_outline_numbers_are_blanked():
    h = header()
    h.blank_numbering("1")
    heads = h.root.findall(".//hh:numbering[@id='1']/hh:paraHead", NS)
    assert heads and all(not (x.text or "") and x.get("textOffset") == "0" for x in heads)


def test_package_stays_sound_after_edits():
    package = Package.read(builtin_hwpx())
    h = Header(package.xml("Contents/header.xml"))
    h.add_char("0", CharSpec(font="Consolas", underline=True))
    h.add_para("0", ParaSpec(border_fill=h.add_border_fill(fill="#EEEEEE"), tab_pr=h.add_tabs([(10, "LEFT")])))
    package.set_xml("Contents/header.xml", h.root)
    hwpx_integrity(package.write())
```

- [ ] **Step 2: 실행 — 실패 확인**

Run: `uv run python -m pytest tests/test_hwpx_header.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mdcast.hwpx.header'`

- [ ] **Step 3: `src/mdcast/hwpx/header.py`**

```python
"""header.xml editing: character and paragraph shapes, border fills, tabs, fonts (spec §5)."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from lxml import etree

from mdcast.hwpx.container import ContainerError
from mdcast.hwpx.units import hwpunit, hwpunit_pt, para_unit, para_unit_pt

HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
LANGS = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")
# child order of hh:charPr as Hangul writes it (appendix A-16)
CHAR_ORDER = (
    "fontRef", "ratio", "spacing", "relSz", "offset", "italic", "bold", "underline",
    "strikeout", "outline", "shadow", "emboss", "engrave", "supscript", "subscript",
)
# the typeInfo Hangul writes for fonts it knows (appendix A-16); other faces go without one
TYPE_INFO = {
    "맑은 고딕": {
        "familyType": "FCAT_GOTHIC", "weight": "5", "proportion": "3", "contrast": "2",
        "strokeVariation": "0", "armStyle": "0", "letterform": "2", "midline": "0", "xHeight": "4",
    },
}
LINE_WIDTH = "0.12 mm"  # border width seen working in Hangul (appendix A-6)


def hh(tag: str) -> str:
    return f"{{{HH}}}{tag}"


def hc(tag: str) -> str:
    return f"{{{HC}}}{tag}"


@dataclass(frozen=True)
class CharSpec:
    """Changes to a base character shape; ``None`` keeps the base value."""

    font: str | None = None
    size: float | None = None  # pt
    color: str | None = None  # "#RRGGBB"
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strike: bool | None = None
    script: str | None = None  # "sup" | "sub" | "" (neither)


@dataclass(frozen=True)
class ParaSpec:
    """Changes to a base paragraph shape; ``None`` keeps the base value. Lengths mm, gaps pt."""

    align: str | None = None
    line_height: float | None = None
    prev: float | None = None
    next: float | None = None
    left: float | None = None
    right: float | None = None
    hanging: float | None = None
    keep_with_next: bool | None = None
    border_fill: str | None = None
    offsets: tuple[float, float, float, float] | None = None  # left, right, top, bottom
    connect: bool | None = None
    tab_pr: str | None = None


def _flag(element: etree._Element, name: str, on: bool | None, **attrs: str) -> None:
    if on is None:
        return
    for old in element.findall(hh(name)):
        element.remove(old)
    if on:
        etree.SubElement(element, hh(name), attrs)


def _order(element: etree._Element, order: tuple[str, ...]) -> None:
    rank = {hh(name): index for index, name in enumerate(order)}
    children = sorted(element, key=lambda child: rank.get(child.tag, len(order)))
    element[:] = children


class Header:
    def __init__(self, root: etree._Element) -> None:
        self.root = root
        self._known: dict[tuple[str, bytes], str] = {}

    def _list(self, tag: str) -> etree._Element:
        element = self.root.find(f".//{hh(tag)}")
        if element is None:
            raise ContainerError(f"header.xml 에 {tag} 가 없습니다")
        return element

    def item(self, list_tag: str, item_id: str) -> etree._Element:
        for element in self._list(list_tag):
            if element.get("id") == item_id:
                return element
        raise ContainerError(f"header.xml 에 {list_tag} id={item_id} 가 없습니다")

    def style_id(self, name: str) -> str | None:
        for style in self._list("styles"):
            if style.get("name") == name:
                return style.get("id")
        return None

    def style(self, style_id: str) -> etree._Element:
        return self.item("styles", style_id)

    def first_style_id(self) -> str:
        first = next(iter(self._list("styles")), None)
        if first is None:
            raise ContainerError("header.xml 에 스타일이 없습니다")
        return first.get("id")

    def para_left(self, para_id: str) -> float:
        """Left margin of a paragraph shape in mm."""
        left = self.item("paraProperties", para_id).find(f".//{hh('margin')}/{hc('left')}")
        return 0.0 if left is None else int(left.get("value", "0")) * 25.4 / 14400

    def _add(self, list_tag: str, element: etree._Element) -> str:
        element.attrib.pop("id", None)
        key = (list_tag, etree.tostring(element))
        if key in self._known:
            return self._known[key]
        container = self._list(list_tag)
        ids = [int(e.get("id")) for e in container if (e.get("id") or "").isdigit()]
        new_id = str(max(ids, default=-1) + 1)
        attrs = dict(element.attrib)
        element.attrib.clear()
        element.set("id", new_id)
        for name, value in attrs.items():
            element.set(name, value)
        container.append(element)
        container.set("itemCnt", str(len(container)))
        self._known[key] = new_id
        return new_id

    def font_refs(self, face: str) -> dict[str, str]:
        """The font's id in every language group, adding it where missing."""
        refs: dict[str, str] = {}
        for fontface in self._list("fontfaces").findall(hh("fontface")):
            fonts = fontface.findall(hh("font"))
            found = next((f for f in fonts if f.get("face") == face), None)
            if found is None:
                ids = [int(f.get("id")) for f in fonts if (f.get("id") or "").isdigit()]
                found = etree.SubElement(
                    fontface, hh("font"), id=str(max(ids, default=-1) + 1), face=face, type="TTF", isEmbedded="0"
                )
                if face in TYPE_INFO:
                    etree.SubElement(found, hh("typeInfo"), TYPE_INFO[face])
                fontface.set("fontCnt", str(len(fontface.findall(hh("font")))))
            refs[(fontface.get("lang") or "").lower()] = found.get("id")
        return refs

    def add_char(self, base_id: str, spec: CharSpec) -> str:
        element = copy.deepcopy(self.item("charProperties", base_id))
        if spec.size is not None:
            element.set("height", str(hwpunit_pt(spec.size)))
        if spec.color is not None:
            element.set("textColor", spec.color.upper())
        if spec.font is not None:
            ref = element.find(hh("fontRef"))
            if ref is not None:
                for lang, font_id in self.font_refs(spec.font).items():
                    if lang in LANGS:
                        ref.set(lang, font_id)
        _flag(element, "bold", spec.bold)
        _flag(element, "italic", spec.italic)
        color = element.get("textColor", "#000000")
        _flag(element, "underline", spec.underline, type="BOTTOM", shape="SOLID", color=color)
        _flag(element, "strikeout", spec.strike, shape="SOLID", color=color)
        if spec.script is not None:
            _flag(element, "supscript", spec.script == "sup")
            _flag(element, "subscript", spec.script == "sub")
        _order(element, CHAR_ORDER)
        return self._add("charProperties", element)

    def add_para(self, base_id: str, spec: ParaSpec) -> str:
        # hh:margin / hh:lineSpacing may sit in hp:switch case/default copies: update every copy
        element = copy.deepcopy(self.item("paraProperties", base_id))
        if spec.align is not None:
            for align in element.iter(hh("align")):
                align.set("horizontal", spec.align.upper())
        if spec.line_height is not None:
            for spacing in element.iter(hh("lineSpacing")):
                spacing.set("type", "PERCENT")
                spacing.set("value", str(round(spec.line_height * 100)))
        margins = {
            "intent": None if spec.hanging is None else -para_unit(spec.hanging),
            "left": None if spec.left is None else para_unit(spec.left),
            "right": None if spec.right is None else para_unit(spec.right),
            "prev": None if spec.prev is None else para_unit_pt(spec.prev),
            "next": None if spec.next is None else para_unit_pt(spec.next),
        }
        for margin in element.iter(hh("margin")):
            for name, value in margins.items():
                if value is None:
                    continue
                child = margin.find(hc(name))
                if child is None:
                    child = etree.SubElement(margin, hc(name), unit="HWPUNIT")
                child.set("value", str(value))
        if spec.keep_with_next is not None:
            for brk in element.iter(hh("breakSetting")):
                brk.set("keepWithNext", "1" if spec.keep_with_next else "0")
        borders = list(element.iter(hh("border")))
        if spec.border_fill is not None and not borders:
            borders = [etree.SubElement(element, hh("border"), offsetLeft="0", offsetRight="0",
                                        offsetTop="0", offsetBottom="0", connect="0", ignoreMargin="0")]
        for border in borders:
            if spec.border_fill is not None:
                border.set("borderFillIDRef", spec.border_fill)
            if spec.offsets is not None:
                for name, value in zip(("offsetLeft", "offsetRight", "offsetTop", "offsetBottom"), spec.offsets):
                    border.set(name, str(hwpunit(value)))
            if spec.connect is not None:
                border.set("connect", "1" if spec.connect else "0")
        if spec.tab_pr is not None:
            element.set("tabPrIDRef", spec.tab_pr)
        return self._add("paraProperties", element)

    def add_border_fill(self, *, fill: str | None = None, top: bool = False, bottom: bool = False) -> str:
        element = etree.Element(hh("borderFill"), threeD="0", shadow="0", centerLine="NONE", breakCellSeparateLine="0")
        for name in ("slash", "backSlash"):
            etree.SubElement(element, hh(name), type="NONE", Crooked="0", isCounter="0")
        for name, on in (("leftBorder", False), ("rightBorder", False), ("topBorder", top), ("bottomBorder", bottom)):
            etree.SubElement(element, hh(name), type="SOLID" if on else "NONE",
                             width=LINE_WIDTH if on else "0.1 mm", color="#000000")
        etree.SubElement(element, hh("diagonal"), type="SOLID", width="0.1 mm", color="#000000")
        brush = etree.SubElement(element, hc("fillBrush"))
        etree.SubElement(brush, hc("winBrush"), faceColor=fill.upper() if fill else "none",
                         hatchColor="#999999", alpha="0")
        return self._add("borderFills", element)

    def add_tabs(self, stops: list[tuple[float, str]]) -> str:
        element = etree.Element(hh("tabPr"), autoTabLeft="0", autoTabRight="0")
        for position, kind in stops:
            etree.SubElement(element, hh("tabItem"), pos=str(para_unit(position)), type=kind, leader="NONE")
        return self._add("tabProperties", element)

    def auto_tab(self) -> str:
        """Tabs whose tab after a list marker lands on the hanging indent (appendix A-15)."""
        for tab in self._list("tabProperties"):
            if tab.get("autoTabLeft") == "1" and tab.get("autoTabRight", "0") == "0" and not len(tab):
                return tab.get("id")
        return self._add("tabProperties", etree.Element(hh("tabPr"), autoTabLeft="1", autoTabRight="0"))

    def blank_numbering(self, numbering_id: str) -> None:
        """Hangul's outline numbers off: mdcast's numbering filter writes the numbers (spec §5.2)."""
        for numbering in self.root.iter(hh("numbering")):
            if numbering.get("id") == numbering_id:
                for head in numbering.findall(hh("paraHead")):
                    head.text = None
                    head.set("textOffset", "0")
```

- [ ] **Step 4: 실행 — 통과 확인**

Run: `uv run python -m pytest tests/test_hwpx_header.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/mdcast/hwpx/header.py tests/test_hwpx_header.py
git commit -m "feat(hwpx): header.xml shapes, border fills, tabs and fonts"
```

---

### Task 3: 요소별 모양

**Files:**
- Create: `src/mdcast/hwpx/shapes.py`
- Modify: `tests/helpers.py` (`hwpx_settings`)
- Test: `tests/test_hwpx_shapes.py`

**Interfaces:**
- Consumes: `Header`, `CharSpec`, `ParaSpec` (Task 2); `Look`, `Settings`, `Notices`, `ELEMENTS` (Task 1)
- Produces: `Shape(style: str, para: str, char: str, look: Look)`, `build_shapes(header, settings, notices) -> dict[str, Shape]` (모든 `ELEMENTS` 키), `PADDING = 2.0`; `tests/helpers.hwpx_settings(**changes) -> Settings` (내장 템플릿과 같은 값)

- [ ] **Step 1: `tests/helpers.py` 에 덧붙임**

```python
def hwpx_settings(**changes):
    """hwpx Settings with the built-in template's values, for writer tests below the adapter."""
    from dataclasses import replace as _replace

    from mdcast.hwpx.look import Look, Settings

    body = Look(font="맑은 고딕", size=11, bold=False, italic=False, color="#000000", align="justify",
                line_height=1.8, space_before=0, space_after=4, indent_left=0, keep_with_next=False)
    looks = {
        "body": body,
        "quote": _replace(body, size=10.5, color="#555555", align="left", space_after=0, indent_left=5),
        "code": Look(font="Consolas", size=9.5, bold=False, italic=False, color="#000000", align="left",
                     line_height=1.3, space_before=0, space_after=0, indent_left=0, background="#F6F8FA"),
        "caption": _replace(body, size=9.5, bold=True, align="center", line_height=1.3, space_after=0),
        "footnote": _replace(body, size=9, align="left", line_height=1.3, space_after=0),
    }
    for level in range(1, 7):
        looks[f"heading{level}"] = _replace(body, size=16 if level == 1 else 12, bold=True, align="left",
                                            line_height=1.3, space_before=12, space_after=6, keep_with_next=True)
    styles = {f"heading{level}": f"개요 {level}" for level in range(1, 7)}
    styles.update(body="바탕글", quote="바탕글", code="바탕글", caption="캡션", footnote="각주")
    markers = "□○-·"
    values = dict(
        looks=looks, styles=styles, body_size=11.0, body_line_height=1.8,
        list_marker=lambda ordered, level, n: f"{n}." if ordered else markers[min(level, 4) - 1],
    )
    values.update(changes)
    return Settings(**values)
```

- [ ] **Step 2: 실패하는 테스트** — `tests/test_hwpx_shapes.py`

```python
from helpers import HWPX_NS as NS
from helpers import builtin_hwpx, hwpx_settings

from mdcast.hwpx.container import Package
from mdcast.hwpx.header import Header
from mdcast.hwpx.look import ELEMENTS, Look, Notices, Settings
from mdcast.hwpx.shapes import build_shapes
from mdcast.hwpx.units import hwpunit, para_unit


def build(settings):
    header = Header(Package.read(builtin_hwpx()).xml("Contents/header.xml"))
    notices = Notices()
    return header, build_shapes(header, settings, notices), notices


def test_every_element_has_a_shape():
    _, shapes, notices = build(hwpx_settings())
    assert set(shapes) == set(ELEMENTS)
    assert notices.items == []


def test_heading_keeps_the_outline_level_and_drops_its_indent():
    header, shapes, _ = build(hwpx_settings())
    shape = shapes["heading1"]
    assert shape.style == "2"
    para = header.item("paraProperties", shape.para)
    assert para.find("hh:heading", NS).get("type") == "OUTLINE"
    assert para.find("hh:margin/hc:left", NS).get("value") == "0"
    char = header.item("charProperties", shape.char)
    assert char.get("height") == "1600" and char.find("hh:bold", NS) is not None


def test_body_values():
    header, shapes, _ = build(hwpx_settings())
    para = header.item("paraProperties", shapes["body"].para)
    assert para.find("hh:lineSpacing", NS).get("value") == "180"
    assert para.find("hh:align", NS).get("horizontal") == "JUSTIFY"
    assert para.find("hh:margin/hc:next", NS).get("value") == "800"


def test_missing_style_falls_back_with_one_notice():
    _, shapes, notices = build(Settings(styles={"quote": "인용", "code": "인용"}))
    assert shapes["quote"].style == "0"
    assert sorted((n.kind, n.element) for n in notices.items) == [
        ("style-missing", "code"),
        ("style-missing", "quote"),
    ]


def test_background_pads_the_paragraph():
    header, shapes, _ = build(hwpx_settings())
    para = header.item("paraProperties", shapes["code"].para)
    border = para.find("hh:border", NS)
    assert border.get("offsetLeft") == str(hwpunit(2.0)) and border.get("connect") == "0"
    assert para.find("hh:margin/hc:left", NS).get("value") == str(para_unit(2.0))
    assert para.find("hh:margin/hc:right", NS).get("value") == str(para_unit(2.0))
    assert para.find("hh:margin/hc:prev", NS).get("value") == str(para_unit(2.0))
    fill = header.item("borderFills", border.get("borderFillIDRef"))
    assert fill.find("hc:fillBrush/hc:winBrush", NS).get("faceColor") == "#F6F8FA"


def test_none_keeps_the_container_value():
    header, shapes, _ = build(Settings(looks={"body": Look()}, styles={"body": "바탕글"}))
    base = header.item("paraProperties", "0")
    para = header.item("paraProperties", shapes["body"].para)
    assert para.find("hh:lineSpacing", NS).get("value") == base.find("hh:lineSpacing", NS).get("value")
    assert para.find("hh:align", NS).get("horizontal") == base.find("hh:align", NS).get("horizontal")
```

- [ ] **Step 3: 실행 — 실패 확인**

Run: `uv run python -m pytest tests/test_hwpx_shapes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mdcast.hwpx.shapes'`

- [ ] **Step 4: `src/mdcast/hwpx/shapes.py`**

```python
"""Each element's style, paragraph shape and character shape (spec §5.1)."""

from __future__ import annotations

from dataclasses import dataclass

from mdcast.hwpx.header import CharSpec, Header, ParaSpec
from mdcast.hwpx.look import ELEMENTS, Look, Notices, Settings

PADDING = 2.0  # mm around a paragraph background, as the PDF code block's inset (spec §5.4)


@dataclass(frozen=True)
class Shape:
    style: str
    para: str
    char: str
    look: Look


def char_spec(look: Look) -> CharSpec:
    return CharSpec(font=look.font, size=look.size, color=look.color, bold=look.bold, italic=look.italic)


def para_spec(header: Header, look: Look) -> ParaSpec:
    left, right, prev, after = look.indent_left, None, look.space_before, look.space_after
    fill = offsets = connect = None
    if look.background:
        # Hangul widens a background by the border offsets: keep it on the text column and push
        # the neighbours away by the same amount, as the PDF block's inset does
        pad_pt = PADDING * 72 / 25.4
        fill = header.add_border_fill(fill=look.background)
        left, right = (look.indent_left or 0.0) + PADDING, PADDING
        prev, after = (look.space_before or 0.0) + pad_pt, (look.space_after or 0.0) + pad_pt
        offsets, connect = (PADDING,) * 4, False
    return ParaSpec(
        align=look.align, line_height=look.line_height, prev=prev, next=after, left=left, right=right,
        keep_with_next=look.keep_with_next, border_fill=fill, offsets=offsets, connect=connect,
    )


def build_shapes(header: Header, settings: Settings, notices: Notices) -> dict[str, Shape]:
    shapes: dict[str, Shape] = {}
    for element in ELEMENTS:
        look = settings.looks.get(element) or Look()
        name = settings.styles.get(element)
        style_id = header.style_id(name) if name else None
        if style_id is None:
            if name:
                notices.add(
                    "style-missing", element,
                    f"hwpx 기준 문서에 스타일 '{name}' 이(가) 없어 첫 스타일(바탕글)을 씁니다",
                )
            style_id = header.first_style_id()
        style = header.style(style_id)
        para = header.add_para(style.get("paraPrIDRef", "0"), para_spec(header, look))
        char = header.add_char(style.get("charPrIDRef", "0"), char_spec(look))
        shapes[element] = Shape(style_id, para, char, look)
    return shapes
```

- [ ] **Step 5: 실행 — 통과 확인**

Run: `uv run python -m pytest tests/test_hwpx_shapes.py -q`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add src/mdcast/hwpx/shapes.py tests/helpers.py tests/test_hwpx_shapes.py
git commit -m "feat(hwpx): element shapes from the template looks"
```

---

### Task 4: 본문 문단과 인라인

**Files:**
- Create: `src/mdcast/hwpx/section.py`
- Modify: `tests/helpers.py` (`hwpx_render`, `hwpx_texts`)
- Test: `tests/test_hwpx_section.py`

**Interfaces:**
- Consumes: `Shape`, `build_shapes` (Task 3); `Header`, `CharSpec`, `ParaSpec`; `Settings`, `Notices`
- Produces:
  - `section.HP`, `section.hp(tag)`, `section.PAGE_BREAK = ("mdcast-hwpx", "pagebreak")`, `section.append_text(t, text)`
  - `SectionWriter(header, shapes, settings, notices).build(doc) -> list[_Element]` (각각 `hp:p`, 최소 1개)
  - 이 Task 는 문단·제목·코드·인용·가로줄·줄 블록·Div·정의 목록·인라인·링크·쪽 나눔. 목록(Task 5)·표/그림/각주/수식(Task 6)은 이후 Task 가 같은 클래스에 메서드를 채운다. 이 Task 에서는 `list`·`table`·`figure` 메서드와 `Note`/`Math`/`Image` 처리를 아래 코드 그대로(완성본) 넣어 두고, 그 테스트는 Task 5·6 에서 쓴다.
  - `tests/helpers.hwpx_render(md, settings=None) -> (header, shapes, paragraphs, notices)`, `tests/helpers.hwpx_texts(paragraphs) -> list[str]`

- [ ] **Step 1: `tests/helpers.py` 에 덧붙임**

```python
def hwpx_render(md: str, settings=None, doc=None):
    """Header, shapes, paragraphs and notices of ``md`` (or ``doc``) on the built-in container."""
    from mdcast.ast import md_to_doc
    from mdcast.hwpx.container import Package
    from mdcast.hwpx.header import Header
    from mdcast.hwpx.look import Notices
    from mdcast.hwpx.section import SectionWriter
    from mdcast.hwpx.shapes import build_shapes

    settings = settings or hwpx_settings()
    header = Header(Package.read(builtin_hwpx()).xml("Contents/header.xml"))
    notices = Notices()
    shapes = build_shapes(header, settings, notices)
    paragraphs = SectionWriter(header, shapes, settings, notices).build(doc or md_to_doc(md))
    return header, shapes, paragraphs, notices


def hwpx_texts(paragraphs) -> list[str]:
    """Each paragraph's own text (runs directly under it; header/footer lists excluded)."""
    t = f"{{{HWPX_NS['hp']}}}t"
    run = f"{{{HWPX_NS['hp']}}}run"
    return ["".join("".join(x.itertext()) for r in p.findall(run) for x in r.findall(t)) for p in paragraphs]
```

- [ ] **Step 2: 실패하는 테스트** — `tests/test_hwpx_section.py`

```python
import panflute as pf
from helpers import HWPX_NS as NS
from helpers import hwpx_render, hwpx_texts

from mdcast.ast import md_to_doc
from mdcast.filters._raw import raw_block


def runs(paragraph):
    return [(r.get("charPrIDRef"), "".join("".join(t.itertext()) for t in r.findall("hp:t", NS)))
            for r in paragraph.findall("hp:run", NS)]


def test_heading_and_body_paragraphs():
    header, shapes, paragraphs, _ = hwpx_render("# 제목\n\n본문 *기울임* **굵게**\n")
    assert hwpx_texts(paragraphs) == ["제목", "본문 기울임 굵게"]
    heading, body = paragraphs
    assert heading.get("styleIDRef") == "2" and heading.get("paraPrIDRef") == shapes["heading1"].para
    assert body.get("paraPrIDRef") == shapes["body"].para
    chars = [char for char, _ in runs(body)]
    assert chars[0] == shapes["body"].char and len(set(chars)) == 3
    assert header.item("charProperties", chars[1]).find("hh:italic", NS) is not None
    assert header.item("charProperties", chars[2]).find("hh:bold", NS) is not None


def test_inline_code_uses_the_code_font_and_size():
    header, shapes, paragraphs, _ = hwpx_render("앞 `x = 1` 뒤\n")
    char = runs(paragraphs[0])[1][0]
    element = header.item("charProperties", char)
    assert element.get("height") == "950"
    code_ref = header.item("charProperties", shapes["code"].char).find("hh:fontRef", NS).get("latin")
    assert element.find("hh:fontRef", NS).get("latin") == code_ref


def test_code_block_is_one_paragraph_with_line_breaks():
    _, shapes, paragraphs, _ = hwpx_render("```\n가\n나\n```\n")
    assert len(paragraphs) == 1 and paragraphs[0].get("paraPrIDRef") == shapes["code"].para
    assert len(paragraphs[0].findall(".//hp:lineBreak", NS)) == 1
    assert hwpx_texts(paragraphs) == ["가나"]


def test_link_field():
    url = "https://x.kr/a?b=1;c:d\\e"
    doc = pf.Doc(pf.Para(pf.Link(pf.Str("링크"), url=url), pf.Space(), pf.Str("뒤")))
    header, _, paragraphs, _ = hwpx_render("", doc=doc)
    p = paragraphs[0]
    begin = p.find(".//hp:fieldBegin", NS)
    params = {e.get("name"): e.text for e in begin.find("hp:parameters", NS)}
    assert begin.get("type") == "HYPERLINK" and begin.get("fieldid") == "627600491"
    assert params["Command"] == "https\\://x.kr/a?b=1\\;c\\:d\\\\e;1;0;0;"
    assert params["Path"] == "https://x.kr/a?b=1;c:d\\e"
    assert p.find(".//hp:fieldEnd", NS).get("beginIDRef") == begin.get("id")
    link_char = next(char for char, text in runs(p) if text == "링크")
    element = header.item("charProperties", link_char)
    assert element.get("textColor") == "#0000FF" and element.find("hh:underline", NS) is not None


def test_internal_link_is_plain_text():
    _, _, paragraphs, _ = hwpx_render("[절](#sec)\n")
    assert paragraphs[0].find(".//hp:fieldBegin", NS) is None
    assert hwpx_texts(paragraphs) == ["절"]


def test_pagebreak_marker_breaks_before_the_next_paragraph():
    doc = md_to_doc("가\n\n나\n")
    doc.content.insert(1, raw_block("pagebreak", "mdcast-hwpx"))
    _, _, paragraphs, _ = hwpx_render("", doc=doc)
    assert [p.get("pageBreak") for p in paragraphs] == ["0", "1"]


def test_raw_blocks_of_other_formats_are_dropped():
    doc = md_to_doc("가\n")
    doc.content.append(raw_block("#pagebreak()", "typst"))
    _, _, paragraphs, _ = hwpx_render("", doc=doc)
    assert hwpx_texts(paragraphs) == ["가"]


def test_control_characters_are_dropped():
    doc = pf.Doc(pf.Para(pf.Str("가\x0b나\x01다")))
    _, _, paragraphs, _ = hwpx_render("", doc=doc)
    assert hwpx_texts(paragraphs) == ["가나다"]


def test_quotes_indent_per_level():
    header, shapes, paragraphs, _ = hwpx_render("> 바깥\n>\n> > 안쪽\n")
    lefts = [header.para_left(p.get("paraPrIDRef")) for p in paragraphs]
    assert abs(lefts[0] - 5.0) < 0.01 and abs(lefts[1] - 10.0) < 0.01
    assert all(p.get("styleIDRef") == shapes["quote"].style for p in paragraphs)


def test_horizontal_rule_draws_a_bottom_border():
    header, _, paragraphs, _ = hwpx_render("가\n\n---\n\n나\n")
    rule = paragraphs[1]
    fill_id = header.item("paraProperties", rule.get("paraPrIDRef")).find("hh:border", NS).get("borderFillIDRef")
    assert header.item("borderFills", fill_id).find("hh:bottomBorder", NS).get("type") == "SOLID"
    assert hwpx_texts(paragraphs) == ["가", "", "나"]


def test_line_block_and_definition_list():
    header, _, paragraphs, _ = hwpx_render("| 하나\n| 둘\n\n용어\n:   정의\n")
    assert hwpx_texts(paragraphs) == ["하나둘", "용어", "정의"]
    assert len(paragraphs[0].findall(".//hp:lineBreak", NS)) == 1
    term_char = paragraphs[1].find("hp:run", NS).get("charPrIDRef")
    assert header.item("charProperties", term_char).find("hh:bold", NS) is not None
    assert abs(header.para_left(paragraphs[2].get("paraPrIDRef")) - 5.0) < 0.01


def test_empty_document_has_one_paragraph():
    _, _, paragraphs, _ = hwpx_render("")
    assert len(paragraphs) == 1 and paragraphs[0].find("hp:run/hp:t", NS) is not None
```

- [ ] **Step 3: 실행 — 실패 확인**

Run: `uv run python -m pytest tests/test_hwpx_section.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mdcast.hwpx.section'`

- [ ] **Step 4: `src/mdcast/hwpx/section.py`** (목록·낮춰 출력 포함 완성본)

```python
"""Pandoc AST → section0.xml paragraphs (spec §5)."""

from __future__ import annotations

import itertools
import re
import unicodedata
from dataclasses import dataclass, replace

import panflute as pf
from lxml import etree

from mdcast.hwpx.header import CharSpec, Header, ParaSpec
from mdcast.hwpx.look import Notices, Settings
from mdcast.hwpx.shapes import Shape

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
PAGE_BREAK = ("mdcast-hwpx", "pagebreak")  # raw block the pagebreak filter writes for hwpx
LINK_COLOR = "#0000FF"  # Hangul's own link look (appendix A-5)
HYPERLINK_FIELD = "627600491"  # '%hlk'
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_GAP_EM = 0.5  # between a list marker and its text, as the docx writer
_MIN_HANGING_MM = 3.0
_DEGRADED = {
    "table": "hwpx 표는 M2b 에서 지원합니다 — 행마다 한 문단으로 낮춰 썼습니다",
    "image": "hwpx 이미지는 M2b 에서 지원합니다 — [이미지: 설명] 으로 대신 썼습니다",
    "footnote": "hwpx 각주는 M2b 에서 지원합니다 — 문서 끝에 모아 썼습니다",
    "math": "hwpx 수식은 M4 에서 이미지로 지원합니다 — LaTeX 원문을 썼습니다",
}


def hp(tag: str) -> str:
    return f"{{{HP}}}{tag}"


def append_text(t: etree._Element, text: str) -> None:
    """Add text at the end of an ``hp:t`` that may already hold tab or line-break children."""
    if len(t):
        t[-1].tail = (t[-1].tail or "") + text
    else:
        t.text = (t.text or "") + text


def text_em(text: str) -> float:
    """Rough rendered width in em, as the docx writer estimates list markers."""
    return sum(1.0 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 0.55 for ch in text)


def hanging_mm(markers: list[str], size_pt: float) -> float:
    """Hanging indent holding the widest marker plus a gap (appendix A-15: never narrower)."""
    em = max(text_em(marker) for marker in markers) + _GAP_EM
    return max(em * size_pt * 25.4 / 72, _MIN_HANGING_MM)


def escape_command(url: str) -> str:
    return url.replace("\\", "\\\\").replace(":", "\\:").replace(";", "\\;")


class Paragraph:
    """One ``hp:p`` being built; consecutive text with the same character shape shares a run."""

    def __init__(self, para: str, style: str, char: str, page_break: bool) -> None:
        self.element = etree.Element(
            hp("p"), id="0", paraPrIDRef=para, styleIDRef=style,
            pageBreak="1" if page_break else "0", columnBreak="0", merged="0",
        )
        self.char = char
        self._run: etree._Element | None = None
        self._text: etree._Element | None = None

    def _run_for(self, char: str) -> etree._Element:
        if self._run is None or self._run.get("charPrIDRef") != char:
            self._run = etree.SubElement(self.element, hp("run"), charPrIDRef=char)
            self._text = None
        return self._run

    def _t(self, char: str) -> etree._Element:
        run = self._run_for(char)
        if self._text is None:
            self._text = etree.SubElement(run, hp("t"))
        return self._text

    def text(self, char: str, value: str) -> None:
        value = _CONTROL.sub("", value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        for index, part in enumerate(value.split("\t")):
            if index:
                self.mark(char, "tab")
            if part:
                append_text(self._t(char), part)

    def mark(self, char: str, kind: str) -> None:
        """A ``lineBreak`` or ``tab`` inside the text (appendix A-4, A-7)."""
        attrs = {"width": "0", "leader": "0", "type": "1"} if kind == "tab" else {}
        etree.SubElement(self._t(char), hp(kind), attrs)

    def control(self, char: str) -> etree._Element:
        ctrl = etree.SubElement(self._run_for(char), hp("ctrl"))
        self._text = None
        return ctrl

    def finish(self) -> etree._Element:
        if self._run is None:
            etree.SubElement(etree.SubElement(self.element, hp("run"), charPrIDRef=self.char), hp("t"))
        return self.element


@dataclass(frozen=True)
class Context:
    element: str = "body"  # look of plain paragraphs here: body, quote or footnote
    quotes: int = 0  # enclosing block quotes
    extra: float = 0.0  # mm added to the element's left margin (list item bodies, definitions)
    level: int = 0  # list depth
    list_text: float = 0.0  # mm: where the enclosing list item's text starts
    tight: bool = False  # no paragraph gaps (tight list items)


class SectionWriter:
    def __init__(self, header: Header, shapes: dict[str, Shape], settings: Settings, notices: Notices) -> None:
        self.header = header
        self.shapes = shapes
        self.settings = settings
        self.notices = notices
        self.paragraphs: list[Paragraph] = []
        self._page_break = False
        self._notes: list[list[pf.Element]] = []
        self._fields = itertools.count(1_000_001)
        self._quote = header.para_left(shapes["quote"].para)

    # paragraphs ---------------------------------------------------------------------------

    def build(self, doc: pf.Doc) -> list[etree._Element]:
        self.blocks(doc.content, Context())
        index = 0
        while index < len(self._notes):  # a note may hold notes
            self._note(index + 1, self._notes[index])
            index += 1
        if not self.paragraphs:
            self.paragraph("body", Context())
        return [p.finish() for p in self.paragraphs]

    def _left(self, element: str, ctx: Context) -> float:
        own = self.header.para_left(self.shapes[element].para)
        depth = ctx.quotes - 1 if element == "quote" else ctx.quotes
        return own + self._quote * max(depth, 0) + ctx.extra

    def _para_id(self, element: str, ctx: Context, **changes) -> str:
        shape = self.shapes[element]
        left = self._left(element, ctx)
        if abs(left - self.header.para_left(shape.para)) < 1e-6 and not ctx.tight and not changes:
            return shape.para
        gaps = {"prev": 0.0, "next": 0.0} if ctx.tight else {}
        return self.header.add_para(shape.para, ParaSpec(left=left, **gaps, **changes))

    def paragraph(self, element: str, ctx: Context, para: str | None = None) -> Paragraph:
        shape = self.shapes[element]
        paragraph = Paragraph(para or self._para_id(element, ctx), shape.style, shape.char, self._page_break)
        self._page_break = False
        self.paragraphs.append(paragraph)
        return paragraph

    # blocks -------------------------------------------------------------------------------

    def blocks(self, blocks, ctx: Context) -> None:
        for block in blocks:
            self.block(block, ctx)

    def block(self, block: pf.Element, ctx: Context) -> None:
        if isinstance(block, (pf.Para, pf.Plain)):
            paragraph = self.paragraph(ctx.element, ctx)
            self.inlines(paragraph, block.content, self.shapes[ctx.element].char)
        elif isinstance(block, pf.Header):
            element = f"heading{min(max(block.level, 1), 6)}"
            paragraph = self.paragraph(element, replace(ctx, tight=False))
            self.inlines(paragraph, block.content, self.shapes[element].char)
        elif isinstance(block, pf.CodeBlock):
            paragraph = self.paragraph("code", ctx)
            char = self.shapes["code"].char
            for index, line in enumerate(block.text.split("\n")):
                if index:
                    paragraph.mark(char, "lineBreak")
                paragraph.text(char, line)
        elif isinstance(block, pf.BlockQuote):
            self.blocks(block.content, replace(ctx, element="quote", quotes=ctx.quotes + 1))
        elif isinstance(block, pf.HorizontalRule):
            rule = self.header.add_border_fill(bottom=True)
            self.paragraph("body", ctx, self._para_id("body", ctx, border_fill=rule))
        elif isinstance(block, pf.LineBlock):
            paragraph = self.paragraph(ctx.element, ctx)
            char = self.shapes[ctx.element].char
            for index, line in enumerate(block.content):
                if index:
                    paragraph.mark(char, "lineBreak")
                self.inlines(paragraph, line.content, char)
        elif isinstance(block, pf.Div):
            self.blocks(block.content, ctx)
        elif isinstance(block, pf.DefinitionList):
            self.definitions(block, ctx)
        elif isinstance(block, (pf.BulletList, pf.OrderedList)):
            self.list(block, ctx)
        elif isinstance(block, pf.Table):
            self.table(block, ctx)
        elif isinstance(block, pf.Figure):
            self.figure(block, ctx)
        elif isinstance(block, pf.RawBlock):
            if (block.format, block.text.strip()) == PAGE_BREAK:
                self._page_break = True

    def definitions(self, block: pf.DefinitionList, ctx: Context) -> None:
        inner = replace(ctx, extra=ctx.extra + self.settings.list_indent)
        bold = self._char(self.shapes[ctx.element].char, bold=True)
        for item in block.content:
            self.inlines(self.paragraph(ctx.element, ctx), item.term, bold)
            for definition in item.definitions:
                self.blocks(definition.content, inner)

    def list(self, block: pf.Element, ctx: Context) -> None:
        """개조식: marker text + tab, hanging indent with Hangul's auto tab (spec §5.3)."""
        ordered = isinstance(block, pf.OrderedList)
        level = ctx.level + 1
        numbers = range(1, 11) if ordered else [1]
        hanging = hanging_mm([self.settings.list_marker(ordered, level, n) for n in numbers], self.settings.body_size)
        base = self._left(ctx.element, replace(ctx, extra=0.0))
        # one indent step further per level, but never left of the parent item's text (docx rule)
        marker_left = base + self.settings.list_indent * (level - 1)
        if ctx.level:
            marker_left = max(marker_left, ctx.list_text)
        text_left = marker_left + hanging
        char = self.shapes[ctx.element].char
        start = block.start if ordered else 1
        for offset, item in enumerate(block.content):
            blocks = list(item.content)
            first = blocks[0] if blocks else None
            marker_ctx = replace(ctx, extra=marker_left - base, tight=isinstance(first, pf.Plain))
            para = self._para_id(ctx.element, marker_ctx, hanging=hanging, tab_pr=self.header.auto_tab())
            paragraph = self.paragraph(ctx.element, ctx, para)
            paragraph.text(char, self.settings.list_marker(ordered, level, start + offset))
            paragraph.mark(char, "tab")
            if isinstance(first, (pf.Para, pf.Plain)):
                self.inlines(paragraph, first.content, char)
                blocks = blocks[1:]
            inner = replace(ctx, extra=text_left - base, level=level, list_text=text_left)
            for rest in blocks:
                self.block(rest, replace(inner, tight=isinstance(rest, pf.Plain)))

    # degraded until M2b (spec §5.6) -------------------------------------------------------

    def table(self, table: pf.Table, ctx: Context) -> None:
        self.notices.add("degraded", "table", _DEGRADED["table"])
        caption = self._caption_blocks(table.caption)
        above = self.settings.table_caption_above
        if caption and above:
            self._caption(caption, ctx)
        rows = list(table.head.content) if table.head else []
        for body in table.content:
            rows += list(body.head) + list(body.content)
        if table.foot:
            rows += list(table.foot.content)
        char = self.shapes[ctx.element].char
        for row in rows:
            paragraph = self.paragraph(ctx.element, ctx)
            for index, cell in enumerate(row.content):
                if index:
                    paragraph.text(char, " | ")
                for number, inner in enumerate(cell.content):
                    if number:
                        paragraph.text(char, " ")
                    if isinstance(inner, (pf.Para, pf.Plain)):
                        self.inlines(paragraph, inner.content, char)
                    else:
                        paragraph.text(char, pf.stringify(inner))
        if caption and not above:
            self._caption(caption, ctx)

    def figure(self, figure: pf.Figure, ctx: Context) -> None:
        caption = self._caption_blocks(figure.caption)
        above = self.settings.figure_caption_above
        if caption and above:
            self._caption(caption, ctx)
        self.blocks(figure.content, ctx)
        if caption and not above:
            self._caption(caption, ctx)

    @staticmethod
    def _caption_blocks(caption: pf.Caption | None) -> list[pf.Element]:
        if caption is None:
            return []
        return [b for b in caption.content if isinstance(b, (pf.Para, pf.Plain)) and pf.stringify(b).strip()]

    def _caption(self, blocks: list[pf.Element], ctx: Context) -> None:
        for block in blocks:
            self.inlines(self.paragraph("caption", ctx), block.content, self.shapes["caption"].char)

    def _note(self, number: int, blocks: list[pf.Element]) -> None:
        ctx = Context(element="footnote")
        char = self.shapes["footnote"].char
        paragraph = self.paragraph("footnote", ctx)
        paragraph.text(char, f"[{number}] ")
        rest = list(blocks)
        if rest and isinstance(rest[0], (pf.Para, pf.Plain)):
            self.inlines(paragraph, rest.pop(0).content, char)
        self.blocks(rest, ctx)

    # inlines ------------------------------------------------------------------------------

    def _char(self, base: str, **changes) -> str:
        return self.header.add_char(base, CharSpec(**changes))

    def _code(self, base: str) -> str:
        look = self.shapes["code"].look
        return self.header.add_char(base, CharSpec(font=look.font, size=look.size))

    def inlines(self, paragraph: Paragraph, items, char: str) -> None:
        for item in items:
            self.inline(paragraph, item, char)

    def inline(self, paragraph: Paragraph, item: pf.Element, char: str) -> None:
        if isinstance(item, pf.Str):
            paragraph.text(char, item.text)
        elif isinstance(item, (pf.Space, pf.SoftBreak)):
            paragraph.text(char, " ")
        elif isinstance(item, pf.LineBreak):
            paragraph.mark(char, "lineBreak")
        elif isinstance(item, pf.Emph):
            self.inlines(paragraph, item.content, self._char(char, italic=True))
        elif isinstance(item, pf.Strong):
            self.inlines(paragraph, item.content, self._char(char, bold=True))
        elif isinstance(item, pf.Underline):
            self.inlines(paragraph, item.content, self._char(char, underline=True))
        elif isinstance(item, pf.Strikeout):
            self.inlines(paragraph, item.content, self._char(char, strike=True))
        elif isinstance(item, pf.Superscript):
            self.inlines(paragraph, item.content, self._char(char, script="sup"))
        elif isinstance(item, pf.Subscript):
            self.inlines(paragraph, item.content, self._char(char, script="sub"))
        elif isinstance(item, pf.Quoted):
            left, right = ("“", "”") if item.quote_type == "DoubleQuote" else ("‘", "’")
            paragraph.text(char, left)
            self.inlines(paragraph, item.content, char)
            paragraph.text(char, right)
        elif isinstance(item, pf.Code):
            paragraph.text(self._code(char), item.text)
        elif isinstance(item, pf.Math):
            self.notices.add("degraded", "math", _DEGRADED["math"])
            paragraph.text(self._code(char), item.text)
        elif isinstance(item, pf.Image):
            self.notices.add("degraded", "image", _DEGRADED["image"])
            paragraph.text(char, f"[이미지: {pf.stringify(item).strip() or item.url}]")
        elif isinstance(item, pf.Note):
            self.notices.add("degraded", "footnote", _DEGRADED["footnote"])
            self._notes.append(list(item.content))
            paragraph.text(char, f"[{len(self._notes)}]")
        elif isinstance(item, pf.Link):
            self.link(paragraph, item, char)
        elif isinstance(item, (pf.SmallCaps, pf.Span, pf.Cite)):
            self.inlines(paragraph, item.content, char)
        # RawInline (other formats) and anything else: dropped

    def link(self, paragraph: Paragraph, item: pf.Link, char: str) -> None:
        """Hangul hyperlink field around the link text (appendix A-5); ``#id`` links stay text."""
        if not item.url or item.url.startswith("#"):
            self.inlines(paragraph, item.content, char)
            return
        field = str(next(self._fields))
        begin = etree.SubElement(
            paragraph.control(char), hp("fieldBegin"), id=field, type="HYPERLINK", name="",
            editable="0", dirty="0", zorder="-1", fieldid=HYPERLINK_FIELD,
        )
        params = etree.SubElement(begin, hp("parameters"), cnt="6", name="")
        etree.SubElement(params, hp("integerParam"), name="Prop").text = "0"
        for name, value in (
            ("Command", escape_command(item.url) + ";1;0;0;"),
            ("Path", item.url),
            ("Category", "HWPHYPERLINK_TYPE_URL"),
            ("TargetType", "HWPHYPERLINK_TARGET_BOOKMARK"),
            ("DocOpenType", "HWPHYPERLINK_JUMP_CURRENTTAB"),
        ):
            etree.SubElement(params, hp("stringParam"), name=name).text = value
        self.inlines(paragraph, item.content, self._char(char, color=LINK_COLOR, underline=True))
        etree.SubElement(paragraph.control(char), hp("fieldEnd"), beginIDRef=field, fieldid=HYPERLINK_FIELD)
```

- [ ] **Step 5: 실행 — 통과 확인**

Run: `uv run python -m pytest tests/test_hwpx_section.py -q`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add src/mdcast/hwpx/section.py tests/helpers.py tests/test_hwpx_section.py
git commit -m "feat(hwpx): body paragraphs, inline looks, links and page breaks"
```

---

### Task 5: 개조식 목록

**Files:**
- Test: `tests/test_hwpx_lists.py`
- (구현은 Task 4 의 `SectionWriter.list` — 테스트가 드러내는 결함만 고친다)

**Interfaces:**
- Consumes: `SectionWriter.list`, `section.hanging_mm(markers, size_pt)` (Task 4), `tests/helpers.hwpx_render`
- Produces: 목록 문단 = 기호 + `hp:tab` + 글자; paraPr `left` = 기호 위치, `intent` = −내어쓰기, `tabPrIDRef` = 자동 탭(id 1)

- [ ] **Step 1: 테스트** — `tests/test_hwpx_lists.py`

```python
from helpers import HWPX_NS as NS
from helpers import hwpx_render, hwpx_settings, hwpx_texts

from mdcast.hwpx.section import hanging_mm
from mdcast.hwpx.units import para_unit


def margin(header, paragraph, name):
    para = header.item("paraProperties", paragraph.get("paraPrIDRef"))
    return int(para.find(f"hh:margin/hc:{name}", NS).get("value"))


def test_bullet_marker_tab_and_hanging_indent():
    header, _, paragraphs, _ = hwpx_render("- 하나\n- 둘\n")
    assert hwpx_texts(paragraphs) == ["□하나", "□둘"]
    first = paragraphs[0]
    assert first.find("hp:run/hp:t/hp:tab", NS) is not None
    assert margin(header, first, "left") == 0
    assert margin(header, first, "intent") == -para_unit(hanging_mm(["□"], 11))
    assert header.item("paraProperties", first.get("paraPrIDRef")).get("tabPrIDRef") == "1"


def test_ordered_markers_count_from_the_list_start():
    _, _, paragraphs, _ = hwpx_render("3. 셋\n4. 넷\n")
    assert hwpx_texts(paragraphs) == ["3.셋", "4.넷"]


def test_hanging_holds_the_widest_marker():
    settings = hwpx_settings(list_marker=lambda ordered, level, n: f"({n})" if ordered else "-")
    header, _, paragraphs, _ = hwpx_render("1. 가\n", settings)
    widest = hanging_mm([f"({n})" for n in range(1, 11)], 11)
    assert margin(header, paragraphs[0], "intent") == -para_unit(widest)


def test_nested_marker_never_left_of_the_parent_text():
    header, _, paragraphs, _ = hwpx_render("- 하나\n    - 둘\n")
    parent_text = hanging_mm(["□"], 11)
    expected = max(5.0, parent_text)
    assert margin(header, paragraphs[1], "left") == para_unit(expected)
    assert hwpx_texts(paragraphs)[1] == "○둘"


def test_tight_items_have_no_gaps_loose_items_keep_the_body_gaps():
    header, _, tight, _ = hwpx_render("- 하나\n- 둘\n")
    assert margin(header, tight[0], "next") == 0
    header, _, loose, _ = hwpx_render("- 하나\n\n- 둘\n")
    assert margin(header, loose[0], "next") == para_unit(4 * 25.4 / 72)


def test_second_paragraph_of_an_item_aligns_with_its_text():
    header, _, paragraphs, _ = hwpx_render("- 하나\n\n    이어지는 문단\n")
    assert margin(header, paragraphs[1], "left") == para_unit(hanging_mm(["□"], 11))
    assert margin(header, paragraphs[1], "intent") == 0


def test_item_starting_with_code_block():
    header, shapes, paragraphs, _ = hwpx_render("-   ```\n    코드\n    ```\n")
    assert hwpx_texts(paragraphs) == ["□", "코드"]
    code_left = header.para_left(paragraphs[1].get("paraPrIDRef"))
    assert abs(code_left - (hanging_mm(["□"], 11) + 2.0)) < 0.01  # item text + code padding


def test_list_inside_quote():
    header, _, paragraphs, _ = hwpx_render("> - 하나\n>     - 둘\n")
    first, second = paragraphs
    assert margin(header, first, "left") == para_unit(5.0)  # quote indent
    assert margin(header, second, "left") == para_unit(max(10.0, 5.0 + hanging_mm(["□"], 11)))
```

- [ ] **Step 2: 실행**

Run: `uv run python -m pytest tests/test_hwpx_lists.py -q`
Expected: PASS. 실패하면 systematic-debugging 으로 `SectionWriter.list`/`_para_id` 의 원인을 찾아 고치고, 테스트의 기대값이 spec §5.3 과 다르면 spec 이 기준이다.

- [ ] **Step 3: 커밋**

```bash
git add tests/test_hwpx_lists.py src/mdcast/hwpx/section.py
git commit -m "test(hwpx): 개조식 list markers, hanging indents and nesting"
```

---

### Task 6: M2b 전까지 낮춰 출력하는 요소

**Files:**
- Test: `tests/test_hwpx_degraded.py`
- (구현은 Task 4 의 `table`, `figure`, `_note`, `inline`)

**Interfaces:**
- Consumes: `SectionWriter`, `Notices` (`kind="degraded"`, `element` ∈ table/image/footnote/math)
- Produces: spec §5.6 의 낮춘 출력과 종류당 알림 1개

- [ ] **Step 1: 테스트** — `tests/test_hwpx_degraded.py`

```python
from helpers import hwpx_render, hwpx_texts


def kinds(notices):
    return [(n.kind, n.element) for n in notices.items]


def test_tables_become_row_paragraphs_with_one_notice():
    md = "Table: 요약\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n| c |\n|---|\n| 3 |\n"
    _, shapes, paragraphs, notices = hwpx_render(md)
    assert hwpx_texts(paragraphs) == ["요약", "a | b", "1 | 2", "c", "3"]
    assert paragraphs[0].get("styleIDRef") == shapes["caption"].style
    assert kinds(notices) == [("degraded", "table")]


def test_table_caption_below_when_configured():
    from helpers import hwpx_settings

    _, _, paragraphs, _ = hwpx_render("Table: 요약\n\n| a |\n|---|\n| 1 |\n", hwpx_settings(table_caption_above=False))
    assert hwpx_texts(paragraphs) == ["a", "1", "요약"]


def test_images_become_placeholders_and_figure_captions_stay():
    _, shapes, paragraphs, notices = hwpx_render("앞 ![그림](x.png) 뒤\n\n![설명](y.png)\n")
    assert hwpx_texts(paragraphs) == ["앞 [이미지: 그림] 뒤", "[이미지: 설명]", "설명"]
    assert paragraphs[2].get("styleIDRef") == shapes["caption"].style
    assert kinds(notices) == [("degraded", "image")]


def test_footnotes_are_collected_at_the_end():
    _, shapes, paragraphs, notices = hwpx_render("본문[^1] 둘[^2]\n\n[^1]: 첫 각주\n[^2]: 둘째\n")
    assert hwpx_texts(paragraphs) == ["본문[1] 둘[2]", "[1] 첫 각주", "[2] 둘째"]
    assert paragraphs[1].get("paraPrIDRef") == shapes["footnote"].para
    assert kinds(notices) == [("degraded", "footnote")]


def test_math_keeps_its_latex_in_the_code_look():
    header, shapes, paragraphs, notices = hwpx_render("식 $x^2$ 끝\n")
    assert hwpx_texts(paragraphs) == ["식 x^2 끝"]
    assert kinds(notices) == [("degraded", "math")]
```

- [ ] **Step 2: 실행**

Run: `uv run python -m pytest tests/test_hwpx_degraded.py -q`
Expected: PASS (실패하면 원인을 찾아 `section.py` 를 고친다)

- [ ] **Step 3: 커밋**

```bash
git add tests/test_hwpx_degraded.py src/mdcast/hwpx/section.py
git commit -m "test(hwpx): tables, images, footnotes and math degrade with one notice each"
```

---

### Task 7: 쪽 설정·머리말/꼬리말·첫 문단

**Files:**
- Create: `src/mdcast/hwpx/page.py`
- Test: `tests/test_hwpx_page.py`

**Interfaces:**
- Consumes: `Header`, `ParaSpec`, `Shape`, `Settings`, `Slots`, `PageNumber`, `PageSetup`, `section.hp`, `section.append_text`, `units.hwpunit`
- Produces:
  - `layout(top, bottom, size, ratio, header_line, footer_line) -> Layout(top, header, bottom, footer, footer_prev, below_offset, above_offset)` — mm, `footer_prev` 는 pt
  - `find_sec_pr_run(section) -> _Element` (없으면 `ContainerError`)
  - `assemble(section, paragraphs, header, shapes, settings) -> None` — section 의 문단을 `paragraphs` 로 바꾸고, secPr 런을 첫 문단 맨 앞에, 머리말·꼬리말 컨트롤 런을 그 다음에 둔다
  - `auto_number(kind) -> _Element` (`hp:ctrl/hp:autoNum`)

- [ ] **Step 1: 실패하는 테스트** — `tests/test_hwpx_page.py`

```python
import pytest
from helpers import HWPX_NS as NS
from helpers import builtin_hwpx, hwpx_settings

from mdcast.ast import md_to_doc
from mdcast.hwpx.container import Package
from mdcast.hwpx.header import Header
from mdcast.hwpx.look import Notices, PageNumber, PageSetup, Slots
from mdcast.hwpx.page import assemble, layout
from mdcast.hwpx.section import SectionWriter
from mdcast.hwpx.shapes import build_shapes
from mdcast.hwpx.units import hwpunit, para_unit, para_unit_pt

PAGE = PageSetup(width=210, height=297, landscape=False, top=20, bottom=15, left=20, right=20)
HEADER = Slots(left=("왼쪽",), right=("오른쪽",), line="below")
FOOTER = Slots(center=(PageNumber("page"), " / ", PageNumber("pages")))


def build(md="본문\n", container=None, **changes):
    values = {"page": PAGE, "header": HEADER, "footer": FOOTER}
    values.update(changes)
    settings = hwpx_settings(**values)
    package = Package.read(container or builtin_hwpx())
    header = Header(package.xml("Contents/header.xml"))
    section = package.xml("Contents/section0.xml")
    notices = Notices()
    shapes = build_shapes(header, settings, notices)
    paragraphs = SectionWriter(header, shapes, settings, notices).build(md_to_doc(md))
    assemble(section, paragraphs, header, shapes, settings)
    package.set_xml("Contents/header.xml", header.root)
    package.set_xml("Contents/section0.xml", section)
    return header, section, package


def test_layout_matches_the_pdf_model():
    lay = layout(20, 15, 11, 1.8, "below", "none")
    assert lay.top == pytest.approx(6.69, abs=0.01)
    assert lay.header == pytest.approx(13.31, abs=0.01)
    assert (lay.bottom, lay.footer) == (0.0, 15)
    assert lay.footer_prev == pytest.approx(16.6, abs=0.1)
    assert lay.below_offset == pytest.approx(0.14, abs=0.01)


def test_layout_never_goes_above_the_page():
    lay = layout(3, 3, 11, 1.8, "below", "above")
    assert lay.top == 0.0 and lay.header == 3


def test_first_paragraph_carries_the_section_settings_and_controls():
    _, section, _ = build("# 제목\n\n본문\n")
    first = section[0]
    assert first.find("hp:run/hp:secPr", NS) is not None and first[0].find("hp:secPr", NS) is not None
    controls = first[1].findall("hp:ctrl", NS)
    assert [c[0].tag.split("}")[1] for c in controls] == ["header", "footer"]
    assert "".join(first.find("hp:run/hp:t", NS).itertext()) == "제목"
    assert len(section.findall("hp:p", NS)) == 2


def test_page_size_margins_and_split():
    _, section, _ = build()
    page = section.find(".//hp:pagePr", NS)
    assert (page.get("width"), page.get("height"), page.get("landscape")) == (
        str(hwpunit(210)), str(hwpunit(297)), "WIDELY")
    margin = page.find("hp:margin", NS)
    lay = layout(20, 15, 11, 1.8, "below", "none")
    assert margin.get("left") == str(hwpunit(20))
    assert margin.get("top") == str(hwpunit(lay.top))
    assert abs(int(margin.get("top")) + int(margin.get("header")) - hwpunit(20)) <= 1  # rounding
    assert (margin.get("bottom"), margin.get("footer")) == ("0", str(hwpunit(15)))
    assert section.find(".//hp:visibility", NS).get("hideFirstHeader") == "0"


def test_landscape_keeps_portrait_dimensions():
    _, section, _ = build(page=PageSetup(width=210, height=297, landscape=True))
    page = section.find(".//hp:pagePr", NS)
    assert page.get("landscape") == "NARROWLY" and page.get("width") == str(hwpunit(210))


def test_header_slots_tabs_and_rule():
    header, section, _ = build()
    control = section.find(".//hp:header", NS)
    sub = control.find("hp:subList", NS)
    assert abs(int(sub.get("textWidth")) - hwpunit(170)) <= 1 and sub.get("vertAlign") == "TOP"
    p = sub.find("hp:p", NS)
    t = p.find("hp:run/hp:t", NS)
    assert t.text == "왼쪽" and len(t.findall("hp:tab", NS)) == 2 and t[-1].tail == "오른쪽"
    para = header.item("paraProperties", p.get("paraPrIDRef"))
    tabs = header.item("tabProperties", para.get("tabPrIDRef"))
    positions = [int(i.get("pos")) for i in tabs]
    assert abs(positions[0] - para_unit(85)) <= 2 and abs(positions[1] - para_unit(170)) <= 2
    fill = header.item("borderFills", para.find("hh:border", NS).get("borderFillIDRef"))
    assert fill.find("hh:bottomBorder", NS).get("type") == "SOLID"


def test_footer_page_numbers_and_offset():
    header, section, _ = build()
    p = section.find(".//hp:footer/hp:subList/hp:p", NS)
    numbers = [n.get("numType") for n in p.iter(f"{{{NS['hp']}}}autoNum")]
    assert numbers == ["PAGE", "TOTAL_PAGE"]
    lay = layout(20, 15, 11, 1.8, "below", "none")
    prev = header.item("paraProperties", p.get("paraPrIDRef")).find("hh:margin/hc:prev", NS)
    assert prev.get("value") == str(para_unit_pt(lay.footer_prev))


def test_empty_slots_write_no_control():
    _, section, _ = build(header=Slots(), footer=Slots())
    assert section.find(".//hp:header", NS) is None and section.find(".//hp:footer", NS) is None


def test_reference_header_is_kept_and_filled():
    _, _, package = build(header=Slots(left=("{{title}} 쪽 {{page}}",)), footer=Slots(center=("꼬리",)))

    def fill(text):
        out = []
        for part in text.replace("{{title}}", "제목값").split("{{page}}"):
            if out:
                out.append(PageNumber("page"))
            out.append(part)
        return out

    _, section, _ = build(container=package.write(), header=None, footer=None, fill=fill)
    p = section.find(".//hp:header/hp:subList/hp:p", NS)
    texts = "".join("".join(t.itertext()) for t in p.iter(f"{{{NS['hp']}}}t"))
    assert texts == "제목값 쪽 "
    assert [n.get("numType") for n in p.iter(f"{{{NS['hp']}}}autoNum")] == ["PAGE"]
    assert len(section.findall(".//hp:header", NS)) == 1 and len(section.findall(".//hp:footer", NS)) == 1
```

- [ ] **Step 2: 실행 — 실패 확인**

Run: `uv run python -m pytest tests/test_hwpx_page.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mdcast.hwpx.page'`

- [ ] **Step 3: `src/mdcast/hwpx/page.py`**

```python
"""Page setup, header/footer controls and the first paragraph (spec §6.1, §6.2)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from lxml import etree

from mdcast.hwpx.container import ContainerError
from mdcast.hwpx.header import Header, ParaSpec
from mdcast.hwpx.look import PageNumber, PageSetup, Piece, Settings, Slots
from mdcast.hwpx.section import append_text, hp
from mdcast.hwpx.shapes import Shape
from mdcast.hwpx.units import hwpunit

RULE = 1.5 + 0.18  # mm: the PDF's gap between a header row and its 0.5pt rule, plus the rule
BASELINE = 0.85  # Hangul: baseline below a line's top, in font sizes (appendix A-9)


@dataclass(frozen=True)
class Layout:
    top: float  # mm
    header: float
    bottom: float
    footer: float
    footer_prev: float  # pt: space above the footer paragraph
    below_offset: float  # mm: header rule below the text
    above_offset: float  # mm: footer rule above the text


def layout(top: float, bottom: float, size: float, ratio: float, header_line: str, footer_line: str) -> Layout:
    """Split the yaml margins so header and footer baselines land where the PDF puts them (§6.1)."""
    s = size * 25.4 / 72
    header_baseline = 0.7 * top - (RULE if header_line == "below" else 0.0) - (0.2 + (ratio - 1) / 2) * s
    page_top = max(0.0, header_baseline - BASELINE * s)
    footer_baseline = 0.3 * bottom + (RULE if footer_line == "above" else 0.0) + (0.8 + (ratio - 1) / 2) * s
    return Layout(
        top=page_top,
        header=top - page_top,
        bottom=0.0,
        footer=bottom,
        footer_prev=max(0.0, footer_baseline - BASELINE * s) * 72 / 25.4,
        below_offset=max(0.0, 1.5 + (0.55 - ratio / 2) * s),
        above_offset=max(0.0, 1.5 + ((ratio - 1) / 2 - 0.05) * s),
    )


def find_sec_pr_run(section: etree._Element) -> etree._Element:
    for paragraph in section.findall(hp("p")):
        for run in paragraph.findall(hp("run")):
            if run.find(hp("secPr")) is not None:
                return run
    raise ContainerError("section0.xml 에 쪽 설정(secPr)이 없습니다")


def auto_number(kind: str) -> etree._Element:
    ctrl = etree.Element(hp("ctrl"))
    number = etree.SubElement(ctrl, hp("autoNum"), num="1", numType="TOTAL_PAGE" if kind == "pages" else "PAGE")
    etree.SubElement(number, hp("autoNumFormat"), type="DIGIT", userChar="", prefixChar="", suffixChar="",
                     supscript="0")
    return ctrl


def _mm(value: str | None) -> float:
    return int(value or "0") * 25.4 / 7200


def _set(margin: etree._Element, **values: float) -> None:
    for name, value in values.items():
        margin.set(name, str(hwpunit(value)))


def apply_page(sec_pr: etree._Element, page: PageSetup) -> etree._Element:
    page_pr = sec_pr.find(hp("pagePr"))
    margin = None if page_pr is None else page_pr.find(hp("margin"))
    if margin is None:
        raise ContainerError("section0.xml 의 쪽 설정에 용지(pagePr)가 없습니다")
    if page.width is not None and page.height is not None:
        page_pr.set("width", str(hwpunit(min(page.width, page.height))))
        page_pr.set("height", str(hwpunit(max(page.width, page.height))))
    if page.landscape is not None:
        page_pr.set("landscape", "NARROWLY" if page.landscape else "WIDELY")
    for side in ("left", "right"):
        value = getattr(page, side)
        if value is not None:
            margin.set(side, str(hwpunit(value)))
    return margin


def body_width(sec_pr: etree._Element) -> float:
    page_pr = sec_pr.find(hp("pagePr"))
    margin = page_pr.find(hp("margin"))
    across = page_pr.get("height") if page_pr.get("landscape") == "NARROWLY" else page_pr.get("width")
    used = int(margin.get("left", "0")) + int(margin.get("right", "0")) + int(margin.get("gutter", "0"))
    return (int(across or "0") - used) * 25.4 / 7200


def _controls(section: etree._Element, kinds: list[str]) -> list[etree._Element]:
    found = []
    for paragraph in section.findall(hp("p")):
        for run in paragraph.findall(hp("run")):
            for ctrl in run.findall(hp("ctrl")):
                if any(ctrl.find(hp(kind)) is not None for kind in kinds):
                    found.append(ctrl)
    return found


def _expand(t: etree._Element, fill: Callable[[str], list[Piece]]) -> list[etree._Element]:
    """An ``hp:t`` with ``{{key}}`` text as text and page-number controls."""
    if "{{" not in "".join(t.itertext()):
        return [t]
    out: list[etree._Element] = []
    current = etree.Element(hp("t"))

    def put(value: str) -> None:
        nonlocal current
        for piece in fill(value) if "{{" in value else [value]:
            if isinstance(piece, PageNumber):
                out.append(current)
                out.append(auto_number(piece.kind))
                current = etree.Element(hp("t"))
            else:
                append_text(current, piece)

    put(t.text or "")
    for child in list(t):
        tail, child.tail = child.tail, None
        current.append(child)
        put(tail or "")
    out.append(current)
    kept = [node for node in out if node.tag != hp("t") or node.text or len(node)]
    return kept or [etree.Element(hp("t"))]


def fill_controls(controls: list[etree._Element], fill: Callable[[str], list[Piece]]) -> None:
    for ctrl in controls:
        for run in list(ctrl.iter(hp("run"))):
            children: list[etree._Element] = []
            for child in run:
                children.extend(_expand(child, fill) if child.tag == hp("t") else [child])
            run[:] = children


def _has_content(slots: Slots) -> bool:
    return bool(slots.left or slots.center or slots.right) or slots.line in ("below", "above")


def _slot_paragraph(slots: Slots, para: str, style: str, char: str) -> etree._Element:
    paragraph = etree.Element(hp("p"), id="0", paraPrIDRef=para, styleIDRef=style, pageBreak="0",
                              columnBreak="0", merged="0")
    run = etree.SubElement(paragraph, hp("run"), charPrIDRef=char)
    t = etree.SubElement(run, hp("t"))
    for index, pieces in enumerate((slots.left, slots.center, slots.right)):
        if index:
            if t is None:
                t = etree.SubElement(run, hp("t"))
            etree.SubElement(t, hp("tab"), width="0", leader="0", type="1")
        for piece in pieces:
            if isinstance(piece, PageNumber):
                run.append(auto_number(piece.kind))
                t = None
            else:
                if t is None:
                    t = etree.SubElement(run, hp("t"))
                append_text(t, piece)
    return paragraph


def _slot_control(kind: str, number: int, paragraph: etree._Element, width: float, height: float) -> etree._Element:
    ctrl = etree.Element(hp("ctrl"))
    part = etree.SubElement(ctrl, hp(kind), id=str(number), applyPageType="BOTH")
    sub = etree.SubElement(
        part, hp("subList"), id="", textDirection="HORIZONTAL", lineWrap="BREAK", vertAlign="TOP",
        linkListIDRef="0", linkListNextIDRef="0", textWidth=str(hwpunit(width)), textHeight=str(hwpunit(height)),
        hasTextRef="0", hasNumRef="0",
    )
    sub.append(paragraph)
    return ctrl


def _slot_para(header: Header, body: Shape, slots: Slots, width: float, lay: Layout, footer: bool) -> str:
    fill = offsets = None
    if slots.line in ("below", "above"):
        fill = header.add_border_fill(top=slots.line == "above", bottom=slots.line == "below")
        offsets = (0.0, 0.0, lay.above_offset if slots.line == "above" else 0.0,
                   lay.below_offset if slots.line == "below" else 0.0)
    tabs = header.add_tabs([(width / 2, "CENTER"), (width, "RIGHT")])
    spec = ParaSpec(align="left", prev=lay.footer_prev if footer else 0.0, next=0.0, left=0.0, right=0.0,
                    hanging=0.0, keep_with_next=False, border_fill=fill, offsets=offsets, tab_pr=tabs)
    return header.add_para(body.para, spec)


def assemble(section: etree._Element, paragraphs: list[etree._Element], header: Header,
             shapes: dict[str, Shape], settings: Settings) -> None:
    """Put ``paragraphs`` in the section with the container's section settings (spec §6)."""
    sec_run = find_sec_pr_run(section)
    sec_pr = sec_run.find(hp("secPr"))
    kinds = [kind for kind, slots in (("header", settings.header), ("footer", settings.footer)) if slots is None]
    if len(kinds) == 2:
        kinds.append("pageNum")
    kept = _controls(section, kinds)
    first_id = section.find(hp("p")).get("id", "0")
    sec_run.getparent().remove(sec_run)
    for ctrl in kept:
        ctrl.getparent().remove(ctrl)
    for child in section.findall(hp("p")):
        section.remove(child)

    margin = apply_page(sec_pr, settings.page)
    old = {name: _mm(margin.get(name)) for name in ("top", "header", "bottom", "footer")}
    top = settings.page.top if settings.page.top is not None else old["top"] + old["header"]
    bottom = settings.page.bottom if settings.page.bottom is not None else old["bottom"] + old["footer"]
    lay = layout(top, bottom, settings.body_size, settings.body_line_height,
                 settings.header.line if settings.header else "none",
                 settings.footer.line if settings.footer else "none")
    width = body_width(sec_pr)
    visibility = sec_pr.find(hp("visibility"))
    fill_controls(kept, settings.fill)
    controls = list(kept)
    body = shapes["body"]
    style = header.style_id("머리말") or body.style
    number = max((int(c[0].get("id") or 0) for c in kept if (c[0].get("id") or "").isdigit()), default=0)

    if settings.header is None:
        _set(margin, top=max(0.0, top - old["header"]), header=min(old["header"], top))
    else:
        _set(margin, top=lay.top, header=lay.header)
        if visibility is not None:
            visibility.set("hideFirstHeader", "0")
        if _has_content(settings.header):
            number += 1
            para = _slot_para(header, body, settings.header, width, lay, footer=False)
            controls.append(_slot_control("header", number, _slot_paragraph(settings.header, para, style, body.char),
                                          width, lay.header))
    if settings.footer is None:
        _set(margin, bottom=max(0.0, bottom - old["footer"]), footer=min(old["footer"], bottom))
    else:
        _set(margin, bottom=lay.bottom, footer=lay.footer)
        if visibility is not None:
            visibility.set("hideFirstFooter", "0")
        if _has_content(settings.footer):
            number += 1
            para = _slot_para(header, body, settings.footer, width, lay, footer=True)
            controls.append(_slot_control("footer", number, _slot_paragraph(settings.footer, para, style, body.char),
                                          width, lay.footer))

    first = paragraphs[0]
    first.set("id", first_id)
    first.insert(0, sec_run)
    if controls:
        run = etree.Element(hp("run"), charPrIDRef=body.char)
        for ctrl in controls:
            run.append(ctrl)
        first.insert(1, run)
    for paragraph in paragraphs:
        section.append(paragraph)
```

- [ ] **Step 4: 실행 — 통과 확인**

Run: `uv run python -m pytest tests/test_hwpx_page.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/mdcast/hwpx/page.py tests/test_hwpx_page.py
git commit -m "feat(hwpx): page setup, header and footer controls, first paragraph"
```

---

### Task 8: 메타데이터와 `write()`

**Files:**
- Create: `src/mdcast/hwpx/meta.py`, `src/mdcast/hwpx/writer.py`
- Modify: `src/mdcast/hwpx/__init__.py` (`write`, `Header` 재수출)
- Test: `tests/test_hwpx_write.py`

**Interfaces:**
- Consumes: Task 1–7 전부
- Produces: `mdcast.hwpx.write(doc: pf.Doc, container: bytes, settings: Settings) -> tuple[bytes, list[Notice]]` (그릇이 깨졌으면 `ContainerError`); `meta.apply_metadata(content_root, Metadata)`, `meta.preview_text(paragraphs) -> bytes`, `meta.reset_caret(app_root)`, `meta.keep_first_section(package, content_root)`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_hwpx_write.py`

```python
import re
from pathlib import Path

import pytest
from helpers import HWPX_NS as NS
from helpers import builtin_hwpx, hwpx_integrity, hwpx_settings

from mdcast.ast import md_to_doc
from mdcast.hwpx import ContainerError, Metadata, Package, write

FIXTURES = Path(__file__).parent / "fixtures" / "md"
SRC = Path(__file__).resolve().parents[1] / "src" / "mdcast" / "hwpx"
OPF = f"{{{NS['opf']}}}"
META = Metadata(title="제목", author="작성자", keywords="mdcast", created="2026-10-16T00:00:00Z",
                extra=(("mdcast.generator", "mdcast 0.1"),))


@pytest.mark.parametrize("name", ["kitchen-sink", "edge-cases", "korean-report"])
def test_fixtures_give_sound_packages(name):
    text = (FIXTURES / f"{name}.md").read_text(encoding="utf-8")
    data, _ = write(md_to_doc(text), builtin_hwpx(), hwpx_settings(metadata=META))
    hwpx_integrity(data)


def test_metadata_preview_and_caret():
    data, _ = write(md_to_doc("# 첫 제목\n\n본문\n"), builtin_hwpx(), hwpx_settings(metadata=META))
    parts = hwpx_integrity(data)
    content = parts["Contents/content.hpf"]
    assert content.find(f"{OPF}metadata/{OPF}title").text == "제목"
    values = {m.get("name"): m.text for m in content.iter(f"{OPF}meta")}
    assert values["creator"] == "작성자" and values["keyword"] == "mdcast"
    assert values["mdcast.generator"] == "mdcast 0.1" and values["CreatedDate"] == "2026-10-16T00:00:00Z"
    preview = Package.read(data).get("Preview/PrvText.txt").decode("utf-8")
    assert preview.startswith("첫 제목\r\n본문")
    caret = parts["settings.xml"].find("{http://www.hancom.co.kr/hwpml/2011/app}CaretPosition")
    assert (caret.get("paraIDRef"), caret.get("pos")) == ("0", "0")


def test_outline_numbers_are_blanked_in_the_output():
    data, _ = write(md_to_doc("# 제목\n"), builtin_hwpx(), hwpx_settings())
    heads = hwpx_integrity(data)["Contents/header.xml"].findall(".//hh:numbering[@id='1']/hh:paraHead", NS)
    assert all(not (h.text or "") for h in heads)


def test_empty_document_keeps_the_section_settings():
    data, _ = write(md_to_doc(""), builtin_hwpx(), hwpx_settings())
    section = hwpx_integrity(data)["Contents/section0.xml"]
    assert len(section.findall("hp:p", NS)) == 1


def test_extra_sections_of_a_container_are_dropped():
    package = Package.read(builtin_hwpx())
    package.set("Contents/section1.xml", package.get("Contents/section0.xml"))
    content = package.xml("Contents/content.hpf")
    manifest = content.find(f"{OPF}manifest")
    item = manifest.makeelement(f"{OPF}item", {"id": "section1", "href": "Contents/section1.xml",
                                               "media-type": "application/xml"})
    manifest.append(item)
    spine = content.find(f"{OPF}spine")
    spine.append(spine.makeelement(f"{OPF}itemref", {"idref": "section1", "linear": "yes"}))
    package.set_xml("Contents/content.hpf", content)
    data, _ = write(md_to_doc("본문\n"), package.write(), hwpx_settings())
    out = Package.read(data)
    assert "Contents/section1.xml" not in out.names()
    assert b"section1" not in out.get("Contents/content.hpf")


def test_broken_container_raises():
    with pytest.raises(ContainerError):
        write(md_to_doc("본문\n"), b"junk", hwpx_settings())


def test_hwpx_package_imports_only_itself():
    pattern = re.compile(r"^\s*(?:from|import)\s+mdcast(?:\.(\w+))?", re.MULTILINE)
    for path in SRC.glob("*.py"):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            assert match.group(1) == "hwpx", f"{path.name}: {match.group(0).strip()}"
```

- [ ] **Step 2: 실행 — 실패 확인**

Run: `uv run python -m pytest tests/test_hwpx_write.py -q`
Expected: FAIL — `ImportError: cannot import name 'write' from 'mdcast.hwpx'`

- [ ] **Step 3: `src/mdcast/hwpx/meta.py`**

```python
"""content.hpf metadata, preview text, caret position and extra sections (spec §6.3)."""

from __future__ import annotations

import re

from lxml import etree

from mdcast.hwpx.container import Package
from mdcast.hwpx.look import Metadata
from mdcast.hwpx.section import hp

OPF = "http://www.idpf.org/2007/opf/"
HA = "http://www.hancom.co.kr/hwpml/2011/app"
MAX_PREVIEW = 1000
_SECTION = re.compile(r"Contents/section[1-9]\d*\.xml")


def _opf(tag: str) -> str:
    return f"{{{OPF}}}{tag}"


def _meta(metadata: etree._Element, name: str) -> etree._Element:
    for element in metadata.findall(_opf("meta")):
        if element.get("name") == name:
            return element
    return etree.SubElement(metadata, _opf("meta"), name=name, content="text")


def apply_metadata(package_root: etree._Element, md: Metadata) -> None:
    metadata = package_root.find(_opf("metadata"))
    if metadata is None:
        metadata = etree.Element(_opf("metadata"))
        package_root.insert(0, metadata)
    title = metadata.find(_opf("title"))
    if title is None:
        title = etree.SubElement(metadata, _opf("title"))
    title.text = md.title or None
    values = {"creator": md.author, "keyword": md.keywords, "CreatedDate": md.created,
              "ModifiedDate": md.created, "date": "", **dict(md.extra)}
    for name, value in values.items():
        _meta(metadata, name).text = value or None


def keep_first_section(package: Package, package_root: etree._Element) -> None:
    """A form's other sections would show its own text after mdcast's body: drop them."""
    manifest = package_root.find(_opf("manifest"))
    spine = package_root.find(_opf("spine"))
    for item in list(manifest if manifest is not None else []):
        if _SECTION.fullmatch(item.get("href", "")):
            manifest.remove(item)
            for ref in list(spine if spine is not None else []):
                if ref.get("idref") == item.get("id"):
                    spine.remove(ref)
    for name in package.names():
        if _SECTION.fullmatch(name):
            package.remove(name)


def preview_text(paragraphs: list[etree._Element]) -> bytes:
    lines = ["".join("".join(t.itertext()) for t in p.findall(f"{hp('run')}/{hp('t')}")) for p in paragraphs]
    return ("\r\n".join(lines)[:MAX_PREVIEW] + "\r\n").encode("utf-8")


def reset_caret(app_root: etree._Element) -> None:
    for caret in app_root.iter(f"{{{HA}}}CaretPosition"):
        caret.set("listIDRef", "0")
        caret.set("paraIDRef", "0")
        caret.set("pos", "0")
```

- [ ] **Step 4: `src/mdcast/hwpx/writer.py`**

```python
"""``write``: pandoc AST + container + settings → hwpx bytes (spec §4.1)."""

from __future__ import annotations

import panflute as pf

from mdcast.hwpx.container import Package
from mdcast.hwpx.header import Header
from mdcast.hwpx.look import Notice, Notices, Settings
from mdcast.hwpx.meta import apply_metadata, keep_first_section, preview_text, reset_caret
from mdcast.hwpx.page import assemble, find_sec_pr_run
from mdcast.hwpx.section import SectionWriter, hp
from mdcast.hwpx.shapes import build_shapes


def write(doc: pf.Doc, container: bytes, settings: Settings) -> tuple[bytes, list[Notice]]:
    """Raises ``ContainerError`` when ``container`` is not a usable hwpx."""
    package = Package.read(container)
    header = Header(package.xml("Contents/header.xml"))
    section = package.xml("Contents/section0.xml")
    content = package.xml("Contents/content.hpf")
    notices = Notices()
    sec_pr = find_sec_pr_run(section).find(hp("secPr"))
    header.blank_numbering(sec_pr.get("outlineShapeIDRef", "1"))
    shapes = build_shapes(header, settings, notices)
    paragraphs = SectionWriter(header, shapes, settings, notices).build(doc)
    assemble(section, paragraphs, header, shapes, settings)
    apply_metadata(content, settings.metadata)
    keep_first_section(package, content)
    package.set_xml("Contents/header.xml", header.root)
    package.set_xml("Contents/section0.xml", section)
    package.set_xml("Contents/content.hpf", content)
    if "Preview/PrvText.txt" in package.names():
        package.set("Preview/PrvText.txt", preview_text(paragraphs))
    if "settings.xml" in package.names():
        app = package.xml("settings.xml")
        reset_caret(app)
        package.set_xml("settings.xml", app)
    return package.write(), list(notices.items)
```

- [ ] **Step 5: `src/mdcast/hwpx/__init__.py` 를 완성본으로 바꾼다**

```python
"""Standalone OWPML (hwpx) writer: pandoc AST in, hwpx bytes out.

Imports nothing from mdcast outside this package (spec 2026-10-15 §2).
"""

from mdcast.hwpx.container import ContainerError, Package
from mdcast.hwpx.header import Header
from mdcast.hwpx.look import ELEMENTS, Look, Metadata, Notice, PageNumber, PageSetup, Piece, Settings, Slots
from mdcast.hwpx.writer import write

__all__ = [
    "ELEMENTS",
    "ContainerError",
    "Header",
    "Look",
    "Metadata",
    "Notice",
    "Package",
    "PageNumber",
    "PageSetup",
    "Piece",
    "Settings",
    "Slots",
    "write",
]
```

- [ ] **Step 6: 실행 — 통과 확인**

Run: `uv run python -m pytest tests/test_hwpx_write.py tests/test_hwpx_container.py -q`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add src/mdcast/hwpx tests/test_hwpx_write.py
git commit -m "feat(hwpx): write() with metadata, preview text and one section"
```

---

### Task 9: 어댑터와 파이프라인 연결

**Files:**
- Create: `src/mdcast/writers/generator.py`, `src/mdcast/writers/hwpx.py`
- Modify: `src/mdcast/writers/docx/meta.py:20-33,97` (`_custom_values` → `generator_values`)
- Modify: `src/mdcast/pipeline.py:22-28` (WRITERS)
- Modify: `src/mdcast/filters/pagebreak.py:21-26` (`break_block`)
- Modify: `src/mdcast/cli.py:87` (도움말)
- Modify: `src/mdcast/templates/inspect.py` (`validate_template` 에 hwpx 스타일 검사)
- Modify: `tests/test_pipeline.py:40-44`, `tests/test_cli.py:54-58`, `tests/test_no_reject.py`
- Test: `tests/test_writer_hwpx.py`

**Interfaces:**
- Consumes: `mdcast.hwpx.write/Settings/Look/...` (Task 8), `ResolvedTemplate.explicit`, `ResolvedFields.render`, `counters.format_counter`
- Produces: `writers.hwpx.write_hwpx(doc, ctx) -> bytes`; `writers.generator.generator_values(generator) -> dict[str, str]`; 이벤트: 낮춰 출력 → `RENDER_WARNING`(warn, format=hwpx, element), 스타일 없음 → `STYLE_UNMAPPED`(info), 깨진 그릇 → `TEMPLATE_INVALID`(warn)

- [ ] **Step 1: 실패하는 테스트** — `tests/test_writer_hwpx.py`

```python
from helpers import HWPX_NS as NS
from helpers import build, builtin_hwpx, hwpx_integrity, write_template

from mdcast import pipeline
from mdcast.hwpx import Package
from mdcast.report import Codes, Level, Report
from mdcast.templates import validate_template
from mdcast.types import Format, Options, Source
from mdcast.writers.hwpx import write_hwpx


def render(tmp_path, md, template=None):
    doc, ctx = build(tmp_path, md, Format.HWPX, template=template)
    return hwpx_integrity(write_hwpx(doc, ctx)), ctx


def body_para(parts, text):
    for p in parts["Contents/section0.xml"].iter(f"{{{NS['hp']}}}p"):
        if "".join("".join(t.itertext()) for t in p.findall("hp:run/hp:t", NS)) == text:
            return p
    raise AssertionError(text)


def text_char(p):
    """charPrIDRef of the first run holding text (the first paragraph starts with secPr/ctrl runs)."""
    return next(r for r in p.findall("hp:run", NS) if r.find("hp:t", NS) is not None).get("charPrIDRef")


def test_builtin_template_looks(tmp_path):
    parts, _ = render(tmp_path, "---\ntitle: 보고서\n---\n\n# 개요\n\n본문 문단\n")
    head = parts["Contents/header.xml"]
    body = body_para(parts, "본문 문단")
    para = head.find(f".//hh:paraPr[@id='{body.get('paraPrIDRef')}']", NS)
    assert para.find("hh:lineSpacing", NS).get("value") == "180"
    heading = body_para(parts, "개요")
    char = head.find(f".//hh:charPr[@id='{text_char(heading)}']", NS)
    assert char.get("height") == "1600" and char.get("textColor") == "#1F3864"
    header_text = "".join(parts["Contents/section0.xml"].find(".//hp:header", NS).itertext())
    assert "보고서" in header_text
    footer = parts["Contents/section0.xml"].find(".//hp:footer", NS)
    assert [n.get("numType") for n in footer.iter(f"{{{NS['hp']}}}autoNum")] == ["PAGE", "TOTAL_PAGE"]


def test_pagebreak_marker_reaches_hwpx(tmp_path):
    parts, _ = render(tmp_path, "가\n\n<!-- pagebreak -->\n\n나\n")
    assert body_para(parts, "나").get("pageBreak") == "1"


def test_degraded_elements_warn_once(tmp_path):
    _, ctx = render(tmp_path, "| a |\n|---|\n| 1 |\n\n| b |\n|---|\n| 2 |\n")
    events = [(e.code, e.where.get("element")) for e in ctx.report.events if e.where.get("format") == "hwpx"]
    assert events.count((Codes.RENDER_WARNING, "table")) == 1


def test_custom_container_gets_only_explicit_values(tmp_path):
    package = Package.read(builtin_hwpx())
    head = package.xml("Contents/header.xml")
    head.find(".//hh:paraPr[@id='0']/hh:lineSpacing", NS).set("value", "150")
    package.set_xml("Contents/header.xml", head)
    tpl = write_template(tmp_path, "t", "name: t\nelements: {body: {size: 12pt}}\n",
                         {"reference.hwpx": package.write()})
    parts, _ = render(tmp_path, "본문\n", str(tpl))
    body = body_para(parts, "본문")
    head = parts["Contents/header.xml"]
    para = head.find(f".//hh:paraPr[@id='{body.get('paraPrIDRef')}']", NS)
    assert para.find("hh:lineSpacing", NS).get("value") == "150"
    char = head.find(f".//hh:charPr[@id='{text_char(body)}']", NS)
    assert char.get("height") == "1200"


def test_broken_custom_container_falls_back(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\n", {"reference.hwpx": b"junk"})
    parts, ctx = render(tmp_path, "본문\n", str(tpl))
    assert body_para(parts, "본문") is not None
    assert Codes.TEMPLATE_INVALID in [e.code for e in ctx.report.events]


def test_missing_hwpx_style_is_info(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nstyles: {quote: {docx: Block Text, hwpx: 인용문}}\n")
    _, ctx = render(tmp_path, "> 인용\n", str(tpl))
    events = [(e.code, e.level, e.where.get("element")) for e in ctx.report.events if e.where.get("format") == "hwpx"]
    assert (Codes.STYLE_UNMAPPED, Level.INFO, "quote") in events


def test_validate_reports_missing_hwpx_style(tmp_path):
    write_template(tmp_path / ".mdcast" / "templates", "t", "name: t\nstyles: {quote: {hwpx: 인용문}}\n",
                   {"reference.hwpx": builtin_hwpx()})
    _, report = validate_template("t", cwd=tmp_path, home=tmp_path / "home")
    assert [(e.code, e.where.get("format")) for e in report.events if e.code == Codes.STYLE_UNMAPPED] == [
        (Codes.STYLE_UNMAPPED, "hwpx")
    ]


def test_pipeline_writes_hwpx(tmp_path):
    source = Source("# 제목\n\n본문\n".encode(), "doc.md", Format.MD, base_dir=tmp_path)
    result = pipeline.convert(source, [Format.HWPX], options=Options(offline=True, cwd=tmp_path, home=tmp_path))
    output = result.outputs[0]
    assert output.name == "doc.hwpx" and output.data[:2] == b"PK"
    hwpx_integrity(output.data)
    assert not [e for e in result.report.events if e.level is Level.ERROR]
```

참고: `write_template(directory, name, yaml, files)` 는 `tests/helpers.py` 의 기존 함수다 (`directory/name/template.yaml` 과 파일들을 쓰고 그 폴더를 돌려준다).

- [ ] **Step 2: 기존 테스트 고치기**
  - `tests/test_pipeline.py` `test_unsupported_target_fails_only_that_target(tmp_path)` → 인자에 `monkeypatch` 추가하고 첫 줄에 `monkeypatch.delitem(pipeline.WRITERS, Format.HWPX)` (지원하지 않는 대상의 동작을 계속 시험한다).
  - `tests/test_cli.py` `test_unsupported_target_exits_1_but_writes_others(env)` → 인자에 `monkeypatch` 추가, 첫 줄에 `from mdcast import pipeline` 과 `from mdcast.types import Format` 를 import 하고 `monkeypatch.delitem(pipeline.WRITERS, Format.HWPX)`.
  - `tests/test_no_reject.py`: `_convert` 의 대상을 `[Format.DOCX, Format.HWPX, Format.PDF]` 로, 두 곳의 `assert len(result.outputs) == 2` 를 `== 3` 으로, `CASES` 에 `"bad-reference-hwpx": ("name: x\n", {"reference.hwpx": b"not a zip"}, Codes.TEMPLATE_INVALID),` 추가.

- [ ] **Step 3: 실행 — 실패 확인**

Run: `uv run python -m pytest tests/test_writer_hwpx.py tests/test_no_reject.py tests/test_pipeline.py tests/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mdcast.writers.hwpx'` 등

- [ ] **Step 4: `src/mdcast/writers/generator.py`** — `docx/meta.py` 의 `_custom_values` 본문을 옮긴다

```python
"""Generator facts written into every output (spec 2026-10-15 §5.6)."""

from __future__ import annotations

from typing import Any


def generator_values(generator: dict[str, Any]) -> dict[str, str]:
    template = generator.get("template") or {}
    mdcast = generator.get("generator")
    if not mdcast and generator.get("mdcast"):
        mdcast = f"mdcast {generator['mdcast']}"
    values = {
        "mdcast.generator": mdcast,
        "mdcast.template.name": template.get("name"),
        "mdcast.template.version": template.get("version"),
        "mdcast.template.source": template.get("source"),
        "mdcast.pandoc": generator.get("pandoc"),
        "mdcast.typst": generator.get("typst"),
    }
    return {k: str(v) for k, v in values.items() if v not in (None, "")}
```

`src/mdcast/writers/docx/meta.py`: `_custom_values` 함수를 지우고 `from mdcast.writers.generator import generator_values` 를 추가, `_write_custom_properties(d, _custom_values(generator), report)` 를 `_write_custom_properties(d, generator_values(generator), report)` 로.

- [ ] **Step 5: `src/mdcast/writers/hwpx.py`**

```python
"""hwpx writer adapter: template config → hwpx.Settings, notices → report (spec §4.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import panflute as pf

from mdcast import hwpx
from mdcast.counters import format_counter
from mdcast.fields import PageField, ResolvedFields
from mdcast.report import Codes
from mdcast.units import normalize_color, page_size_mm, parse_length_mm, parse_pt, parse_ratio
from mdcast.writers.context import RenderError, WriterContext
from mdcast.writers.generator import generator_values

# what the PDF uses where the built-in template leaves a key empty (spec §4.3), so Hangul's
# blank-document defaults (outline indents, justified text, …) do not leak into the output
NEUTRAL = {
    "bold": False, "italic": False, "color": "#000000", "align": "left", "line_height": 1.3,
    "space_before": 0.0, "space_after": 0.0, "indent_left": 0.0, "keep_with_next": False,
}


def _role(element: str) -> str:
    if element.startswith("heading"):
        return "heading"
    return "code" if element == "code" else "body"


def _color(value: Any) -> str | None:
    color = normalize_color(value)
    return None if color is None else f"#{color}"


def _look(values: dict[str, Any], family: Any, neutral: bool) -> hwpx.Look:
    def get(key: str, convert):
        value = values.get(key)
        return None if value is None else convert(value)

    look = {
        "font": str(family) if family else None,
        "size": get("size", parse_pt),
        "bold": get("bold", bool),
        "italic": get("italic", bool),
        "color": get("color", _color),
        "align": get("align", str),
        "line_height": get("line_height", parse_ratio),
        "space_before": get("space_before", parse_pt),
        "space_after": get("space_after", parse_pt),
        "indent_left": get("indent_left", parse_length_mm),
        "background": get("background", _color),
        "keep_with_next": get("keep_with_next", bool),
    }
    if neutral:
        look.update({key: value for key, value in NEUTRAL.items() if look[key] is None})
    return hwpx.Look(**look)


def _pieces(fields: ResolvedFields, text: str) -> list[hwpx.Piece]:
    return [hwpx.PageNumber(s.kind) if isinstance(s, PageField) else s.value for s in fields.render(text)]


def _slots(spec: dict[str, Any], fields: ResolvedFields) -> hwpx.Slots | None:
    if spec.get("source") == "reference":
        return None

    def slot(key: str) -> tuple[hwpx.Piece, ...]:
        return tuple(_pieces(fields, str(spec.get(key) or "")))

    return hwpx.Slots(slot("left"), slot("center"), slot("right"), str(spec.get("line") or "none"))


def _page(page: dict[str, Any]) -> hwpx.PageSetup:
    width = height = None
    if page.get("size") is not None:
        width, height = page_size_mm(str(page["size"]), "portrait")
    margin = page.get("margin") or {}

    def mm(key: str) -> float | None:
        value = margin.get(key)
        return None if value is None else parse_length_mm(value)

    orientation = page.get("orientation")
    return hwpx.PageSetup(
        width=width, height=height, landscape=None if orientation is None else orientation == "landscape",
        top=mm("top"), bottom=mm("bottom"), left=mm("left"), right=mm("right"),
    )


def _settings(ctx: WriterContext, custom: bool) -> hwpx.Settings:
    config = ctx.template.config
    values = ctx.template.explicit if custom else config
    elements = values.get("elements") or {}
    fonts = values.get("fonts") or {}
    looks = {
        element: _look(elements.get(element) or {}, (fonts.get(_role(element)) or {}).get("family"), not custom)
        for element in hwpx.ELEMENTS
    }
    styles = {
        element: str(mapping["hwpx"])
        for element, mapping in (config.get("styles") or {}).items()
        if isinstance(mapping, dict) and mapping.get("hwpx")
    }
    lists = config["lists"]
    bullets = [str(b) for b in lists["bullet"]] or ["-"]
    ordered = [str(o) for o in lists["ordered"]] or ["1."]

    def marker(is_ordered: bool, level: int, n: int) -> str:
        if is_ordered:
            return format_counter(ordered[min(level, len(ordered)) - 1], n)
        return bullets[min(level, len(bullets)) - 1]

    body = config["elements"]["body"]
    return hwpx.Settings(
        looks=looks,
        styles=styles,
        page=_page(values.get("page") or {}),
        header=_slots(config["header"], ctx.fields),
        footer=_slots(config["footer"], ctx.fields),
        fill=lambda text: _pieces(ctx.fields, text),
        list_marker=marker,
        list_indent=parse_length_mm(lists["indent_per_level"]),
        body_size=parse_pt(body.get("size") or "11pt"),
        body_line_height=parse_ratio(body["line_height"]) if body.get("line_height") is not None else 1.3,
        table_caption_above=(config["tables"]["caption"].get("position") or "above") == "above",
        figure_caption_above=(config["figures"]["caption"].get("position") or "below") == "above",
        metadata=hwpx.Metadata(
            title=ctx.fields.values.get("title", ""),
            author=ctx.fields.values.get("author", ""),
            keywords="mdcast",
            created=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            extra=tuple(generator_values(ctx.generator).items()),
        ),
    )


def _write(doc: pf.Doc, container: bytes, ctx: WriterContext, custom: bool) -> bytes:
    data, notices = hwpx.write(doc, container, _settings(ctx, custom))
    for notice in notices:
        if notice.kind == "style-missing":
            ctx.report.info(Codes.STYLE_UNMAPPED, notice.message, format="hwpx", element=notice.element)
        else:
            ctx.report.warn(Codes.RENDER_WARNING, notice.message, format="hwpx", element=notice.element)
    return data


def write_hwpx(doc: pf.Doc, ctx: WriterContext) -> bytes:
    container = ctx.template.container_for("hwpx")
    if container.source == "custom" and container.path is not None:
        try:
            return _write(doc, container.path.read_bytes(), ctx, custom=True)
        except (hwpx.ContainerError, OSError) as exc:
            ctx.report.warn(
                Codes.TEMPLATE_INVALID,
                f"커스텀 reference.hwpx 를 쓸 수 없어 내장 그릇으로 변환합니다: {exc}",
                format="hwpx",
            )
    builtin = ctx.template.builtin_container("hwpx")
    try:
        return _write(doc, builtin.path.read_bytes(), ctx, custom=False)
    except (hwpx.ContainerError, OSError) as exc:
        raise RenderError(f"내장 hwpx 그릇을 쓸 수 없습니다: {exc}") from exc
```

(Python 3.11 에 `datetime.UTC` 가 있다.)

- [ ] **Step 6: 연결**
  - `src/mdcast/pipeline.py`: `from mdcast.writers.hwpx import write_hwpx` 추가, `WRITERS` 에 `Format.HWPX: write_hwpx,` 추가.
  - `src/mdcast/filters/pagebreak.py` `break_block`: `if target is Format.PDF:` 블록 다음에
    ```python
        if target is Format.HWPX:
            return raw_block("pagebreak", "mdcast-hwpx")  # read by mdcast.hwpx.section
    ```
  - `src/mdcast/cli.py:87`: `help="출력 포맷, 쉼표로 구분 (docx,hwpx,pdf)"`.
  - `src/mdcast/templates/inspect.py`: 맨 위에 `from mdcast import hwpx` 추가, `_check_docx_styles` 다음에 함수 추가, `validate_template` 에서 `_check_docx_styles(tpl, report)` 다음 줄에 `_check_hwpx_styles(tpl, report)` 호출:
    ```python
    def _check_hwpx_styles(tpl: ResolvedTemplate, report: Report) -> None:
        container = tpl.container_for("hwpx")
        if container.source != "custom" or container.path is None:
            return
        try:
            package = hwpx.Package.read(container.path.read_bytes())
            header = hwpx.Header(package.xml("Contents/header.xml"))
            names = {style.get("name") for style in header.root.iter(f"{{{HWPX_HEAD}}}style")}
        except (hwpx.ContainerError, OSError) as exc:
            report.warn(Codes.TEMPLATE_INVALID, f"reference.hwpx 를 읽을 수 없습니다: {exc}", format="hwpx")
            return
        for element, mapping in (tpl.config.get("styles") or {}).items():
            name = (mapping or {}).get("hwpx") if isinstance(mapping, dict) else None
            if name and name not in names:
                report.warn(
                    Codes.STYLE_UNMAPPED,
                    f"hwpx 기준 문서에 스타일 '{name}' ({element}) 이(가) 없습니다 — 변환 시 바탕글을 씁니다",
                    format="hwpx",
                    element=element,
                )
    ```
    그리고 모듈 상단 상수 `HWPX_HEAD = "http://www.hancom.co.kr/hwpml/2011/head"`. (`ResolvedTemplate`, `Report`, `Codes` 가 inspect.py 에 이미 import 되어 있는지 확인하고 없으면 추가.)

- [ ] **Step 7: 실행 — 통과 확인**

Run: `uv run python -m pytest tests/test_writer_hwpx.py tests/test_no_reject.py tests/test_pipeline.py tests/test_cli.py tests/test_filter_pagebreak.py tests/test_docx_styles.py -q`
Expected: PASS

- [ ] **Step 8: 전체 테스트**

Run: `uv run python -m pytest -q`
Expected: 모두 통과 (기존 347 + 새 테스트, skip 은 opt-in 표시만)

- [ ] **Step 9: 커밋**

```bash
git add src/mdcast/writers src/mdcast/pipeline.py src/mdcast/filters/pagebreak.py src/mdcast/cli.py src/mdcast/templates/inspect.py tests
git commit -m "feat: hwpx output in the pipeline (template looks, fallbacks, validation)"
```

---

### Task 10: 한글 COM 검증, 렌더 스크립트, README

**Files:**
- Modify: `tests/conftest.py` (`--run-hangul`)
- Modify: `tests/helpers.py` (`char_origin`, `line_starts`)
- Create: `tests/test_hangul.py`
- Modify: `scripts/render_pages.py` (hwpx → 한글 → PDF)
- Modify: `README.md`

**Interfaces:**
- Consumes: 파이프라인(Task 9), `helpers.line_pitch`
- Produces: `helpers.char_origin(pdf, needle, page=0) -> (x_mm, y_mm)`, `helpers.line_starts(pdf, needle) -> list[(x_mm, y_mm)]`; `--run-hangul` opt-in

- [ ] **Step 1: `tests/conftest.py`** — `OPT_IN` 에 `"hangul": "--run-hangul"` 추가, `pytest_addoption` 에
  `parser.addoption("--run-hangul", action="store_true", help="run Hancom Office (Hangul) COM tests (Windows + Hangul)")` 추가.

- [ ] **Step 2: `tests/helpers.py` 에 덧붙임**

```python
def _pdf_chars(data: bytes, page: int = 0):
    import ctypes

    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    pdf_page = pdfium.PdfDocument(data)[page]
    textpage = pdf_page.get_textpage()
    height = pdf_page.get_height()
    x, y = ctypes.c_double(), ctypes.c_double()
    chars = []
    for i in range(pdfium_c.FPDFText_CountChars(textpage.raw)):
        pdfium_c.FPDFText_GetCharOrigin(textpage.raw, i, ctypes.byref(x), ctypes.byref(y))
        ch = chr(pdfium_c.FPDFText_GetUnicode(textpage.raw, i) or 0xFFFD)
        chars.append((ch, x.value * 25.4 / 72, (height - y.value) * 25.4 / 72))
    return chars


def char_origin(data: bytes, needle: str, page: int = 0) -> tuple[float, float]:
    """Baseline origin (x, y from the top-left, mm) of the first character of ``needle``."""
    chars = _pdf_chars(data, page)
    text = "".join(ch for ch, _, _ in chars)
    _, x, y = chars[text.index(needle)]
    return x, y


def line_starts(data: bytes, needle: str, page: int = 0) -> list[tuple[float, float]]:
    """(x, y) mm of the first visible character of each line from ``needle`` on."""
    chars = _pdf_chars(data, page)
    text = "".join(ch for ch, _, _ in chars)
    starts: list[tuple[float, float]] = []
    for ch, x, y in chars[text.index(needle):]:
        if ch.strip() and (not starts or abs(y - starts[-1][1]) > 1.0):
            starts.append((x, y))
    return starts
```

- [ ] **Step 3: `tests/test_hangul.py`**

```python
"""Hancom Office checks (spec §8.3): run with --run-hangul on Windows with Hangul installed.

Without the security module registered (README), Hangul asks to allow file access on each run.
"""

import re
from pathlib import Path

import pytest
from helpers import char_origin, line_pitch, line_starts

from mdcast import pipeline
from mdcast.types import Format, Options, Source

pytestmark = pytest.mark.hangul
FIXTURES = Path(__file__).parent / "fixtures" / "md"
LONG = "줄 간격을 보기 위해 충분히 긴 문장을 씁니다. " * 6


@pytest.fixture(scope="module")
def hangul():
    win32 = pytest.importorskip("win32com.client")
    try:
        hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    except Exception as exc:  # noqa: BLE001 - COM errors are pywintypes.com_error
        pytest.skip(f"한글을 실행할 수 없습니다: {exc}")
    hwp.XHwpWindows.Item(0).Visible = True
    if not hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule"):
        print("한글 보안 모듈이 등록되지 않아 '접근 허용' 대화상자가 뜹니다 (README 참고)")
    yield hwp
    hwp.Clear(1)
    hwp.Quit()


def convert(tmp_path: Path, md: str, name: str = "doc") -> tuple[Path, bytes]:
    source = Source(md.encode("utf-8"), f"{name}.md", Format.MD, base_dir=tmp_path)
    result = pipeline.convert(source, [Format.HWPX, Format.PDF],
                              options=Options(offline=True, cwd=tmp_path, home=tmp_path / "home"))
    outputs = {o.format: o.data for o in result.outputs}
    path = tmp_path / f"{name}.hwpx"
    path.write_bytes(outputs[Format.HWPX])
    return path, outputs[Format.PDF]


def through_hangul(hwp, path: Path) -> tuple[str, bytes]:
    assert hwp.Open(str(path.resolve()), "HWPX", ""), f"한글이 {path.name} 을(를) 열지 못했습니다"
    text = hwp.GetTextFile("UNICODE", "")
    pdf = path.with_suffix(".hangul.pdf")
    assert hwp.SaveAs(str(pdf.resolve()), "PDF", "")
    hwp.Clear(1)
    return text, pdf.read_bytes()


@pytest.mark.parametrize("name", ["kitchen-sink", "edge-cases", "korean-report"])
def test_hangul_opens_fixture(hangul, tmp_path, name):
    md = (FIXTURES / f"{name}.md").read_text(encoding="utf-8")
    path, _ = convert(tmp_path, md, name)
    text, pdf = through_hangul(hangul, path)
    words = re.findall(r"[가-힣]{2,}", md)
    assert text.strip() and words and words[0] in text
    assert pdf.startswith(b"%PDF")


def test_line_pitch_matches_the_pdf(hangul, tmp_path):
    md = f"# 제목{LONG}\n\n본문{LONG}\n\n- 목록{LONG}\n\n```\n코드 첫째 줄\n코드 둘째 줄\n```\n"
    path, mdcast_pdf = convert(tmp_path, md)
    _, hangul_pdf = through_hangul(hangul, path)
    for needle in ("제목", "본문", "목록", "코드 첫째"):
        assert line_pitch(hangul_pdf, needle) == pytest.approx(line_pitch(mdcast_pdf, needle), rel=0.005), needle


def test_text_columns(hangul, tmp_path):
    md = f"# 제목\n\n본문 문단\n\n- 목록{LONG}\n"
    path, mdcast_pdf = convert(tmp_path, md)
    _, hangul_pdf = through_hangul(hangul, path)
    for needle in ("제목", "본문"):
        assert char_origin(hangul_pdf, needle)[0] == pytest.approx(char_origin(mdcast_pdf, needle)[0], abs=0.5)
    first_text = char_origin(hangul_pdf, "목록")[0]
    wrapped = line_starts(hangul_pdf, "목록")[1][0]
    assert first_text == pytest.approx(wrapped, abs=0.5)


def test_header_footer_and_first_line_positions(hangul, tmp_path):
    md = "---\ntitle: 머리말제목\n---\n\n본문첫줄\n"
    path, mdcast_pdf = convert(tmp_path, md)
    _, hangul_pdf = through_hangul(hangul, path)
    assert char_origin(hangul_pdf, "머리말제목")[1] == pytest.approx(char_origin(mdcast_pdf, "머리말제목")[1], abs=1.0)
    assert char_origin(hangul_pdf, "/")[1] == pytest.approx(char_origin(mdcast_pdf, "/")[1], abs=1.0)
    # known difference (spec §6.1): Hangul puts a line's extra height below the text
    expected = -((1.8 - 1) / 2 - 0.05) * 11 * 25.4 / 72
    shift = char_origin(hangul_pdf, "본문첫줄")[1] - char_origin(mdcast_pdf, "본문첫줄")[1]
    assert shift == pytest.approx(expected, abs=0.5)
```

- [ ] **Step 4: 실행** — 사용자에게 알린 뒤 (`dangerouslyDisableSandbox: true`)

Run: `uv run python -m pytest tests/test_hangul.py --run-hangul -q -s`
Expected: PASS. 실패하면 측정값을 읽고 spec §6.1·부록 A 의 모형과 비교해 원인을 찾는다 (예: 꼬리말 `prev` 가 머리말 영역 첫 문단에 적용되지 않으면 꼬리말 기준선이 어긋난다 → `layout`/`assemble` 수정과 spec 갱신을 ledger 에 Ruling 으로 기록).

- [ ] **Step 5: `scripts/render_pages.py`** — `docx_to_pdf_with_word` 다음에 함수 추가, `main` 에 분기 추가

```python
def hwpx_to_pdf_with_hangul(hwpx_path: Path) -> Path:
    try:
        import win32com.client as win32
    except ImportError as exc:
        raise ConverterMissing(
            "hwpx 렌더링에는 Windows 와 pywin32, 한글이 필요합니다 "
            "(hwpx rendering needs Windows, pywin32 and Hancom Office)"
        ) from exc

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
```

`main` 의 `elif path.suffix.lower() == ".docx":` 다음에:

```python
            elif path.suffix.lower() == ".hwpx":
                pages = render_pdf(hwpx_to_pdf_with_hangul(path), path.stem + "-hwpx")
```

모듈 docstring 둘째 문장에 "hwpx is exported to PDF with Hancom Office via COM the same way." 를 덧붙인다.

- [ ] **Step 6: README** — 다음을 반영한다.
  - 첫 줄 아래 설명: `(M1: MD → docx, pdf · M2a: MD → hwpx)`
  - 사용 예: `uv run mdcast convert 보고서.md --to docx,hwpx,pdf`
  - 새 절 `## hwpx 출력 (M2a)`:
    ```markdown
    ## hwpx 출력 (M2a)

    - 내장 그릇은 한글 빈 문서입니다. 템플릿에 `reference.hwpx` 를 두면 그 문서의 스타일·쪽 설정을 쓰고 yaml 에 적은 값만 덮어씁니다.
    - 스타일 매핑은 `styles.<요소>.hwpx` (기본: 제목 → "개요 N", 본문·인용·코드 → "바탕글", 캡션 → "캡션", 각주 → "각주"). 한글 개요 번호는 끄고 mdcast 번호 설정을 씁니다.
    - 개조식 목록 기호는 글자로 들어갑니다 (한글에서 항목을 끼워 넣어도 번호가 자동으로 바뀌지 않음).
    - M2b 전까지: 표는 행마다 한 문단(" | " 구분), 이미지는 `[이미지: 설명]`, 각주는 문서 끝에 모아 씁니다. 수식은 LaTeX 원문(M4 에서 이미지).
    - 알려진 차이: 한글은 줄의 남는 높이를 글자 아래에 둡니다. 줄 간격은 같지만 본문 줄이 PDF 보다 약 1.4mm 위에 놓입니다.
    ```
  - `## 테스트` 에 `uv run python -m pytest tests/test_hangul.py --run-hangul   # 한글로 열기·줄 간격·위치 비교 (Windows + 한글, 선택)` 와 `uv run python scripts/render_pages.py out.hwpx   # 한글 → PDF → PNG`
  - 새 절 `## 개발: 한글 COM 보안 모듈 (선택)`:
    ```markdown
    ## 개발: 한글 COM 보안 모듈 (선택)

    한글 자동화(테스트, 렌더 스크립트)는 파일에 접근할 때마다 "접근 허용" 을 묻습니다. 무인으로 돌리려면 한컴 개발자 사이트(developer.hancom.com)의 보안 모듈 `FilePathCheckerModuleExample.dll` 을 받아 두고, 레지스트리 `HKEY_CURRENT_USER\Software\HNC\HwpAutomation\Modules` 에 문자열 값 `FilePathCheckerModule` = DLL 전체 경로(따옴표 없이)를 넣습니다. mdcast 사용자에게는 필요 없습니다.
    ```
  - `## M1 에서 미룬 항목` 아래에 `## M2a 에서 미룬 항목`: "표·이미지·각주(M2b), 한글 고유 번호 목록, 문서 안 링크 책갈피, 다른 한글 버전 그릇 시험".

- [ ] **Step 7: 전체 테스트 + 시각 확인 준비**

Run: `uv run python -m pytest -q`
Expected: 모두 통과

Run (사용자에게 알린 뒤, `dangerouslyDisableSandbox: true`):
`uv run mdcast convert tests/fixtures/md/kitchen-sink.md --to hwpx,pdf --out-dir .test-output/m2a --offline` 후
`uv run python scripts/render_pages.py .test-output/m2a/kitchen-sink.hwpx .test-output/m2a/kitchen-sink.pdf`
Expected: `.test-output/pages/kitchen-sink-hwpx/` 와 `kitchen-sink-pdf/` 의 PNG. 사용자에게 보여 주고 승인을 받는다 (spec §8.4). 링크 클릭 이동도 사용자가 한글에서 확인한다.

- [ ] **Step 8: 커밋**

```bash
git add tests/conftest.py tests/helpers.py tests/test_hangul.py scripts/render_pages.py README.md
git commit -m "test(hwpx): Hangul COM checks, page rendering and README"
```
