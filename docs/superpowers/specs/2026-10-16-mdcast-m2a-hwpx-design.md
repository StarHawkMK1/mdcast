# M2a hwpx 내보내기 설계 (2026-10-16)

상위 스펙: `2026-10-15-mdcast-design.md` (§2 구조, §3 템플릿, §4.1 내보내기, §7.4 hwpx 검증, §9 M2). 줄 높이의 뜻은 `2026-10-16-line-height-design.md` 를 따른다.

## 1. 범위

M2 는 두 단계로 나눈다 (2026-10-16 사용자 결정).

| 단계 | 내용 |
|---|---|
| **M2a (이 문서)** | 그릇 재사용, 쪽 설정, 머리말/꼬리말·쪽 번호, 제목, 본문, 개조식 목록, 인용, 코드, 가로줄, 쪽 나눔, 인라인 서식·링크, 메타데이터, 한글 COM 검증 루프 |
| M2b | 표(병합 셀, 테두리, 머리글 행), 이미지, 각주. M2a 동안은 §5.6 대로 낮춰 출력한다 |

회사 hwpx 양식은 아직 없다. 내장 그릇은 **한글이 저장한 빈 문서**로 한다. 사용자 reference.hwpx 지원(스타일 이름 매핑, explicit 규칙)도 M2a 에 들어가지만, 실제 회사 양식 시험은 양식이 생긴 뒤에 한다.

M2a 의 대상이 아닌 것: hwpx 가져오기(M3), 수식 이미지(M4), `template init --from x.hwpx`(M3 이후), 한글 고유 번호·글머리표 정의를 쓰는 목록.

## 2. 방식 결정

**자체 lxml OWPML writer + 그릇 재사용** (2026-10-16 사용자 결정, 접근 A).

- 상위 스펙 §2 의 `hwpx/` 독립 패키지 설계와 같다. S1 실험(2026-10-15)에서 한글이 저장한 hwpx 를 풀어 XML 을 고치고 다시 묶은 파일이 한글에서 오류 없이 열렸다.
- 버린 대안:
  - python-hwpx: Alpha 단계라 API 가 바뀔 수 있고, 글자/문단 모양(charPr/paraPr)을 직접 고치는 API 가 없다. docx·pdf 와 같은 모양을 내려면 결국 XML 을 직접 고쳐야 한다.
  - 한글 COM 으로 생성: 한글이 설치된 PC 에서만 돈다. COM 은 검증에만 쓴다.
- **추측으로 XML 을 쓰지 않는다.** 첫 작업(§3)에서 한글로 견본을 저장해 정확한 표현을 읽고, 그 결과를 이 문서의 부록에 기록한 뒤 구현한다.

## 3. 첫 작업: 견본 채취

한글 COM 으로 아래 기능을 하나씩 넣은 문서를 hwpx 로 저장하고, 해당 XML 조각과 header.xml 변화를 기록한다. 스크립트는 `spikes/m2_samples/` 에 두고, 결과는 이 문서 끝 "부록 A" 에 붙인다.

1. 쪽 나눔 (문단 속성 `pageBreak` 인지 확인)
2. 머리말·꼬리말 (양쪽, 첫 쪽 감춤 포함)
3. 현재 쪽 번호, 전체 쪽 수 (`autoNum` 의 `numType` 값)
4. 탭(가운데·오른쪽 탭 정의, 본문의 탭 문자)
5. 하이퍼링크
6. 문단 테두리/배경 (아래 테두리만, 배경색 + 안쪽 여백), 연속 문단 테두리 연결
7. 한 문단 안 줄 바꿈
8. 개요 문단에서 개요 번호 서식을 비웠을 때의 표현과 화면
9. 위쪽 여백·머리말 높이와 본문 시작 위치의 관계 (§6.1 의 가정 확인)
10. 줄 간격 "글자에 따라 N%" 의 줄 피치 (§8.3 측정의 사전 확인)
11. content.hpf 에 모르는 `opf:meta` 이름을 넣어도 열리는지

결과가 이 문서의 가정과 다르면, 그 항목의 설계를 고쳐 이 문서에 반영한 뒤 진행한다.

## 4. 구조

### 4.1 독립 패키지 `src/mdcast/hwpx/`

mdcast 의 다른 모듈을 import 하지 않는다 (상위 스펙 §2). 의존성은 lxml 과 panflute(pandoc AST) 뿐이다.

| 파일 | 책임 |
|---|---|
| `container.py` | zip 읽기·쓰기. 다시 묶을 때 `mimetype` 을 첫 항목·무압축으로 두고, 나머지는 원래 순서와 압축 방식을 지킨다 |
| `header.py` | header.xml 편집. 글자 모양·문단 모양·테두리/배경·탭 정의를 추가하고 새 ID 를 돌려준다. 같은 정의는 재사용하고 `itemCnt` 를 갱신한다. 스타일을 이름으로 찾는다 |
| `section.py` | AST → section0.xml 본문. 첫 문단의 `secPr` 는 유지한다 |
| `meta.py` | content.hpf 메타데이터, `Preview/PrvText.txt`, settings.xml 커서 위치 |
| `look.py` | 입력 값 객체 (§4.3) |
| `__init__.py` | 공개 진입점 `write(...)` |

공개 진입점:

```python
def write(
    doc: pf.Doc,
    container: bytes,
    looks: dict[str, Look],      # 요소 이름 → 모양 (§5)
    styles: dict[str, str],      # 요소 이름 → 그릇의 스타일 이름
    page: PageSetup | None,      # None 이면 그릇의 쪽 설정 유지
    header: Slots | None,        # None 이면 그릇의 머리말 유지 (source: reference)
    footer: Slots | None,
    fill: Callable[[str], list[Segment]],  # "{{키}}" 가 든 문자열 → 텍스트/쪽 번호 조각
    list_marker: Callable[[bool, int, int], str],  # (번호 목록?, 수준 1~, 번호) → 기호 텍스트
    list_indent_mm: float,
    metadata: Metadata,
) -> tuple[bytes, list[Warning]]
```

`Warning` 은 패키지 안의 단순 dataclass(`kind`, `message`, `element`) 다. 정확한 타입 이름과 필드는 구현 계획에서 정한다.

### 4.2 어댑터 `src/mdcast/writers/hwpx.py`

- 템플릿 설정을 `Look`, `PageSetup`, `Slots` 로 바꾼다.
- `ResolvedFields` 로 `fill` 을 만든다.
- `Warning` 을 리포트 이벤트로 옮긴다.
- 그릇을 고른다.
  - 내장 그릇이면 yaml 전체를 반영한다.
  - 사용자 reference.hwpx 이면 **yaml 에 적힌 값(`ResolvedTemplate.explicit`)만** 반영한다 (docx 와 같은 규칙).
- `pipeline.WRITERS` 에 `Format.HWPX` 를 등록한다.
- `filters/pagebreak.break_block` 에 hwpx 표식을 추가한다. 표식은 `section.py` 가 알아보는 raw 블록이다.

### 4.3 입력 값 객체

`Look` 는 한 요소의 모양이다. 모든 필드는 선택이고, `None` 은 그릇 값을 그대로 둔다는 뜻이다.

| 필드 | 단위 | yaml |
|---|---|---|
| `font` | 글꼴 이름 | `fonts.body/heading/code.family` |
| `size` | pt | `size` |
| `bold`, `italic` | bool | `bold`, `italic` |
| `color` | `#RRGGBB` | `color` |
| `align` | left/center/right/justify | `align` |
| `line_height` | 비율 (1.8 = 180%) | `line_height` |
| `space_before`, `space_after` | pt | `space_before`, `space_after` |
| `indent_left` | mm | `indent_left` |
| `background` | `#RRGGBB` | `background` |
| `keep_with_next` | bool | `keep_with_next` |

`PageSetup` 은 용지 폭·높이(mm), 방향, 네 여백(mm)이다. `Slots` 는 left/center/right 문자열과 `line`(below/above/none)이다.

### 4.4 내장 그릇

`src/mdcast/builtin_templates/default/reference.hwpx`:
- 한글 COM 으로 새 빈 문서를 hwpx 로 저장한 파일이다.
- 만드는 스크립트는 `scripts/make_reference_hwpx.py` 에 둔다.

사용자 템플릿에 reference.hwpx 가 없으면 내장 그릇을 쓴다 (`TEMPLATE_CONTAINER_FALLBACK`, 기존 로직).

reference.hwpx 가 깨져 있는 경우:
- zip 이 아니거나, header.xml·section0.xml 이 없거나, XML 오류가 있으면 해당한다.
- `TEMPLATE_INVALID`(warn)를 기록하고, 내장 그릇과 yaml 모양으로 만든다.

## 5. 요소 매핑

### 5.1 공통

- yaml 요소마다 header.xml 에 전용 글자 모양(charPr)과 문단 모양(paraPr)을 하나씩 추가한다.
- 문단은 매핑된 스타일을 `styleIDRef` 로 가리키고, 모양은 전용 `paraPrIDRef`, 런의 `charPrIDRef` 로 직접 지정한다.
  - 그래서 같은 "바탕글" 스타일을 쓰는 본문·인용·코드도 서로 다르게 보인다.
- 새 모양은 매핑된 스타일의 기존 charPr/paraPr 를 복사한 뒤 `Look` 의 값만 덮어쓴다.
  - 내장 그릇에서는 `Look` 이 모든 값을 가지므로 결과가 yaml 그대로다.
  - 사용자 그릇에서는 적힌 값만 바뀐다.
- 스타일 이름이 그릇에 없으면 `STYLE_UNMAPPED`(info)를 남기고 "바탕글"(스타일 ID 0)을 쓴다. `template validate` 도 hwpx 스타일 이름을 검사한다.

값 변환:

| yaml | OWPML |
|---|---|
| `size` | charPr `height` = pt × 100 |
| `bold`, `italic` | charPr `<hh:bold/>`, `<hh:italic/>` 유무 |
| `color` | charPr `textColor` |
| 글꼴 | `fontfaces` 의 각 언어 묶음(한글·영문 등)에 글꼴을 추가하고 charPr `fontRef` 로 가리킨다 |
| `align` | paraPr `align horizontal` = LEFT/CENTER/RIGHT/JUSTIFY |
| `line_height` N% | paraPr `lineSpacing type="PERCENT" value="N"` |
| `space_before/after` | paraPr `margin` 의 `prev`/`next` (HWPUNIT) |
| `indent_left` | paraPr `margin` 의 `left` (HWPUNIT) |
| `keep_with_next` | paraPr `breakSetting keepWithNext="1"` |
| `background` | 문단 테두리/배경용 borderFill 을 추가하고 paraPr `border borderFillIDRef` 로 가리킨다 |

HWPUNIT 은 1/7200 인치다. mm → `round(mm × 7200 / 25.4)`, pt → `round(pt × 100)`.

### 5.2 제목

- "개요 N" 스타일을 쓴다. 개요 수준이 살아 있어야 한글의 개요 보기·차례 만들기가 된다.
- 한글 개요는 번호를 자동으로 붙인다. 그래서 그 개요 스타일이 쓰는 번호 정의(`numbering`)에서 **수준별 번호 서식 문자열을 비운다**.
- 제목 번호는 docx·pdf 와 똑같이 mdcast 번호 필터가 넣은 텍스트만 쓴다.
- 서식을 비운 결과는 §3 의 8번 견본으로 확인한다.
  - 빈 서식이 한글에서 문제가 되면, 제목 문단 모양의 `heading type` 을 `NONE` 으로 바꿔 개요 수준을 포기한다.
  - 이때 이 문서에 기록한다.
- 사용자 그릇에서도 번호 서식은 비운다. 번호의 출처를 mdcast 하나로 두기 위해서다.

### 5.3 개조식 목록

- 기호를 **텍스트로** 문단 맨 앞에 넣는다.
  - 기호는 `lists.bullet`·`lists.ordered` 이고, 번호는 `counters.format_counter` 로 만든다.
  - 기호 뒤에는 탭을 하나 넣는다.
- 수준마다 문단 모양을 하나 만든다.
  - 왼쪽 여백 = 수준 × `lists.indent_per_level`
  - 내어쓰기 = 기호 칸 너비
- 줄 높이와 간격은 본문(`body`) 값이다. docx·pdf 와 같다.
- 한글 고유의 번호·글머리표 정의는 쓰지 않는다 (2026-10-16 결정).
  - 텍스트 기호를 쓰는 쪽이 결과가 확실하고 docx·pdf 와 모양을 맞추기 쉽다.
  - 대가로, 한글에서 항목을 끼워 넣어도 번호가 자동으로 다시 매겨지지 않는다.
  - M3 가져오기는 개조식 휴리스틱으로 이 기호를 목록으로 복원한다.
- 기호를 만드는 코드는 `mdcast.counters` 에 있고 `hwpx/` 는 mdcast 를 import 하지 않는다. 그래서 어댑터가 `list_marker(번호 목록?, 수준, 번호)` 함수를 넘기고, `hwpx/` 는 그 함수가 돌려준 텍스트를 쓴다 (§4.1).

### 5.4 인용·코드·가로줄·정의 목록·줄 블록

| 요소 | 출력 |
|---|---|
| 인용 | `quote` 모양: 왼쪽 여백, 색, 크기. 안의 블록은 각자 매핑하되 왼쪽 여백만 더한다 |
| 코드 블록 | 한 문단에 줄마다 줄 바꿈(`lineBreak`)을 넣는다. 코드 글꼴을 쓴다. 배경은 문단 테두리/배경, 안쪽 여백은 2mm (PDF 와 같음) |
| 가로줄 | 아래 테두리만 있는 빈 문단 |
| 정의 목록 | 용어는 굵은 본문 문단, 정의는 한 수준 들여쓴 본문 문단 |
| 줄 블록 | 한 문단에 줄 바꿈 |
| Div | 안의 블록을 그대로 매핑 |

### 5.5 인라인

- 굵게, 기울임, 밑줄, 취소선, 위/아래 첨자, 인라인 코드:
  - 문단의 글자 모양을 바탕으로 조합마다 charPr 를 하나 만들어 재사용한다.
  - 인라인 코드는 코드 글꼴과 크기를 쓴다.
- 링크는 한글 고유의 하이퍼링크다 (XML 은 §3 의 5번).
- 줄 바꿈 처리:
  - `SoftBreak` 는 공백이다.
  - `LineBreak` 는 문단 안 줄 바꿈이다.
- 다른 형식 전용 raw 인라인(openxml, typst)은 버린다.

### 5.6 M2b 전까지 낮춰 출력하는 요소

거부하지 않는다. 종류마다 `RENDER_WARNING`(warn, `format=hwpx`, `element=<종류>`)을 **문서당 한 번** 기록한다.

| 요소 | M2a 출력 |
|---|---|
| 표 | 캡션 문단(`caption` 모양). 행마다 본문 문단 하나에 셀 텍스트를 " \| " 로 이어 쓴다 |
| 이미지(인라인·그림) | `[이미지: 설명]` 텍스트 (PDF 대체 문구와 같음). 그림 캡션은 캡션 문단 |
| 각주 | 본문에는 `[n]`. 문서 끝에 `footnote` 모양으로 `[n] 내용` 문단을 모은다 |
| 수식 | LaTeX 원문을 인라인 코드 모양으로 쓴다 (이미지는 M4) |
| 다른 형식 전용 raw 블록 | 버린다 (경고 없음, docx·pdf 와 같음) |

## 6. 쪽 설정·머리말/꼬리말·메타데이터

### 6.1 쪽 설정

첫 문단 `secPr` 의 `pagePr` 를 고친다.
- 크기와 방향:
  - 용지 폭·높이를 HWPUNIT 으로 넣는다.
  - 가로 방향이면 `landscape` 값을 바꾼다. 정확한 값은 견본으로 확인한다.
- 내장 그릇에는 yaml 전체를, 사용자 그릇에는 yaml 에 적힌 값만 넣는다.

한글은 본문 시작 위치를 "위쪽 여백 + 머리말 높이" 로 정한다 (§3 의 9번에서 확인). yaml 의 `margin.top` 은 본문 시작 위치를 뜻하므로 두 값으로 나눈다.

- 위쪽 여백(`top`) = PDF 에서 머리말이 놓이는 위치 (Typst 기본: 머리말 아래 끝이 위 여백의 70% 지점)에서 머리말 한 줄 높이를 뺀 값
  - 머리말 한 줄 높이 = `body.size` × `body.line_height`. PDF 머리말이 본문 글자 설정을 물려받기 때문이다. hwpx 머리말 문단도 `body` 모양을 쓴다.
- 머리말 높이(`header`) = `margin.top` − `top`
- 아래쪽(`bottom`, `footer`)도 같은 방식이다.
- `top` 이 0 이하가 되면 `top` = 0, `header` = `margin.top` 으로 둔다.

결과적으로 세 형식의 본문 시작 위치가 같다. 머리말 위치는 §8.3 으로 PDF 와 비교한다.

### 6.2 머리말·꼬리말

`source: yaml` 인 경우:
- 그릇의 해당 머리말(또는 꼬리말) 컨트롤을 모두 지운다.
- 양쪽 공통(`applyPageType="BOTH"`) 컨트롤을 하나 넣는다.
- 내용은 문단 하나다.
  - header.xml 에 탭 정의를 하나 추가한다. 가운데 탭은 본문 폭의 1/2, 오른쪽 탭은 본문 폭 끝이다.
  - 왼쪽·가운데·오른쪽 칸을 탭으로 나눈다 (docx 와 같은 방식).
- 필드 처리:
  - `{{page}}` 는 쪽 번호 컨트롤(`autoNum numType="PAGE"`)이다.
  - `{{pages}}` 는 전체 쪽 수(`numType="TOTAL_PAGE"`)이다.
  - 나머지 필드는 텍스트다.
- `line: below/above` 이면 문단 아래/위 테두리를 그린다.
- 첫 쪽 감춤(`pageHiding`)의 머리말·꼬리말 감춤은 끈다. docx 에서 yaml 머리말일 때 titlePg 를 끄는 것과 같은 규칙이다.

`source: reference` 인 경우:
- 그릇의 머리말을 그대로 두고, 그 안 텍스트의 `{{키}}` 만 채운다.
- `{{page}}`·`{{pages}}` 는 컨트롤로 바꾼다.

### 6.3 메타데이터

`Contents/content.hpf` 의 `opf:metadata`:
- 제목·작성자·키워드는 frontmatter 에서 가져온다. docx core 속성과 같은 값이다.
- mdcast 생성 정보는 docx 사용자 지정 속성과 같은 키(`mdcast.generator`, `mdcast.template.name`, `mdcast.template.version`, `mdcast.template.source`, `mdcast.pandoc`, `mdcast.typst`)로 `opf:meta` 에 넣는다.
- 한글이 모르는 meta 이름을 거부하면(§3 의 11번) 생성 정보는 빼고, 이 문서에 기록한다.

그 밖의 파일:
- `Preview/PrvText.txt` 에 본문 앞부분 텍스트를 다시 쓴다. 그릇의 미리보기 텍스트가 남지 않게 하려는 것이다.
- `Preview/PrvImage.png` 는 그릇 것을 그대로 둔다. 내장 그릇에서는 빈 쪽이고, 사용자 그릇에서는 양식 모양이다.
- `settings.xml` 의 커서 위치는 문서 처음으로 돌린다.

## 7. 오류 처리

- 상위 스펙의 "거부 금지" 원칙을 따른다. 어떤 입력과 템플릿이든 hwpx 파일을 만든다.
- 낮춰 출력하는 요소는 §5.6 대로 처리한다.
- 깨진 그릇은 §4.4 대로 처리한다.
- `hwpx.write` 안의 예기치 않은 예외는 파이프라인이 `RENDER_FAILED`(error)로 잡는다. 다른 대상 형식의 출력은 영향을 받지 않는다 (기존 동작).

## 8. 검증

### 8.1 구조 테스트 (한글 없이, CI)

생성한 hwpx 를 풀어 XPath 로 단언한다. 단언 대상:
- `mimetype` 이 첫 항목이고 무압축이다. 모든 XML 이 올바른 형식이다.
- `tests/helpers.hwpx_integrity(data)`:
  - 모든 `*IDRef` 가 존재하는 ID 를 가리킨다.
  - 같은 종류 안에서 ID 가 겹치지 않는다.
  - `itemCnt` 가 실제 자식 수와 같다.
  - 모든 hwpx 테스트가 이 함수를 부른다.
- 요소별 모양 값: `height`, `lineSpacing`, `margin`, `align`, `keepWithNext`, 코드 배경 borderFill.
- 쪽 크기, 여백 분배(§6.1), 머리말·꼬리말 컨트롤, 쪽 번호 컨트롤, 탭 정의.
- 목록 기호 텍스트와 수준별 내어쓰기, 개요 번호 서식이 비어 있는지.
- 메타데이터, PrvText, 커서 위치.
- 사용자 그릇이면 yaml 에 적은 값만 바뀌고 나머지는 그릇 값 그대로인지.
- §5.6 의 경고가 종류마다 한 번인지.

골든 XML 비교는 하지 않는다. 값 단언이 무엇이 바뀌었는지 더 정확히 보여 주고, 골든 갱신 부담이 없다.

### 8.2 거부 금지

`tests/test_no_reject.py`:
- 기존 사례를 hwpx 대상으로도 돌린다.
- 깨진 reference.hwpx 사례를 추가한다. 기대: `TEMPLATE_INVALID` 기록, 내장 그릇으로 대체, 파일 생성.

### 8.3 한글 COM 테스트 (`--run-hangul`, Windows + 한글 설치 PC 전용)

`tests/conftest.py` 의 opt-in 표에 `hangul` 을 추가한다.

픽스처 각각(kitchen-sink, edge-cases, 테스트 픽스처)에 대해:
- 한글로 열었을 때 `Open` 이 True 를 반환한다.
- `GetTextFile("UNICODE")` 에 기대 텍스트가 있다.
- PDF 로 저장해 쪽 수를 확인한다.

줄 간격 비교 (`tests/test_hangul_parity.py`):
- 한글이 저장한 PDF 와 mdcast PDF 에서 `helpers.line_pitch` 로 본문·제목·목록·코드의 줄 피치를 잰다.
- 목표 오차는 0.5% (Word 비교와 같음).
- 한글의 "글자에 따라 N%" 가 글자 크기 × N/100 과 다르면 측정값과 함께 보고하고, 변환식을 정해 이 문서에 기록한다.
- 본문 시작 위치와 머리말 위치도 PDF 와 비교한다.

보안 모듈:
- 등록하지 않으면 COM 실행마다 "접근 허용" 대화상자가 뜨고, 사람이 눌러야 테스트가 진행된다.
- 테스트는 시작할 때 `RegisterModule` 결과를 확인하고, 실패하면 경고 한 줄을 출력한다.
- README 에 등록 방법을 적는다: 한컴 개발자 사이트의 보안 모듈 DLL 과 레지스트리 경로 값. 일반 사용자에게는 필요 없다.

### 8.4 시각 확인

- `scripts/render_pages.py` 가 hwpx 도 처리한다 (한글 → PDF → PNG).
- M1 처럼 사용자가 결과 화면을 직접 보고 승인한다.

## 9. M2a 완료 기준

- 전체 테스트 통과 (`uv run python -m pytest -q`).
- kitchen-sink.hwpx 가 한글에서 오류·복구 안내 없이 열린다.
- `--run-hangul` 줄 간격 비교 통과.
- 사용자 시각 확인 승인.
- README 에 hwpx 출력, 낮춰 출력하는 요소, 보안 모듈 안내가 반영된다.

## 부록 A. 견본 채취 결과

(§3 작업에서 채운다.)
