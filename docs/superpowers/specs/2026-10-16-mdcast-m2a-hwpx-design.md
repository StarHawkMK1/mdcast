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

**2026-10-16 수행 완료.** 결과는 부록 A 에 있다. 가정과 다른 점(길이 단위 2배, 내어쓰기 방향, 줄 안 글자 위치, 첫 문단 처리, 빈 값의 처리)은 §4–§6 에 반영했다.

추가로 확인한 항목:

12. 문단 모양 여백 값의 단위
13. 첫 문단에 secPr 와 첫 블록 글자를 함께 넣는 방식
14. 가로 방향 표현
15. 목록 내어쓰기와 기호 뒤 탭

## 4. 구조

### 4.1 독립 패키지 `src/mdcast/hwpx/`

mdcast 의 다른 모듈을 import 하지 않는다 (상위 스펙 §2). 의존성은 lxml 과 panflute(pandoc AST) 뿐이다.

| 파일 | 책임 |
|---|---|
| `container.py` | zip 읽기·쓰기. 다시 묶을 때 `mimetype` 을 첫 항목·무압축으로 두고, 나머지는 원래 순서와 압축 방식을 지킨다 |
| `header.py` | header.xml 편집. 글자 모양·문단 모양·테두리/배경·탭 정의를 추가하고 새 ID 를 돌려준다. 같은 정의는 재사용하고 `itemCnt` 를 갱신한다. 스타일을 이름으로 찾는다 |
| `section.py` | AST → section0.xml 본문. 그릇 첫 문단의 `secPr`·`colPr` 런을 **첫 블록의 문단 맨 앞으로 옮긴다** (빈 첫 문단을 남기지 않는다, 부록 A-13) |
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

어댑터가 `None` 을 넘기는 규칙은 그릇에 따라 다르다.
- **내장 그릇**에서는 yaml 의 빈 값(null)을 PDF 가 실제로 쓰는 값으로 바꿔 넘긴다. 한글 빈 문서의 기본값(개요 들여쓰기, 함초롬 글꼴, 머리말 9pt 150% 등)이 새어 들지 않게 하려는 것이다.
  - 들여쓰기·앞뒤 간격: 0
  - 굵게·기울임: 아니오
  - 색: 검정
  - 정렬: 왼쪽
  - 줄 높이: 130%
  - 배경: 없음
  - 다음 문단과 함께: 아니오
- **사용자 그릇**에서는 yaml 에 적힌 값만 넘기고 나머지는 `None` 이다.

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
- 저장소가 공개이므로, 스크립트는 저장 뒤 content.hpf 의 작성자·날짜 메타데이터와 `Preview/PrvText.txt` 를 비운다.

사용자 템플릿에 reference.hwpx 가 없으면 내장 그릇을 쓴다 (`TEMPLATE_CONTAINER_FALLBACK`, 기존 로직). `ResolvedTemplate.builtin_container("hwpx")` 는 지금 `path=None`("엔진 기본")을 돌려주므로, pdf 처럼 내장 파일 경로를 돌려주게 바꾼다.

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
| `space_before/after` | paraPr `margin` 의 `prev`/`next` (**HWPUNIT × 2**) |
| `indent_left` | paraPr `margin` 의 `left` (**HWPUNIT × 2**) |
| `keep_with_next` | paraPr `breakSetting keepWithNext="1"` |
| `background` | 문단 테두리/배경용 borderFill 을 추가하고 paraPr `border borderFillIDRef` 로 가리킨다 |

HWPUNIT 은 1/7200 인치다. mm → `round(mm × 7200 / 25.4)`, pt → `round(pt × 100)`.

단위가 값마다 다르다 (부록 A-12에서 측정).
- **HWPUNIT 의 2배로 쓰는 값:**
  - paraPr `margin` 의 `left`·`right`·`intent`·`prev`·`next`
  - tabPr `tabItem` 의 `pos`
- **HWPUNIT 그대로 쓰는 값:**
  - `pagePr` 의 크기와 여백
  - paraPr `border` 의 `offset*`
  - subList 의 `textWidth`·`textHeight`
- 이 차이는 `hwpx/units.py` 의 두 함수(`hwpunit`, `para_unit`)로만 다룬다. 구조 테스트로 값마다 단위를 고정한다.

### 5.2 제목

- "개요 N" 스타일을 쓴다. 개요 수준이 살아 있어야 한글의 개요 보기·차례 만들기가 된다.
- 한글 개요는 번호를 자동으로 붙인다. 그래서 그 개요 스타일이 쓰는 번호 정의(`numbering`)에서 **수준별 번호 서식 문자열을 비운다**.
- 제목 번호는 docx·pdf 와 똑같이 mdcast 번호 필터가 넣은 텍스트만 쓴다.
- 비우는 대상은 각 수준(`paraHead`)의 서식 문자열이다. 함께 번호 뒤 간격 `textOffset` 을 0 으로 한다.
  - 간격을 그대로 두면 번호가 없어도 제목이 약 1.8mm 오른쪽에서 시작한다 (부록 A-8).
  - 이렇게 하면 제목 글자가 본문과 같은 x 에서 시작한다. `GetTextFile` 결과에는 제목 앞에 공백 하나가 남지만, 화면과 PDF 에는 보이지 않는다.
- 제목 문단 모양은 개요 스타일의 paraPr 를 복사하고 왼쪽 여백을 `indent_left`(내장 그릇에서는 0)로 바꾼다. 한글 개요 1–3 은 수준마다 왼쪽 여백이 있다.
- 사용자 그릇에서도 번호 서식은 비운다. 번호의 출처를 mdcast 하나로 두기 위해서다.

### 5.3 개조식 목록

- 기호를 **텍스트로** 문단 맨 앞에 넣는다.
  - 기호는 `lists.bullet`·`lists.ordered` 이고, 번호는 `counters.format_counter` 로 만든다.
  - 기호 뒤에는 탭을 하나 넣는다.
- 수준마다 문단 모양을 하나 만든다. 번호 목록과 글머리표 목록은 따로 만든다.
- 한글의 내어쓰기는 **둘째 줄부터 오른쪽으로 민다** (부록 A-15). 첫 줄은 `left` 에서 시작하고, 둘째 줄부터는 `left + 내어쓰기` 에서 시작한다. 그래서 각 값을 이렇게 정한다.
  - `left` = 기호 위치. 수준마다 `lists.indent_per_level` 씩 늘지만, 윗 수준의 글자 위치보다 왼쪽으로 가지는 않는다 (docx 와 같은 규칙).
  - `intent` = −내어쓰기
  - 내어쓰기 = 그 수준에서 가장 넓은 기호의 폭 + 0.5em (최소 3mm)
    - 번호 목록은 1–10번 기호 중 가장 넓은 것을 쓴다.
    - 폭은 docx 와 같은 어림셈이다: 한글·전각 글자 1em, 나머지 0.55em.
- 기호 뒤 탭이 첫 줄 글자를 둘째 줄과 같은 위치로 보내도록, 문단 모양은 "내어 쓰기용 자동 탭" 이 켜진 탭 정의(`tabPr autoTabLeft="1"`, 탭 항목 없음)를 가리킨다.
  - 내장 그릇에는 id 1 로 이미 있다. 사용자 그릇에 없으면 추가한다.
  - 기호가 내어쓰기보다 넓으면 탭이 기본 탭 위치로 넘어가 정렬이 어긋난다. 내어쓰기를 기호 폭으로 정하는 이유다.
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
| 코드 블록 | 한 문단에 줄마다 줄 바꿈(`lineBreak`)을 넣는다. 코드 글꼴을 쓴다. 배경은 문단 테두리/배경이다. 한글의 배경 상자는 문단의 왼쪽·오른쪽 여백과 앞뒤 간격까지 포함한 영역이고, `offset` 만큼 더 넓어진다 (M2a 시각 확인에서 확인). 그래서 문단 왼쪽·오른쪽 여백과 앞뒤 간격에 각각 2mm 를 두고, `offset` 은 모두 0 으로 둔다. 그러면 배경은 본문 폭에 맞고, 글자는 PDF 처럼 2mm 안쪽에서 시작한다. 코드 글꼴(Consolas)에는 한글 글자가 없으므로 한글 언어 묶음에는 본문 글꼴(맑은 고딕)을 지정한다 (Word 가 보여 주는 것과 같다). `connect="0"` 으로 두지만, 이어진 두 코드 블록은 배경이 맞닿아 하나처럼 보인다 (알려진 차이: PDF 는 블록 사이가 떨어져 있다) |
| 가로줄 | 아래 테두리만 있는 빈 문단 |
| 정의 목록 | 용어는 굵은 본문 문단, 정의는 한 수준 들여쓴 본문 문단 |
| 줄 블록 | 한 문단에 줄 바꿈 |
| Div | 안의 블록을 그대로 매핑 |

### 5.5 인라인

- 굵게, 기울임, 밑줄, 취소선, 위/아래 첨자, 인라인 코드:
  - 문단의 글자 모양을 바탕으로 조합마다 charPr 를 하나 만들어 재사용한다.
  - 인라인 코드는 코드 글꼴과 크기를 쓴다.
- 링크는 한글 고유의 하이퍼링크 필드다 (부록 A-5).
  - 구조: `fieldBegin`(type HYPERLINK) 런 → 링크 글자 런 → `fieldEnd` 런.
  - `fieldid` 는 상수 627600491 (`'%hlk'`)이다.
  - `id` 는 문서 안에서 겹치지 않는 수다.
  - `Command` 는 URL 의 `\`·`:`·`;` 를 `\` 로 escape 한 뒤 `;1;0;0;` 를 붙인 값이다.
  - `Path` 는 URL 원문이다.
  - 링크 글자는 파랑(#0000FF) 밑줄이다 (한글 기본, docx Hyperlink 스타일과 같음).
- 문서 안 링크(`#id`)는 글자만 쓴다. 책갈피는 M2b 이후다.
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
  - `width`·`height` 는 용지의 세로 방향 치수(HWPUNIT)다.
  - 세로 방향은 `landscape="WIDELY"`, 가로 방향은 `landscape="NARROWLY"` 로 쓴다 (부록 A-14).
- 내장 그릇에는 yaml 전체를, 사용자 그릇에는 yaml 에 적힌 값만 넣는다.

**여백 나누기.** 한글의 본문 시작 위치는 "위쪽 여백 + 머리말 높이" 다 (부록 A-9). 본문 끝도 같은 방식으로 "아래쪽 여백 + 꼬리말 높이" 만큼 위다. yaml 의 `margin.top`/`margin.bottom` 은 본문 시작·끝 위치를 뜻하므로 그대로 나눠 쓴다.

**글자 위치 모형** (부록 A-9, A-10 측정):
- 크기 s, 줄 높이 비율 r 인 한 줄은 한글에서 줄 위쪽 끝으로부터 0.85·s 아래에 기준선이 있고, 남는 높이는 모두 기준선 아래로 간다.
- PDF(`_lines(r)`)는 기준선이 줄 위쪽 끝으로부터 (0.8 + (r−1)/2)·s 아래다.

**머리말·꼬리말 문단 모양.** 머리말·꼬리말 문단은 `body` 의 글자 크기와 줄 높이를 쓴다. PDF 머리말이 본문 글자 설정을 물려받기 때문이다.

머리말과 꼬리말이 yaml 칸(`source: yaml`)일 때의 배치는 아래와 같다. 길이는 mm, T = `margin.top`, B = `margin.bottom` 이다.

1. **PDF 머리말 기준선.**
   - PDF 머리말 블록 아래 끝은 0.7·T 에 있다 (Typst `header-ascent` 30%).
   - `line: below` 이면 그 위에 1.5mm 간격과 0.5pt 선이 있다.
   - 기준선 y_h = 0.7·T − (선 있으면 1.5 + 0.18) − (0.2 + (r−1)/2)·s
2. **한글 머리말.**
   - `top` = max(0, y_h − 0.85·s)
   - `header` = T − `top`
   - 머리말 영역 세로 정렬은 위쪽(`vertAlign="TOP"`)이다.
3. **PDF 꼬리말 기준선**(본문 끝에서 아래로 잰 거리).
   - y_f = 0.3·B + (`line: above` 이면 1.5 + 0.18) + (0.8 + (r−1)/2)·s
4. **한글 꼬리말.**
   - `bottom` = 0, `footer` = B
   - 꼬리말 영역 세로 정렬은 위쪽이다.
   - 꼬리말 문단의 위 간격(`prev`) = max(0, y_f − 0.85·s)
   - 그러면 꼬리말 영역이 본문 끝에서 시작하고, 기준선이 PDF 와 같은 곳에 온다.
   - 위 간격이 머리말·꼬리말 영역 첫 문단에도 적용되는지는 한글 COM 테스트(§8.3)로 확인한다.
5. **선.**
   - `line: below` 는 문단 아래 테두리다. `offsetBottom` = max(0, 1.5 + (0.55 − r/2)·s)
   - `line: above` 는 문단 위 테두리다. `offsetTop` = max(0, 1.5 + ((r−1)/2 − 0.05)·s)
   - 알려진 차이: 한글의 테두리 상자는 문단 앞 간격을 포함하므로 (§5.4), 꼬리말의 `line: above` 선은 PDF 보다 꼬리말 위 간격만큼 위(본문 끝 근처)에 그려진다. 내장 템플릿은 꼬리말 선을 쓰지 않는다.
6. 사용자 그릇의 머리말을 그대로 쓰는 경우(`source: reference`):
   - `top` = max(0, T − 그릇의 `header`)
   - `bottom` = max(0, B − 그릇의 `footer`)
   - 그릇 머리말·꼬리말 높이는 유지한다.

결과적으로 세 형식의 본문 시작·끝 위치가 같다. 머리말·꼬리말 기준선은 PDF 와 1mm 안에서 맞춘다 (§8.3).

**알려진 차이:**
- 위 모형대로 본문 각 줄의 기준선은 PDF 보다 ((r−1)/2 − 0.05)·s 위에 온다. 본문 11pt·180% 에서 약 1.4mm 다.
- 줄 피치는 같지만, 줄 높이가 다른 문단이 바뀌는 곳(제목→본문)마다 몇 pt 차이가 생긴다.
- M2a 에서는 맞추지 않고 기록만 한다. 맞추려면 PDF·docx 의 줄 안 글자 위치를 바꿔야 하고, 그러면 골든을 다시 승인받아야 하기 때문이다. 사용자 결정 사항으로 남긴다.

### 6.2 머리말·꼬리말

`source: yaml` 인 경우:
- 그릇의 해당 머리말(또는 꼬리말) 컨트롤을 모두 지운다.
- 양쪽 공통(`applyPageType="BOTH"`) 컨트롤을 하나 넣는다.
- 내용은 문단 하나다.
  - header.xml 에 탭 정의를 하나 추가한다. 가운데 탭은 본문 폭의 1/2, 오른쪽 탭은 본문 폭 끝이다. `pos` 는 HWPUNIT × 2 다.
  - 왼쪽·가운데·오른쪽 칸을 탭(`<hp:tab width="0" leader="0" type="1"/>`, 한글이 열 때 폭을 다시 잰다)으로 나눈다 (docx 와 같은 방식).
  - subList `textWidth` = 본문 폭, `textHeight` = 머리말(꼬리말) 높이 (HWPUNIT).
  - 문단 스타일은 그릇의 "머리말" 스타일이다. 없으면 바탕글이다.
- 필드 처리:
  - `{{page}}` 는 쪽 번호 컨트롤(`autoNum numType="PAGE"`)이다.
  - `{{pages}}` 는 전체 쪽 수(`numType="TOTAL_PAGE"`)이다.
  - 나머지 필드는 텍스트다.
- `line: below/above` 이면 문단 아래/위 테두리를 그린다.
- 첫 쪽 감춤은 끈다. docx 에서 yaml 머리말일 때 titlePg 를 끄는 것과 같은 규칙이다.
  - `secPr/visibility` 의 `hideFirstHeader`/`hideFirstFooter` 를 "0" 으로 둔다.
  - 그릇 본문에 있던 `hp:pageHiding` 컨트롤은 본문과 함께 사라진다 (본문을 새로 만들기 때문).
  - 내장 그릇에는 둘 다 없어서 견본을 채취하지 않았다.

`source: reference` 인 경우:
- 그릇의 머리말을 그대로 두고, 그 안 텍스트의 `{{키}}` 만 채운다.
- `{{page}}`·`{{pages}}` 는 컨트롤로 바꾼다.

### 6.3 메타데이터

`Contents/content.hpf` 의 `opf:metadata`:
- 제목·작성자·키워드는 frontmatter 에서 가져온다. docx core 속성과 같은 값이다.
- mdcast 생성 정보는 docx 사용자 지정 속성과 같은 키(`mdcast.generator`, `mdcast.template.name`, `mdcast.template.version`, `mdcast.template.source`, `mdcast.pandoc`, `mdcast.typst`)로 `opf:meta` 에 넣는다.
- 한글은 모르는 meta 이름이 있어도 문서를 연다. 다만 한글에서 다시 저장하면 그 항목은 사라진다 (부록 A-11). mdcast 가 만든 파일 그대로일 때만 생성 정보가 남는다.
- 제목은 `opf:title`, 작성자는 `opf:meta name="creator"`, 키워드는 `opf:meta name="keyword"` 다 (한글이 쓰는 이름).
- `CreatedDate`·`ModifiedDate` 는 변환 시각(UTC, `YYYY-MM-DDThh:mm:ssZ`)으로 쓴다. `date` 는 비운다.

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
- 목표 오차는 0.5% (Word 비교와 같음). 견본에서는 0.1–0.3% 였다 (부록 A-10).
- 제목·본문 글자의 x 를 PDF 와 비교한다 (0.5mm 안).
- 목록은 첫 줄 글자 x 와 둘째 줄 x 가 같은지 본다 (0.5mm 안). PDF 와는 비교하지 않는다. PDF 목록은 한 단계 더 들여쓰는 것이 M1 부터의 알려진 차이이고, hwpx 는 docx 규칙을 따른다.
- 머리말·꼬리말 기준선을 PDF 와 비교한다 (1mm 안, §6.1).
- 본문 첫 줄 기준선은 §6.1 의 알려진 차이 값과 비교한다 (0.5mm 안).

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

## 부록 A. 견본 채취 결과 (2026-10-16)

스크립트는 `spikes/m2_samples/` 에 있다 (`capture.py`: 한글 동작으로 저장, `author*.py`: 손으로 만든 변형, `judge.py`: 한글로 열기·PDF·재저장).
- 기준 그릇은 한글 빈 문서 + 쪽 나눔 견본이다.
- 측정은 한글이 저장한 PDF 의 글자 기준선 위치(pypdfium2)로 했다.
- "재저장" 은 한글이 그 파일을 다시 hwpx 로 저장한 결과다.

**A-1 쪽 나눔.** 다음 문단의 `pageBreak="1"`.
```xml
<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="1" columnBreak="0" merged="0"><hp:run charPrIDRef="0"><hp:t>나</hp:t></hp:run></hp:p>
```

**A-2 머리말·꼬리말.**
- 첫 문단의 런 안 `hp:ctrl` 이다.
- 꼬리말은 `hp:footer` 이고 구조가 같다.
- COM `HeaderFooter` 의 `Type` 1 은 꼬리말이 아니라 짝수 쪽 머리말을 만들었다. 꼬리말 XML 은 손으로 만들었고, 한글 재저장으로 확인했다.
```xml
<hp:ctrl><hp:header id="1" applyPageType="BOTH"><hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP" linkListIDRef="0" linkListNextIDRef="0" textWidth="42520" textHeight="4252" hasTextRef="0" hasNumRef="0"><hp:p id="0" paraPrIDRef="9" styleIDRef="13" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="2"><hp:t>왼쪽<hp:tab width="2256" leader="0" type="1"/>쪽 </hp:t>…</hp:run></hp:p></hp:subList></hp:header></hp:ctrl>
```

**A-3 쪽 번호.** 런 안 `hp:ctrl`. 전체 쪽 수는 `numType="TOTAL_PAGE"`.
```xml
<hp:ctrl><hp:autoNum num="1" numType="PAGE"><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar="" supscript="0"/></hp:autoNum></hp:ctrl>
```

**A-4 탭.**
- 탭 정의는 `<hh:tabPr id autoTabLeft="0" autoTabRight="0"><hh:tabItem pos type="CENTER|RIGHT|LEFT" leader="NONE"/></hh:tabPr>` 이다.
- `pos` 는 **HWPUNIT × 2** 로 읽힌다.
  - 가운데 탭 `pos=21260` 에서 가운데 칸이 37.5mm 지점에 놓였다.
  - `pos=42520` 으로 바꾸니 75mm(본문 가운데) 지점에 놓였다.
- 본문의 탭 문자 `<hp:tab width="0" leader="0" type="1"/>` 는 받아들여진다. 한글이 열 때 폭과 종류를 다시 잰다.
- 머리말 `왼쪽칸 / 가운데칸 / 오른칸` 이 30.1mm / 가운데 105mm / 오른쪽 끝 179.9mm 에 놓였다.

**A-5 하이퍼링크.**
- 링크 글자 런을 `fieldBegin` 과 `fieldEnd` 가 감싼다.
- `fieldid` 627600491 = 0x25686C6B = `'%hlk'` (상수).
- 손으로 만든 필드도 열린다. `Command` 의 `\:`·`\;` escape 는 재저장 뒤에도 유지된다.
- 한글은 재저장할 때 `Path` 를 쿼리 없는 형태(`https://example.com/a`)로 다시 쓴다. `Command` 에는 전체 URL 이 남는다.
- 실제로 클릭해서 이동하는지는 시각 확인(§8.4)에서 사람이 본다.
```xml
<hp:run charPrIDRef="0"><hp:ctrl><hp:fieldBegin id="1221991324" type="HYPERLINK" name="" editable="0" dirty="1" zorder="-1" fieldid="627600491"><hp:parameters cnt="6" name=""><hp:integerParam name="Prop">0</hp:integerParam><hp:stringParam name="Command">https\://example.com/a?b=1&amp;c=2\;d=3#frag;1;0;0;</hp:stringParam><hp:stringParam name="Path">https://example.com/a</hp:stringParam><hp:stringParam name="Category">HWPHYPERLINK_TYPE_URL</hp:stringParam><hp:stringParam name="TargetType">HWPHYPERLINK_TARGET_BOOKMARK</hp:stringParam><hp:stringParam name="DocOpenType">HWPHYPERLINK_JUMP_CURRENTTAB</hp:stringParam></hp:parameters></hp:fieldBegin></hp:ctrl></hp:run>
<hp:run charPrIDRef="7"><hp:t>링크글</hp:t></hp:run>
<hp:run charPrIDRef="0"><hp:ctrl><hp:fieldEnd beginIDRef="1221991324" fieldid="627600491"/></hp:ctrl><hp:t> 뒤</hp:t></hp:run>
```
- 링크 글자 charPr 은 `textColor="#0000FF"` + `<hh:underline type="BOTTOM" shape="SOLID" color="#0000FF"/>` 이다.

**A-6 문단 테두리/배경.**
- borderFill 은 테두리 `NONE` + `<hc:fillBrush><hc:winBrush faceColor="#F6F8FA" hatchColor="#999999" alpha="0"/></hc:fillBrush>` 다.
- paraPr 는 `<hh:border borderFillIDRef offsetLeft offsetRight offsetTop offsetBottom connect="1" ignoreMargin="0"/>` 다.
- 연속 문단의 배경이 하나로 이어진다.
- `offset*` 은 HWPUNIT 그대로이고, 배경이 글자 영역 바깥으로 그만큼 넓어진다 (567 → 약 2mm).
- 가로줄: `bottomBorder type="SOLID" width="0.12 mm"` borderFill 을 가리키는 빈 문단이다.

**A-7 줄 바꿈.** `<hp:t>가<hp:lineBreak/>나</hp:t>`.

**A-8 개요 번호.**
- `numbering id=1` 의 각 `paraHead` 글자(`^1.` 등)를 비우면 번호가 사라진다.
- 그러나 `textOffset="50"`(%) 때문에 제목이 약 1.8mm 오른쪽에서 시작했다. `textOffset="0"` 으로 하면 제목 x 가 본문 x 와 같다.
- 개요 1–3 의 paraPr 는 왼쪽 여백이 있어(`left` 2000·4000·6000 → 3.5·7.1·10.6mm) 복사 후 0 으로 바꿔야 한다.
- 개요 문단은 `heading type="OUTLINE" idRef="0" level="0..6"` 이다.

**A-9 여백과 본문 시작.**
- 위쪽 여백 20mm 일 때, 머리말 15mm 이면 첫 기준선이 43.6mm, 머리말 0mm 이면 28.6mm 였다. 차이가 15.0mm 이므로 본문 시작 = `top` + `header` 다.
- 기준선은 줄 위쪽 끝에서 0.85·s 아래다 (10pt 160% 에서 3.0mm, lineseg `baseline=850`/`vertsize=1000` 과 같음).
- 머리말 글자 기준선도 `top` + 0.85·s 였다 (9pt, `top` 20mm → 22.7mm).

**A-10 줄 간격.**

| 측정 | 결과 | 기대 |
|---|---|---|
| 11pt, `PERCENT 180` | 19.78pt | 19.8pt |
| 16pt, `PERCENT 130` | 20.74pt | 20.8pt |
| 10pt, `PERCENT 100` | 3.51mm | 3.53mm |

**A-11 메타데이터.**
- `opf:meta name="mdcast.generator"` 가 있어도 열린다. 재저장하면 사라진다.
- 제목·작성자·키워드는 `opf:title`, `creator`, `keyword` 그대로 유지된다.
- 한글이 새로 저장하면 `creator` 에 Windows 사용자 이름이 들어간다. 그래서 내장 그릇에서는 비운다 (§4.4).

**A-12 문단 여백 단위.**
- 10pt 100% 문단에 `left=2834`, `prev=2000`, `next=2000` 을 넣고 쟀다.
  - 둘째 줄 글자 x = 5.0mm (2834 → 1417 HWPUNIT)
  - 앞 간격 = 3.53mm, 뒤 간격 = 3.53mm (2000 → 1000 HWPUNIT)
- 즉 paraPr `margin` 값은 **HWPUNIT × 2** 다. 한글 개요 1 의 `left=2000` 이 한글 화면의 "왼쪽 여백 10pt" 인 것과도 맞는다.
- 양수 `intent`(첫 줄 들여쓰기)는 예상과 다르게 나왔다 (1417 → 12.5mm). mdcast 는 양수 `intent` 를 쓰지 않으므로 더 조사하지 않았다.

**A-13 첫 문단.**
- secPr 런을 첫 블록 문단(개요 제목 포함) 맨 앞에 넣으면, 빈 첫 줄 없이 그 블록이 첫 줄에 놓인다.
- 빈 첫 문단을 남기면 모든 기준선이 한 줄 아래로 밀린다.

**A-14 가로 방향.**
- `landscape="NARROWLY"` + 세로 치수(59528×84186), `landscape="WIDELY"` + 바꾼 치수(84186×59528) 둘 다 296.7×209.9mm 쪽이 된다.
- 재저장해도 각자 그대로 남는다.
- mdcast 는 앞의 형태(세로 치수 + `NARROWLY`)를 쓴다. 세로 방향 그릇은 `WIDELY` 다.

**A-15 목록 내어쓰기와 탭.**
- `left=5668`, `intent=-2834` (값 그대로, 즉 10mm / 5mm) 문단에서 첫 줄은 10mm, 둘째 줄부터는 15mm 에서 시작했다. 한글의 내어쓰기는 둘째 줄을 오른쪽으로 민다.
- 탭 정의에 탭 항목이 없으면, 기호 뒤 탭은 기본 탭 간격(secPr `tabStop`)으로 가서 글자가 14.1mm 에 놓였다. 둘째 줄과 어긋난다.
- 다음 두 방법 모두 첫 줄 글자가 둘째 줄과 같은 15.0mm 에 놓였다.
  - `autoTabLeft="1"` 탭 정의(내장 그릇 id 1)
  - 15mm 위치의 `LEFT` 탭 항목
- 기호 `(가)` 처럼 내어쓰기(5mm)보다 넓은 기호는 탭이 다음 기본 탭 위치로 넘어갔다.

**A-16 글자 모양** (`capture_chars.py`, 한글 동작으로 저장).
- 굵게·기울임·위첨자·아래첨자는 각각 `<hh:bold/>`, `<hh:italic/>`, `<hh:supscript/>`, `<hh:subscript/>` 이다.
- 취소선은 `<hh:strikeout shape="SOLID" color="#000000"/>`, 밑줄은 `<hh:underline type="BOTTOM" shape="SOLID" color="…"/>` 이다.
- 모두 `fontRef`·`ratio`·`spacing`·`relSz`·`offset` 다음에 온다.
- 글꼴을 맑은 고딕으로 바꾸면 한글은 7개 언어 묶음 모두에 다음 항목을 넣는다.
  ```xml
  <hh:font face="맑은 고딕" type="TTF" isEmbedded="0"><hh:typeInfo familyType="FCAT_GOTHIC" weight="5" proportion="3" contrast="2" strokeVariation="0" armStyle="0" letterform="2" midline="0" xHeight="4"/></hh:font>
  ```
  - 한글은 이 글꼴을 목록 맨 앞(id 0)에 넣고 나머지 id 를 다시 매겼다. mdcast 는 목록 끝에 덧붙인다. id 로만 가리키므로 어느 쪽이든 된다.
  - 각 묶음의 `fontCnt` 도 함께 바뀐다.

**A-17 짝수 규칙** (M2a 구현 중, 2026-10-16).
- 2배로 쓰는 값(문단 여백, 탭 위치)은 **짝수여야 한다**.
- 꼬리말 문단 위 간격을 3321 로 쓰자 꼬리말이 쪽 아래 바깥(314mm)에 놓였다. 3320 으로 바꾸자 PDF 와 같은 290.8mm 에 놓였다.
- 홀수 값은 다른 단위로 읽히는 것으로 보인다. A-12 에서 양수 `intent` 1417 이 12.5mm 로 나온 것도 같은 원인이다.
- 그래서 `para_unit` 은 `2 × hwpunit` 으로 계산한다.
- 또 secPr 런의 글자 모양은 첫 문단 글자 모양으로 바꾼다. 그릇의 10pt 글자 모양이 남아 있으면 첫 줄 높이가 그 크기를 따르기 때문이다 (첫 문단이 코드 블록일 때 13.08pt).

**A-18 코드 줄 간격** (알려진 차이).
- 9.5pt·130% 코드 블록의 줄 피치가 두 줄 블록에서 12.24pt, 세 줄 블록에서 12.36pt 였다. 기대값은 12.35pt 다.
- 글꼴을 바꿔도(한글 묶음 맑은 고딕) 같았고, 원인은 찾지 못했다.
- 줄당 0.1pt 차이라 테스트 허용 오차를 1% 로 두었다.
