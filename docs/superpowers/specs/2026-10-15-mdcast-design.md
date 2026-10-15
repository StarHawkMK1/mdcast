# mdcast 설계 스펙

- 작성일: 2026-10-15
- 상태: 검토 대기
- 한 줄 설명: **mdcast — Markdown ↔ docx · hwpx · pdf, 템플릿 기반 변환기**

---

## 0. 배경과 목표

### 0.1 목적
- **내보내기**: MD 문서를 정해진 템플릿에 맞춰 docx / hwpx / pdf 로 만든다.
- **가져오기**: docx / hwpx / pdf 를 MD 로 바꾼다.
- 특정 AI 에이전트에 종속되지 않는다. Claude Code, Codex, Cursor, Copilot, Gemini CLI, Antigravity, qwen-code 등 누가 무엇을 쓸지 모른다.

### 0.2 사용 단계
1. 개인 시험 (작성자 본인)
2. 사내 공유 (사용성 검증 후)
3. 오픈소스 공개 (회사 승인 후)

### 0.3 핵심 원칙
| 원칙 | 의미 |
|---|---|
| MD 허브 | 모든 변환은 MD(정확히는 pandoc AST)를 중심으로 한다. docx↔hwpx 직접 변환은 목표가 아니며 AST 경유로 부수적으로 제공된다 |
| 무거부 | 템플릿·내용 문제로 변환을 거부하지 않는다. 항상 결과물을 만들고 대체 내역을 알린다 |
| 관측성 | 적용된 템플릿(내장/커스텀)과 모든 대체를 CLI·MCP·결과 파일 메타데이터로 보여준다 |
| 로컬 처리 | 변환은 사용자 PC에서 실행된다. 문서는 PC 밖으로 나가지 않는다 |
| 모양의 단일 원천 | 문서의 시각적 모양은 `template.yaml` 이 정의한다. 기준 문서는 그릇이다 |

### 0.4 PDF 품질 기준
"같은 회사 양식으로 보이면 충분" — 글꼴·여백·머리말/꼬리말·개조식 기호·표 모양이 같으면 되고, 줄바꿈·쪽 나뉨의 세부 차이는 허용한다. PDF 는 MD 에서 Typst 로 **직접** 렌더링한다(Office 불필요).

---

## 1. 범위

### 1.1 v1 포함
- 포맷: MD, docx, hwpx, pdf (내보내기·가져오기 양방향)
- MD 요소: 제목, 문단, 강조, 목록, 링크, 표(셀 병합 포함), 이미지, 각주, 코드 블록, 수식(LaTeX), Mermaid, PlantUML
- 템플릿: 내장 default + 사용자 템플릿, `extends` 1단계 상속, `template init/validate/describe/list`
- 쪽 나눔: 명시적 마커 `<!-- pagebreak -->` + 제목 규칙
- 인터페이스: CLI, 로컬 MCP(stdio), Skill
- `doctor` 진단

### 1.2 v1 제외 (향후 후보)
| 항목 | 비고 |
|---|---|
| pptx, html 포맷 | 리더/라이터 모듈 추가로 확장 가능하도록 구조만 대비 |
| 스캔 PDF OCR | 스캔본은 경고만 (`PDF_SCANNED_SUSPECTED`) |
| 구 바이너리 .hwp | hwpx 만 지원 |
| hwpx 네이티브 수식 | v1 은 이미지 + LaTeX 보존. LaTeX→한글 수식 스크립트 변환은 향후 |
| 원격 MCP 서버 | 향후 "내보내기 전용 원격 MCP" 후보. 부록 A 참고 |
| `---`/`-----` 구분선을 쪽 나눔으로 쓰는 옵션 | **v1 에 넣지 않는다.** 포맷터가 구분선을 정규화해 쪽 나눔이 소실될 위험 때문 |
| 다단계 `extends`, `template add <git-url>`, 표지 페이지, 클라이언트별 설정 자동 작성 | YAGNI |

---

## 2. 아키텍처

### 2.1 전체 흐름
```
            ┌──────────── readers ────────────────────────┐
 MD   ──────┤ md   : pandoc MD 파서                        │
 docx ──────┤ docx : pandoc docx reader + 역변환 후처리    ├──▶ pandoc AST
 hwpx ──────┤ hwpx : 자체 OWPML 파서                       │       │
 pdf  ──────┤ pdf  : pdfplumber 추출 → MD → AST            │       ▼
            └──────────────────────────────────────────────┘   filters
                                                               (고정 순서)
                    templates ──▶ 해석된 템플릿                     │
            ┌──────────── writers ────────────────────────┐       │
 docx ◀─────┤ pandoc docx + 패치된 reference.docx → 후처리 │◀──────┘
 hwpx ◀─────┤ 자체 OWPML 생성 (reference.hwpx 그릇 재사용) │
 pdf  ◀─────┤ pandoc typst writer + pdf.typ → typst 컴파일 │
 MD   ◀─────┤ pandoc MD writer (병합 셀 표는 HTML)        │
            └──────────────────────────────────────────────┘
```

### 2.2 핵심 API — 바이트 입출력
경로는 껍데기(CLI, stdio MCP)만 다룬다. 핵심 API 는 바이트를 주고받는다. 이렇게 해두면 나중에 원격 모드를 추가할 때 코어를 바꿀 필요가 없다.

```python
convert(
    source: Source,              # bytes + 파일명 + 포맷
    targets: list[Format],       # docx | hwpx | pdf | md
    template: TemplateRef | None,
    options: Options,            # offline, keep_temp, timeouts ...
) -> Result                      # outputs: list[Output(format, name, bytes, assets)], report: Report
```
- 여러 타깃 중 일부가 실패해도 나머지는 생성한다.
- 모든 구성요소는 경고를 직접 출력하지 않고 `Report` 에 기록만 한다.

### 2.3 구성요소
| 모듈 | 책임 | 의존 |
|---|---|---|
| `pipeline` | `convert()` — reader → filters → writer 조립 | 아래 전부 |
| `ast` | pandoc 실행, AST JSON 입출력, 헬퍼 | pypandoc-binary, panflute(BSD-3) |
| `readers/{md,docx,hwpx,pdf}` | 포맷 → AST | pandoc / `hwpx` / pdfplumber |
| `filters/*` | 기능 하나당 필터 하나 (§4.1) | panflute, 다이어그램 렌더러(선택) |
| `writers/{docx,hwpx,pdf,md}` | AST → 포맷, 머리말/꼬리말·메타데이터 | pandoc, typst(Apache-2.0), `hwpx` |
| `hwpx/` | **독립 하위 패키지.** OWPML 읽기/쓰기. pandoc AST 만 입출력으로 안다 | lxml |
| `templates` | 템플릿 해석(탐색·상속·폴백), 스키마 검증, init | — |
| `report` | 템플릿 출처·이벤트 수집 | — |
| `doctor` | 환경 진단 | — |
| `cli` / `mcp_server` / `skill/` | 얇은 껍데기 | click(BSD), mcp Python SDK(MIT) |

경계 규칙:
- writers 는 템플릿 파일을 직접 탐색하지 않는다. `templates` 가 해석한 결과만 받는다. 폴백 판단은 `templates` 한 곳에서만 일어난다.
- `hwpx/` 는 mdcast 의 다른 모듈을 import 하지 않는다. 향후 별도 라이브러리로 분리할 수 있게 한다.

### 2.4 저장소 구조
```
mdcast/
├── src/mdcast/
│   ├── pipeline.py  ast.py  report.py  doctor.py  cli.py  mcp_server.py
│   ├── readers/  filters/  writers/
│   ├── hwpx/
│   ├── templates/                 # 해석·검증·init 코드
│   └── builtin_templates/default/ # 중립 내장 템플릿
├── skill/SKILL.md
├── tests/
│   ├── fixtures/  golden/  corpus/
├── docs/
├── THIRD_PARTY_LICENSES/
└── pyproject.toml
```
기술 기준: Python 3.11+, uv, 라이선스 Apache-2.0.

---

## 3. 템플릿 체계

### 3.1 템플릿 묶음
```
<template>/
├── template.yaml    # 필수. 모양의 단일 원천
├── reference.docx   # 선택. docx 그릇: 스타일 이름·틀, 쪽 설정, (source: reference 시) 머리말/꼬리말
├── reference.hwpx   # 선택. hwpx 그릇
└── pdf.typ          # 선택. 생략 시 내장 범용 pdf.typ 가 yaml 값을 읽어 렌더링
```
- **reference.docx / .hwpx 는 "견본 문서"(데이터)**다. 복사해서 본문을 채운다.
- **pdf.typ 는 "그리기 규칙"(Typst 코드)**이다. PDF 는 스타일 개념이 없는 최종 출력물이라 견본 PDF 를 템플릿으로 쓸 수 없다. 사용자가 pdf.typ 를 직접 쓰는 경우는 yaml 로 표현할 수 없는 특수 디자인(그래픽 표지, 2단, 워터마크)뿐이다.

### 3.2 `template.yaml` 통합 스키마 (schema 1)
```yaml
schema: 1
name: company-report
version: 1.2.0
description: 회사 보고서 양식
extends: default                 # 선택. 1단계만. 순환 감지

files:                           # 선택. 생략 시 관례 파일명
  docx: reference.docx
  hwpx: reference.hwpx
  pdf:  pdf.typ

page:
  size: A4                       # A4 | Letter | ...
  orientation: portrait
  margin: { top: 20mm, bottom: 15mm, left: 20mm, right: 20mm }

fonts:
  body:    { family: "맑은 고딕", fallback: ["Noto Sans KR"] }
  heading: { family: "맑은 고딕", fallback: ["Noto Sans KR"] }
  code:    { family: "D2Coding",  fallback: ["Noto Sans Mono"] }

elements:                        # 모양 정의 (단일 원천)
  heading1: { size: 16pt, bold: true, color: "#1F3864", space_before: 12pt, space_after: 6pt, keep_with_next: true }
  heading2: { size: 14pt, bold: true, space_before: 10pt, space_after: 4pt, keep_with_next: true }
  # heading3 ~ heading6 동일 형식
  body:     { size: 11pt, line_height: 160%, space_after: 4pt, align: justify }
  quote:    { size: 10.5pt, color: "#555555", indent_left: 5mm }
  code:     { size: 9.5pt, background: "#F6F8FA" }
  caption:  { size: 9.5pt, bold: true, align: center }
  footnote: { size: 9pt }

styles:                          # 요소 → 그릇 안의 스타일 이름
  heading1: { docx: "Heading 1", hwpx: "개요 1" }
  heading2: { docx: "Heading 2", hwpx: "개요 2" }
  body:     { docx: "Body Text", hwpx: "본문" }
  quote:    { docx: "Block Text", hwpx: "인용" }
  code:     { docx: "Source Code", hwpx: "코드" }
  table:    { docx: "Table", hwpx: "기본 표" }
  caption:  { docx: "Caption", hwpx: "캡션" }

headings:
  numbering: ["Ⅰ.", "1.", "가."] # 선택. 생략 시 번호 없음

lists:                           # 개조식
  bullet:  ["□", "○", "-", "·"]
  ordered: ["1.", "가.", "1)", "가)", "(1)", "(가)"]
  indent_per_level: 5mm

tables:
  width: full                    # full | auto
  font_size: 10pt
  cell_padding: 1.5mm
  border:       { width: 0.5pt, color: "#000000" }
  border_outer: { width: 1pt }
  header: { background: "#F2F2F2", bold: true, align: center, valign: middle, repeat: true }
  body:   { align: left, valign: middle, zebra: null }   # MD 열 정렬(:---:)이 우선
  first_column: { bold: false, background: null }
  caption: { position: above, format: "<표 {n}> {text}" }
  variants:                      # 선택. MD 에서 <!-- table: 이름 --> 으로 지정
    plain:   { header: { background: null, bold: false }, border_outer: { width: 0.5pt } }

figures:
  max_width: 100%
  align: center
  caption: { position: below, format: "[그림 {n}] {text}" }

header:
  source: yaml                   # yaml(기본) | reference
  left: "{{dept}}"
  center: ""
  right: "{{security}}"
  line: below                    # none | below
  logo: { file: logo.png, position: left, height: 8mm }   # 선택
footer:
  source: yaml
  left: ""
  center: "{{page}} / {{pages}}"
  right: ""
  line: none

fields:
  defaults: { security: "" }
  date_format: "YYYY-MM-DD"

layout:
  page_break: { before: [h1], skip_first: true }   # before: [] | [h1] | [h2] | [h1, h2]
```

### 3.3 값 결정 우선순위
- 모양: `template.yaml` → (상위 템플릿 yaml) → 그릇의 스타일 값 → 내장 default
- 문서별 덮어쓰기: frontmatter → 템플릿 → 내장 default (현재 `page_break` 만 frontmatter 로 덮어쓸 수 있음)
- 변환 시 yaml 값은 **그릇의 스타일 정의 자체에 덮어쓴다**(문단마다 직접 서식 X). 결과 문서에서 스타일을 수정하면 문서 전체에 반영된다.

### 3.4 머리말·꼬리말과 필드
- `source: yaml`(기본): 세 포맷 모두 yaml 의 left/center/right 정의로 생성한다. 세 결과물이 동일하다.
- `source: reference`: docx/hwpx 는 그릇의 머리말/꼬리말을 그대로 쓰고 그 안의 `{{키}}` 만 채운다. PDF 는 yaml 슬롯으로 그리고 `PDF_HEADER_SIMPLIFIED`(warn) 를 기록한다.
- **필드 채움 우선순위**: frontmatter 값 → `fields.defaults` → 빈칸(`FIELD_EMPTY`, info)
- **예약 키** (frontmatter 로 덮어쓸 수 없음. 시도 시 `FIELD_RESERVED`, info):

| 키 | 의미 | 구현 |
|---|---|---|
| `{{page}}` | 현재 쪽 | 각 포맷 네이티브 쪽 번호 필드 (docx `PAGE`, hwpx 쪽 번호 컨트롤, Typst `counter(page)`) |
| `{{pages}}` | 전체 쪽 수 | 네이티브 필드 (docx `NUMPAGES` 등) |
| `{{today}}` | 변환 일자 | 변환 시점 문자열, `fields.date_format` 적용 |

- 그 외 키는 자유. `describe_template` 이 템플릿에서 발견한 키 목록을 돌려준다.

### 3.5 템플릿 해석
- 선택 우선순위: 명시 인자(`--template`, MCP 인자) → frontmatter `template:` → 내장 `default`
- 탐색 위치: 경로 → `./.mdcast/templates/<이름>/` → `~/.mdcast/templates/<이름>/` → 내장
- **폴백 규칙 (무거부)**:

| 상황 | 동작 | 이벤트 |
|---|---|---|
| 지정 템플릿을 찾지 못함 | 내장 default 로 전체 변환 | `TEMPLATE_NOT_FOUND` (warn) |
| yaml 파싱 실패 / 스키마 위반 | 해당 키 무시 후 상위 → default 값 사용 | `TEMPLATE_INVALID` (warn) |
| 특정 포맷 그릇 누락 (예: reference.hwpx 없음) | **그릇만** 상위 → 내장 것을 쓰고, **모양(yaml)은 커스텀 것을 그대로 적용** | `TEMPLATE_CONTAINER_FALLBACK` — `header.source: reference` 인 경우 warn(머리말 유실), 아니면 info |
| 스타일 매핑 누락 | 해당 요소 default 스타일 | `STYLE_UNMAPPED` (info) |
| 모르는 frontmatter 키 | 무시 | 없음 |

### 3.6 템플릿 명령
| 명령 | 동작 |
|---|---|
| `mdcast template list` | 사용 가능한 템플릿과 출처(내장/사용자/프로젝트) |
| `mdcast template describe <이름>` | 필드 키 목록, 지원 포맷, 폴백 예정 항목 |
| `mdcast template validate <경로>` | 스키마·파일·그릇 내 스타일 존재·필드 키·폰트 설치 점검. 경고만, 실패 없음 |
| `mdcast template init --from <문서.docx> [--from <문서.hwpx>]` | 문서를 그릇으로 복사(본문 비움), 쪽 설정·폰트·스타일 값을 yaml 로 추출, 스타일 매핑 추정, 미매핑 항목 안내. 머리말 고정 문구를 필드로 바꾸는 작업은 사용자에게 안내만 한다 |

### 3.7 내장 default 템플릿
- 작성자가 실제 default 템플릿을 제공하기 전까지 중립 스타터를 둔다: A4, 개조식 기호, 쪽 번호.
- 폰트: docx/hwpx 는 **맑은 고딕**(이름만 기록하므로 재배포 문제 없음). PDF 는 시스템 맑은 고딕을 쓰고, 없으면 동봉 **Noto Sans KR(OFL)** 로 대체(`FONT_FALLBACK`, warn).
- 공개 저장소에는 중립 템플릿만 둔다. 회사 템플릿은 별도 비공개 저장소에 두고 `~/.mdcast/templates/` 로 받아 쓴다.

---

## 4. 변환 흐름

### 4.1 내보내기 (MD → docx / hwpx / pdf)
1. frontmatter 읽기 (`template`, 필드 값, `page_break`)
2. 템플릿 해석 (§3.5) → 리포트에 출처 기록
3. pandoc 으로 MD → AST. 확장: GFM 표, 각주, `$수식$`, raw HTML(병합 셀 표·마커), YAML 메타데이터, 속성 문법
4. 필터 (고정 순서):
   1. `pagebreak` — `<!-- pagebreak -->` 마커 + `layout.page_break` 제목 규칙
   2. `table-variant` — `<!-- table: 이름 -->` 을 다음 표에 부착
   3. `diagrams` — Mermaid/PlantUML 코드 블록 → 이미지(캐시), **원본 코드를 대체 텍스트에 보존**. 렌더러 없음 → 코드 블록 유지 + `DIAGRAM_RENDERER_MISSING`(warn)
   4. `math` — docx·pdf 는 네이티브. **hwpx 는 Typst+mitex 로 렌더링한 이미지로 대체하고 원본 LaTeX 를 대체 텍스트에 보존** (`MATH_AS_IMAGE`, info)
   5. `numbering` — 제목 번호, 개조식 단계, 표·그림 캡션 번호
5. writer:
   - **docx**: reference.docx 임시 사본에 yaml 값을 스타일 정의로 덮어씀 → pandoc docx (`--reference-doc`) → XML 후처리(머리말/꼬리말, `numbering.xml` 의 개조식·제목 번호, 표 스타일 조건부 서식(머리글 행), 메타데이터)
   - **hwpx**: reference.hwpx 압축 해제 → `header.xml` 에 yaml 값 반영(글자 모양·문단 모양·테두리/배경·번호 정의) → AST 로 `section0.xml` 생성(표는 셀 단위 테두리/배경·글자 모양 지정) → 머리말/꼬리말·메타데이터 → 재압축
   - **pdf**: pandoc typst writer → 내장(또는 템플릿) pdf.typ 가 yaml 값을 읽어 레이아웃 적용 → typst 컴파일. 폰트 경로: 시스템 + 동봉
6. 리포트 반환

### 4.2 가져오기 (docx / hwpx / pdf → MD)
| 입력 | 처리 |
|---|---|
| docx | pandoc docx reader, 이미지 추출. mdcast 가 만든 문서면(메타데이터) 해당 템플릿 스타일 매핑을 역적용 |
| hwpx | 자체 OWPML 파서: 개요 수준 → 제목, 표(병합 셀), 이미지, 각주. 한글 네이티브 수식은 코드 블록으로 보존(`HWPX_EQUATION_PRESERVED`, warn). mdcast 가 넣은 수식 이미지는 대체 텍스트의 LaTeX 로 복원 |
| pdf | pdfplumber: 글자 크기·굵기 군집으로 제목 수준 추정, 표·이미지 추출, 쪽마다 반복되는 머리말/꼬리말 제거. 다단 또는 스캔본 의심 시 warn. 텍스트 PDF 만 대상 |

공통 역변환 필터:
- 쪽 나눔 → `<!-- pagebreak -->`
- 대체 텍스트에 원본 코드가 있는 이미지 → Mermaid/PlantUML 코드 블록 / LaTeX 수식 복원
- 템플릿이 붙인 제목 번호(`Ⅰ.`)·캡션 접두어(`<표 1>`) 제거
- **개조식 휴리스틱 (기본 켬)**: 사람이 직접 타이핑한 `□ ○ - ·` 문단을 기호 순서에 따라 MD 목록 단계로 변환

MD 출력: GFM + 각주 + `$수식$` + frontmatter. 병합 셀 표는 HTML `<table>`. 결과: `<이름>.md` + `<이름>_assets/`.

### 4.3 간접 변환
AST 경유로 `docx → hwpx` 등이 부수적으로 가능하다. 원본 서식은 버리고 템플릿 양식으로 재생성되며, 이를 리포트에 info 로 표시한다.

### 4.4 MD 작성 규칙 (Skill 에 수록)
- frontmatter: `template`, 템플릿 필드 키(`describe_template` 으로 확인), 선택적 `page_break`
- 쪽 나눔: `<!-- pagebreak -->`
- 표 종류: 표 바로 위 `<!-- table: 이름 -->`
- 병합 셀: HTML `<table>` + `rowspan`/`colspan`
- 수식: `$...$`, `$$...$$`
- 다이어그램: ```` ```mermaid ````, ```` ```plantuml ````

---

## 5. 오류·대체 처리와 관측성

### 5.1 이벤트 수준
| 수준 | 의미 | 결과물 |
|---|---|---|
| ⛔ error | 결과물을 만들 수 없음 (입력 파일 손상, 출력 경로 쓰기 불가) | 해당 포맷만 미생성 |
| ⚠ warn | 생성했지만 사용자 의도와 다를 수 있음 | 생성 |
| ℹ info | 예상된 범위의 대체 | 생성 |

종료 코드: 성공(경고 포함) `0`, 결과물 중 하나라도 error 면 `1`.

### 5.2 리포트 구조
```yaml
input:   { name: 보고서.md, format: md }
outputs:
  - { format: docx, name: 보고서.docx, status: ok }        # ok | degraded | failed
  - { format: hwpx, name: 보고서.hwpx, status: degraded }
template:
  name: company-report
  version: 1.2.0
  source: custom                                         # builtin | custom
  location: ./.mdcast/templates/company-report
  per_format:
    docx: { container: custom,  styles: custom }
    hwpx: { container: builtin, styles: custom }         # 그릇만 폴백
    pdf:  { container: builtin, styles: custom }         # 내장 pdf.typ + 커스텀 yaml
events:
  - { level: info, code: TEMPLATE_CONTAINER_FALLBACK, message: "...", where: { format: hwpx } }
  - { level: warn, code: DIAGRAM_RENDERER_MISSING, message: "...", where: { element: plantuml, line: 42 } }
```
이벤트 코드(안정 식별자): `TEMPLATE_NOT_FOUND`, `TEMPLATE_INVALID`, `TEMPLATE_CONTAINER_FALLBACK`, `STYLE_UNMAPPED`, `FIELD_EMPTY`, `FIELD_RESERVED`, `DIAGRAM_RENDERER_MISSING`, `DIAGRAM_RENDER_TIMEOUT`, `MATH_AS_IMAGE`, `IMAGE_FETCH_FAILED`, `FONT_FALLBACK`, `PDF_HEADER_SIMPLIFIED`, `PDF_SCANNED_SUSPECTED`, `PDF_MULTICOLUMN_SUSPECTED`, `HWPX_EQUATION_PRESERVED`, `INDIRECT_CONVERSION`, `INPUT_CORRUPT`, `OUTPUT_WRITE_FAILED`

`where.line` 은 가능한 경우 MD 줄 번호.

### 5.3 노출 경로
- **CLI**: 결과물마다 한 줄 요약(템플릿 이름·버전·출처) + warn 목록. `--verbose` 전체, `--json` 리포트 원본, `--quiet`.
  ```
  ✔ 보고서.docx  템플릿: company-report v1.2.0 (커스텀)
  ✔ 보고서.hwpx  템플릿: company-report v1.2.0 (커스텀 · 그릇은 내장)
    ⚠ 42행: PlantUML 미설치 → 코드 블록 유지  (mdcast doctor)
    ℹ 정보 3건 (--verbose)
  ```
- **MCP**: 리포트 JSON + 에이전트가 그대로 전달하기 좋은 요약 문장.
- **Skill**: "변환 후 템플릿 줄과 warn 항목은 반드시 사용자에게 전달하라" 규칙.
- **결과 파일 메타데이터**: mdcast 버전, 템플릿 이름·버전·출처, pandoc·typst 버전. docx 사용자 지정 속성 / hwpx 메타데이터 / PDF Producer·Keywords.

### 5.4 doctor
pandoc·typst 버전(동봉), 폰트(맑은 고딕 시스템 / Noto Sans KR 동봉), Mermaid(Node + mermaid-cli: `npm i -g @mermaid-js/mermaid-cli` 안내), PlantUML(Java + 동봉 jar), 템플릿 폴더 탐색 결과를 표로 출력. CLI 와 MCP 도구로 제공.

### 5.5 견고성
- 외부 렌더러(Mermaid, PlantUML, typst) 타임아웃 기본 60초 → warn + 폴백
- 다이어그램 캐시 `~/.cache/mdcast/` (콘텐츠 해시 키, 손상 시 재생성)
- URL 이미지: 10초 타임아웃, 실패 시 자리표시 + `IMAGE_FETCH_FAILED`. `--offline` 이면 외부 요청 없음
- `--keep-temp`: AST JSON, 생성 Typst 소스, 렌더링 이미지 보존
- 보안: 매크로 포함 문서(.docm 등)는 템플릿으로 사용하지 않음. XML 파싱 시 외부 엔티티 비활성화. zip 압축 해제 비율 제한

---

## 6. 인터페이스

### 6.1 CLI
```
mdcast convert <입력> --to docx,hwpx,pdf|md [--template <이름|경로>] [--out-dir <dir>]
               [--json] [--verbose] [--quiet] [--keep-temp] [--offline]
mdcast template list | describe <이름> | validate <경로> | init --from <문서> [--from <문서>] [--name <이름>]
mdcast doctor
mdcast mcp                                   # 로컬 MCP 서버 (stdio)
mdcast skill install --target <skills 폴더>
```

### 6.2 MCP 도구 (로컬 stdio, 경로 기반) — 5개
| 도구 | 입력 | 출력 |
|---|---|---|
| `convert` | `input_path`, `to`(목록), `template?`, `output_dir?` | 생성 파일 경로 목록 + 리포트 |
| `list_templates` | — | 템플릿 목록과 출처 |
| `describe_template` | `name` | 필드 키, 지원 포맷, 폴백 예정 항목 |
| `validate_template` | `path` | 검증 결과(경고 목록) |
| `doctor` | — | 환경 진단 표 |

### 6.3 Skill
`skill/SKILL.md`: 언제 mdcast 를 쓰는지, CLI/MCP 사용법, MD 작성 규칙(§4.4), 결과 보고 규칙(§5.3). 패키지에 포함되어 `mdcast skill install` 로 각 클라이언트의 skills 폴더에 복사한다.

---

## 7. 테스트 전략

### 7.1 층
| 층 | 대상 | 방식 |
|---|---|---|
| 단위 | 필터, 템플릿 해석·상속·폴백, 번호 체계, 리포트, 분할 run 의 `{{키}}` 병합 | AST JSON 입출력 비교 |
| 구조 | 생성 docx/hwpx 내부 XML | 압축 해제 + XPath 단언. 핵심 부분은 ID 정규화 후 골든 XML 비교 |
| 왕복 | MD → X → MD | 정규화된 AST 의미 동일성. 아래 허용 손실표 외 차이는 실패 |
| 시각 | 쪽별 PNG | 승인된 골든 이미지와 허용 오차 비교 + 세 포맷 나란히 보는 HTML 비교 시트 |
| 무거부 속성 | 망가진 템플릿 조합 | "어떤 조합에서도 결과물 생성 + 기대 이벤트 코드" |
| 껍데기 | CLI / MCP / Skill | CLI 종료 코드·`--json` 스키마, MCP SDK 클라이언트 실호출·도구 정의 스냅샷, Skill 대표 작업 평가 |

### 7.2 왕복 허용 손실
| 포맷 | 허용 손실 |
|---|---|
| docx | 없음(목표). 템플릿 번호·캡션 접두어는 역변환으로 제거되므로 손실 아님 |
| hwpx | 없음(목표). 수식은 대체 텍스트 LaTeX 로 복원 |
| pdf | 제목 수준 오인식, 표 셀 경계 오차, 각주 위치 — 복원율 지표로 관리 (§7.5) |

### 7.3 시각 렌더링 (개발 전용, 배포물 미포함)
| 포맷 | 방법 | 실행 |
|---|---|---|
| PDF | pypdfium2 | CI |
| docx | LibreOffice → PDF → PNG | CI |
| hwpx | 한글 COM 으로 열어 PDF 저장 → PNG | 로컬(작성자 PC에 한글 설치됨) |

### 7.4 hwpx 검증
1. M0 검증 실험(§9)
2. OWPML XSD 확보 시 스키마 검증 (CI)
3. 생성된 모든 테스트 hwpx 를 한글 COM 으로 열어 오류·복구 안내 없음 확인 + PDF 저장 (로컬)
4. 여러 한글 버전에서 만든 비기밀 실제 hwpx 샘플 코퍼스로 가져오기 품질 측정

### 7.5 PDF 가져오기 평가
정답을 아는 PDF(우리 MD → Typst PDF, 같은 MD → docx → Word "PDF로 저장")로 제목 수준 정확도·표 셀 일치율·머리말 제거율을 측정하고 임계값으로 회귀를 감시한다.

### 7.6 테스트 파일 관리
| 구분 | 위치 | Git |
|---|---|---|
| 영속: 입력 픽스처, 정상·손상 템플릿 | `tests/fixtures/` | ✔ |
| 영속: 승인된 XML 스냅샷·골든 PNG (승인 명령으로만 갱신) | `tests/golden/` | ✔ |
| 영속(조건부): 실제 hwpx 코퍼스 | `tests/corpus/` (비기밀만) 또는 `MDCAST_CORPUS_DIR` 로 지정한 저장소 밖 경로 | 비기밀만 ✔ |
| 임시: 단위·구조·왕복 테스트 산출물 | pytest `tmp_path` (자동 삭제) | ✖ |
| 임시: 시각 비교 결과, 비교 시트, `--keep-temp` 산출물 | `.test-output/` (매 실행 덮어씀) | ✖ (`.gitignore`) |

픽스처: `kitchen-sink.md`(전 요소), `korean-report.md`(개조식·제목 번호·`<표 n>`·필드·쪽 나눔), 경계 사례(빈 문서, 6단계 중첩 목록, 대형 표, 병합 셀, 이모지, 긴 단어/URL, 혼합 줄바꿈).

### 7.7 CI
GitHub Actions, Windows + Linux, Python 3.11–3.13. pandoc·typst 버전 고정. 시각 테스트는 폰트를 설치한 Linux 에서만. 한글 의존 테스트는 로컬 전용 마커. 구현은 TDD.

---

## 8. 배포

### 8.1 패키지
| 항목 | 내용 |
|---|---|
| `mdcast` (기본) | 순수 Python. 동봉: pypandoc-binary(pandoc), typst, Noto Sans KR(OFL), 내장 default 템플릿, Skill |
| `mdcast[diagrams]` | plantuml-mit jar 동봉(MIT). Java 필요 |
| Mermaid | Python extra 로 설치 불가. `npm i -g @mermaid-js/mermaid-cli` (doctor 안내) |

### 8.2 실행 모델 — 로컬 MCP
변환은 사용자 PC 에서 실행한다. 변환 서버는 없다. "서버"는 패키지를 내려받는 곳뿐이다.

| 단계 | 패키지 출처 | 설치/실행 |
|---|---|---|
| 0. 개인 시험 | 로컬 소스 또는 공유 드라이브 `.whl` | `uv tool install -e .` / `uvx --from <whl> mdcast mcp` |
| 1. 사내 공유 | 비공개 Git 저장소 (GitHub 비공개 또는 회사 GitLab) | `uvx --from git+https://…/mdcast@v0.1.0 mdcast mcp` (태그 고정) |
| 2. 오픈소스 | GitHub 공개 + PyPI | `uvx mdcast mcp` |

- 의존 패키지는 공개 PyPI 에서 받는다. 회사망이 PyPI 를 차단하면 사내 미러가 필요하다.
- 단계 1 은 PC마다 git 과 저장소 접근 권한(SSH 키/토큰)이 필요하고, 재택 사용자는 저장소에 접근 가능해야 한다(인터넷 호스팅 또는 VPN).

### 8.3 클라이언트 등록
README 에 클라이언트별 예시를 둔다: Claude Code(플러그인 또는 `claude mcp add mdcast -- uvx mdcast mcp`), Codex(`~/.codex/config.toml` `[mcp_servers.mdcast]`), Cursor / VS Code Copilot / Gemini CLI / Antigravity / qwen-code(각 MCP JSON). Skill 지원 클라이언트는 `mdcast skill install`.

### 8.4 버전
mdcast SemVer + CHANGELOG. `template.yaml` 의 `schema` 로 템플릿 형식 버전 관리(구버전은 경고 후 변환, 거부 없음). 동봉 pandoc·typst 버전 고정, doctor 와 메타데이터에 표시.

### 8.5 라이선스·고지
- mdcast: Apache-2.0
- `THIRD_PARTY_LICENSES/`: pandoc(GPL-2.0, 고정 버전 소스 위치), typst(Apache-2.0), Noto Sans KR(OFL), D2Coding(OFL), PlantUML(MIT), 기타 Python 의존성
- AGPL 의존성(PyMuPDF 등) 사용 금지
- README: 한컴·Microsoft 와 무관함 명시. 도구 이름·패키지명에 한컴 상표 미사용
- 텔레메트리 없음

---

## 9. 마일스톤

전체를 한 번에 계획하지 않는다. **첫 구현 계획은 M0–M1 만 다룬다.**

| 마일스톤 | 내용 | 완료 기준 |
|---|---|---|
| **M0 검증 실험** | §10 의 가정 S1–S5 검증 (버리는 코드 허용) | 각 가정 통과 또는 대안 결정 |
| **M1 코어 + docx/pdf 내보내기** | pipeline, report, templates(해석·폴백·스키마), filters(pagebreak, table-variant, numbering), docx writer, pdf writer, 내장 default, CLI `convert`/`template validate·list·describe` | kitchen-sink·korean-report 가 docx/pdf 로 생성, 무거부 속성 테스트 통과 |
| M2 hwpx 내보내기 | `hwpx/` writer, 한글 COM 검증 루프 | 한글에서 오류 없이 열림, 시각 비교 통과 |
| M3 가져오기 | docx / hwpx / pdf readers, 역변환 필터, 개조식 휴리스틱 | 왕복 테스트, PDF 복원율 임계값 |
| M4 다이어그램·수식 | diagrams 필터, hwpx 수식 이미지, 캐시, doctor | 렌더러 유무 양쪽 테스트 |
| M5 패키징·인터페이스 | MCP 서버, Skill, `template init`, `skill install`, 라이선스 고지, 배포 문서 | 2개 이상 에이전트 클라이언트에서 MCP 동작 확인 |

---

## 10. M0 에서 검증할 가정 (위험)

아래는 기억·문서에 근거한 주장으로, **사실로 확정되지 않았다.** M0 에서 검증한다.

| ID | 가정 | 실패 시 대안 |
|---|---|---|
| S1 | 코드로 생성한 최소 hwpx(문단 1개)가 한글에서 오류·복구 안내 없이 열린다 | 한글로 저장한 최소 hwpx 를 그릇으로 삼아 최소 변경만 가하는 방식으로 축소 |
| S2 | pandoc `--reference-doc` 이 머리말·꼬리말·쪽 설정을 유지하고, 사본의 스타일 정의를 덮어쓰면 출력에 반영된다 | docx 후처리에서 스타일·머리말을 직접 주입 |
| S3 | 분할된 run 에 걸친 `{{키}}` 를 찾아 채울 수 있다 | 필드를 docx 콘텐츠 컨트롤/필드 코드로 정의하도록 템플릿 규칙 변경 |
| S4 | 단계별 개조식 기호를 pandoc 이 만든 `numbering.xml` 후처리로 적용할 수 있다 | 목록을 직접 생성하는 docx 목록 writer 작성 |
| S5 | Typst 가 맑은 고딕/Noto Sans KR 로 한글을 조판하고, yaml 을 읽어 머리말·꼬리말·쪽 번호를 구성할 수 있다 | yaml → Typst 변수 코드 생성으로 우회 |

추가로 구현 중 확인할 사실: hwpx 쪽 나눔·쪽 번호 컨트롤의 정확한 XML 표현, pandoc 버전별 병합 셀 docx 출력, pandoc MD writer 의 복잡한 표 HTML 출력 동작.

---

## 11. 확인 필요 (결정 보류 항목)

| 항목 | 담당 | 시점 |
|---|---|---|
| 회사 오픈소스 공개 승인 (코드 소유권, GPL 포함 도구 정책) | 작성자 | 단계 2 이전 |
| 한컴 공개 문서 참고 시 출처 표기 문구 요구 여부 | 작성자 | 단계 2 이전 |
| 단계 1 배포 채널 (GitHub 비공개 vs 회사 GitLab) | 작성자 | M5 이전 |
| 실제 default 템플릿 내용 (작성자 제공) | 작성자 | M1 중 (그 전까지 중립 스타터 사용) |
| 공개 전 점검: 코퍼스 기밀 여부, 회사 로고·양식·사내 폰트 미포함 | 작성자 | 단계 2 이전 |

---

## 부록 A. 향후: 원격 MCP (v1 범위 아님)

설치 없는 사용 요구가 생기면 **내보내기 전용 원격 MCP** 를 추가할 수 있다. 검토 결과:
- 파일 전달: MD 입력은 인자로 가능, 출력은 단기 다운로드 링크(`resource_link`), 가져오기는 별도 업로드 API 필요
- stateless: 앱 서버는 무상태, 다운로드 링크용 파일만 TTL 임시 저장소, 템플릿은 이미지 내장 + 요청별 zip
- 외부 공개 시 보안: 인증(토큰 → SSO/OAuth), 요청 크기·시간·동시성 제한, zip 폭탄·XXE 방어, 네트워크 차단 컨테이너, SSRF 차단(URL 이미지 끔, pandoc `--sandbox`, PlantUML 보안 프로파일), 문서 내용 비로깅, 감사 로그
- 폰트: 맑은 고딕은 Linux 서버에 재배포 불가 → 서버 PDF 는 대체 폰트
- 코어 API 가 바이트 입출력(§2.2)이므로 추가 비용은 껍데기·인프라에 한정된다.
