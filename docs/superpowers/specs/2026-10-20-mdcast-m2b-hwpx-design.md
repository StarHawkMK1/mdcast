# M2b hwpx 표·이미지·각주 설계 (2026-10-20)

상위 스펙: `2026-10-15-mdcast-design.md` (§0.3 원칙, §3 템플릿, §4.1 내보내기, §7.4 hwpx 검증). 앞 단계: `2026-10-16-mdcast-m2a-hwpx-design.md` (이하 "M2a"). M2a 의 구조·원칙·용어(그릇, 모양, Notice, 견본 채취)를 그대로 잇는다.

## 0. 배경

M2a 는 hwpx 에서 표·이미지·각주를 글자로 낮춰 썼다 (M2a §5.6). 한국 보고서·제출 서류는 거의 언제나 표가 들어가므로, 이대로는 hwpx 출력을 실제로 쓰기 어렵다. M2b 는 이 세 가지를 한글 고유 개체로 만든다.

### 0.1 사용자 예시 문서에서 읽은 것

사용자가 예시로 준 파일: 제출 양식에 맞춰 작성한 제품규격서 hwpx (회사 자체 템플릿이 아님, 각주 없음). 구조만 읽었고 내용은 옮기지 않는다. **이 파일은 저장소에 넣지 않는다** (외부 제출 서류이고 문서 보안 추적 메타데이터가 들어 있다).

| 관찰 | 값 |
|---|---|
| 개체 수 | 표 15, 그림 13. 그림 13개가 **모두 표 칸 안**에 있다 (그림 + 설명을 2×2, 2×1 표로 배치) |
| 병합 셀 | 머리행 2줄: 앞 칸들은 `rowSpan=2`, 뒤 칸은 `colSpan=3`. 가려진 칸은 `hp:tc` 를 쓰지 않는다 (3×6 표에 칸 13개) |
| 머리행 | `hp:tc header="1"`, `hp:tbl repeatHeader="1"`, 머리행 배경 `#E5E5E5` |
| 테두리 | 칸마다 `borderFillIDRef`. 네 변 모두 `SOLID 0.12 mm #000000` (바깥·안쪽 같은 굵기) |
| 칸 | `subList vertAlign="CENTER"`, `cellMargin` 좌우 510 · 상하 141 (HWPUNIT) |
| 표 위치·폭 | `hp:pos treatAsChar="1"` (글자처럼 취급), 폭 48109 ≈ 본문 폭 170mm, `pageBreak="CELL"` |
| 그림 | `hp:pic` + `hc:img binaryItemIDRef="imageN"`, 그림 파일은 `BinData/imageN.png`, `content.hpf` manifest 에 `isEmbeded="1"` 로 등록. `header.xml` 에 binDataList 없음. 글자처럼 취급, 원본보다 축소(`curSz` < `orgSz`), `shapeComment` 에 원본 이름 |
| 캡션 | 없음 (`hp:caption` 0개). 표 제목은 일반 문단 |

이 문서의 표 모양(병합 머리행, 칸 안 그림 배치, 긴 표의 머리행 반복)을 **MD 로 표현해 hwpx 로 낼 수 있는 것**이 M2b 의 실사용 목표다. 테두리 굵기·머리행 색은 템플릿 설정으로 맞춘다 (§4.4).

## 1. 범위

| 포함 | 내용 |
|---|---|
| 표 | 병합 셀(colspan·rowspan), 열 너비, 테두리(안쪽·바깥), 머리글 행과 쪽 넘김 시 반복, 줄무늬, 첫 열, 칸 가로·세로 정렬, 칸 안쪽 여백, 표 글자 크기·줄 간격, 표 종류(`<!-- table: 이름 -->`), 캡션 |
| 칸 안의 블록 | 문단, 개조식 목록, 코드, 인용, 이미지, 중첩 표, 각주 |
| 이미지 | 인라인 이미지, 그림(캡션 있는 이미지), 크기 속성(`{width=…}`), `figures.max_width`·`figures.align` 적용, 대체 문구 |
| 각주 | 한글 각주 개체. 번호는 한글이 매긴다 |

**비목표** (M2b 에서 하지 않음):
- 수식 (M4, M2a 처럼 LaTeX 원문 유지).
- 책갈피, 문서 안 링크(`#id`), 표·그림 상호 참조 (M2a 처럼 글자만).
- 미주, 그림 글 어울림(본문이 그림을 둘러싸기), 대각선 칸, 칸 안 글자 방향.
- docx·pdf 쪽의 `figures.max_width`·`figures.align` 적용 (M1 보류 항목 그대로. hwpx 만 이번에 적용한다).
- hwpx 가져오기 (M3).

**반목표** (기능은 돌아가도 이러면 실패):
- 한글에서 "손상" 또는 "복구" 안내가 뜬다.
- 표나 그림이 본문 폭을 넘어 쪽 밖으로 나간다.
- 어떤 입력이든 변환이 거부된다 (상위 §0.3 무거부). 못 만드는 것은 낮춰 쓰고 알린다.
- 견본으로 확인하지 않은 XML 을 추측으로 쓴다 (M2a §2).

## 2. 방식: 견본 채취 먼저

**2026-10-20 수행 완료.** 결과는 부록 B 에 있고, §4–§6 에 반영했다.

M2a 와 같다. 한글 COM 으로 기능을 하나씩 넣은 문서를 hwpx 로 저장하고, XML 조각과 `header.xml`·`content.hpf` 변화를 읽는다. 스크립트는 `spikes/m2b_samples/`, 결과는 이 문서의 "부록 B" 에 붙인다. 결과가 이 문서의 가정과 다르면 해당 절을 고친 뒤 구현한다.

| # | 견본 | 확인할 것 |
|---|---|---|
| B-1 | 기본 표 2×3 | `hp:tbl`·`hp:tr`·`hp:tc` 필수 속성, `cellAddr`·`cellSpan`·`cellSz`, `subList`, 표를 담은 문단 모양 |
| B-2 | 병합 (가로·세로·둘 다) | 가려진 칸 생략 규칙, `rowCnt`·`colCnt`, 병합 칸의 `cellSz` |
| B-3 | 칸 높이를 실제 내용보다 작게 쓴 표 | `linesegarray` 없이 열었을 때 한글이 행 높이를 내용에 맞춰 늘리는지. 안 늘리면 §4.3 의 대안을 쓴다 |
| B-4 | 바깥 굵게·안쪽 가늘게, 색 테두리 | 칸별 `borderFill` 로 표현되는지, `width` 에 쓸 수 있는 값(한글 선 굵기 목록), pt → mm 반올림 |
| B-5 | 칸 배경, 머리행 반복, 표 쪽 넘김 | `fillBrush`, `header="1"`, `repeatHeader`, `pageBreak` 값별 동작 |
| B-6 | 칸 안쪽 여백 | `tbl/inMargin` 과 `tc/cellMargin`·`hasMargin` 의 관계 |
| B-7 | 칸 세로 정렬, 칸 안 문단 정렬 | `subList vertAlign`, 칸 문단의 `paraPr` |
| B-8 | 한글 캡션을 단 표·그림 (위·아래) | `hp:caption` 표현, 자동 번호 없이 글자만 넣을 수 있는지, 캡션이 개체와 같은 쪽에 붙는지 |
| B-9 | 그림 (PNG 하나) | `hp:pic` 전체, BinData 이름·압축, manifest 항목, `orgSz`·`curSz`·`imgDim` 과 픽셀·DPI 의 관계 |
| B-10 | 칸 안 그림 | 예시 문서와 같은 배치가 그대로 되는지 |
| B-11 | 이미지 형식 PNG·JPEG·GIF·BMP·WebP·SVG | 한글 2020 이 각각을 보여 주는지 (보여 주지 못하는 형식은 §5.1 대로 PNG 로 바꾼다) |
| B-12 | 각주 | `hp:footNote` 표현, 번호(`autoNum`), 각주 안 여러 문단·목록, 각주 안 표·그림, 칸 안 각주, 각주 안 각주가 되는지, 스타일 "각주", `footNotePr` |
| B-13 | 칸 안 표 (중첩) | 중첩 표의 표현과 폭 |
| B-14 | 같은 그림을 두 번 넣은 문서 | BinData 를 하나만 두고 두 번 참조해도 되는지 |

## 3. 구조

M2a §4 의 경계를 지킨다: `src/mdcast/hwpx/` 는 mdcast 의 다른 모듈을 import 하지 않고, 파일 입출력도 하지 않는다. 이미지를 읽고 템플릿 설정을 값으로 바꾸는 일은 어댑터(`src/mdcast/writers/hwpx.py`)가 한다.

### 3.1 입력 값 추가 (`hwpx/look.py`)

모두 frozen dataclass, 단위는 M2a 와 같다 (길이 mm, 글자 pt, 색 `#RRGGBB`).

- `Border(width_pt, color)`.
- `TableLook`: `width` (`"full"`·`"auto"`), `font_size`, `cell_padding`, `line_height`, `border`, `border_outer`, 머리행(`background`, `bold`, `align`, `valign`, `repeat`), 본문(`align`, `valign`, `zebra`), 첫 열(`bold`, `background`). 어댑터가 `table_settings(config, variant)` (기존 `filters/tables.py`) 결과로 만든다.
- `Image(data, ext, width_px, height_px, dpi)`: 어댑터가 읽어 둔 그림 한 장.
- `Settings` 에 더할 것:
  - `tables: dict[str | None, TableLook]`: 표 종류 이름 → 모양 (`None` 은 기본).
  - `images: dict[str, Image]`: 이미지 주소 → 그림. 여기 없는 주소는 어댑터가 이미 자리표시로 바꿔 둔 것이다 (§5.1).
  - `figure_max_ratio` 와 `figure_max_mm` (`figures.max_width` 가 `%` 면 비율, `mm` 같은 길이면 길이. 둘 중 하나만 채운다), `figure_align` (`figures.align`).

### 3.2 표 종류를 표마다 전달

지금은 표 필터가 표 종류를 docx 용 기록 목록(`ctx.state["tables"]`)에만 남긴다. hwpx 는 표마다 종류를 알아야 하므로, 필터가 대상이 hwpx 일 때 표의 속성에 `mdcast-variant=<이름>` 을 붙이고 SectionWriter 가 이를 읽어 `settings.tables` 에서 모양을 고른다. 속성이 없거나 모르는 이름이면 기본 모양이다 (모르는 이름은 필터가 이미 `TABLE_VARIANT_UNKNOWN` 으로 알린다).

### 3.3 본문 폭을 먼저 확정

지금은 쪽 설정이 문단을 다 만든 뒤 `assemble()` 에서 적용된다. 표 폭과 그림 최대 폭이 본문 폭에 달려 있으므로, 쪽 설정을 먼저 적용하고 본문 폭(`page.body_width`)을 SectionWriter 에 넘긴다.

### 3.4 새 모듈

표는 `hwpx/table.py`, 그림과 BinData 등록은 `hwpx/picture.py`, 각주는 SectionWriter 안 또는 `hwpx/note.py`. 나누는 방식은 구현자가 정한다. 칸·각주 안의 블록은 같은 SectionWriter 의 블록 처리를 재귀로 써서 만든다 (목록·코드·인용 규칙을 다시 쓰지 않는다).

## 4. 표

### 4.1 격자

- 행 순서: `table.head` 행 → 본문마다 (`body.head` 행, `body.content` 행) → `table.foot` 행.
- pandoc 칸의 `colspan`·`rowspan` 으로 격자를 채우며 `cellAddr`(열·행)를 매긴다. 다른 칸에 가려진 자리는 `hp:tc` 를 쓰지 않는다 (예시 문서와 같음, B-2 로 재확인).
- 표 밖으로 나가는 span 은 표 끝에서 자른다. 칸이 모자란 행은 빈 칸으로 채워 격자를 직사각형으로 만든다. 행이나 열이 하나도 없는 표는 표를 만들지 않고 캡션만 쓴다. 어느 경우도 거부하지 않는다.

### 4.2 폭

- 쓸 수 있는 폭 = 지금 위치의 폭: 본문 폭에서 목록·인용 들여쓰기를 뺀 값. 칸 안의 표라면 그 칸의 안쪽 폭.
- `width: full`: 표 폭 = 쓸 수 있는 폭. 열 너비는 colspec 비율을 합이 1 이 되게 늘려 나눈다 (grid table 은 원문 폭 비율이 와서 합이 1 보다 작다. 예: 0.65). 필터가 기본 너비(`ColWidthDefault`)를 이미 1/n 로 바꿔 두므로 pipe table 은 대개 같은 너비가 된다.
- `width: auto`: 한글은 열 때 자동 맞춤을 하지 않으므로 mdcast 가 계산한다. colspec 비율이 있으면 비율 × 쓸 수 있는 폭이다. 없으면 열마다 가장 긴 칸 글자의 대략 폭(`text_em`, 표 글자 크기 기준) + 안쪽 여백으로 잡는다. 열 하나는 최소 10mm. 합이 쓸 수 있는 폭을 넘으면 비율대로 줄인다.
- 병합 칸의 `cellSz width` 는 덮은 열 너비의 합이다. 반올림 때문에 열 너비 합이 표 폭과 어긋나면 마지막 열에서 맞춘다.

### 4.3 높이

칸 높이에는 최소값(표 글자 크기의 한 줄 높이 + 위아래 안쪽 여백)을 쓰고, 한글이 내용에 맞춰 늘리는 것에 기댄다. B-3 에서 확인했다: `cellSz height=100` 으로 써도 한글이 행을 내용에 맞춰 늘려 그리고, 다시 저장하면 표 `sz height` 를 새로 계산한다.

### 4.4 모양 (`tables.*` 설정)

hwpx 표 모양은 docx·pdf 와 같은 템플릿 `tables` 설정을 따른다. 그래서 내장 템플릿의 hwpx 표는 예시 문서와 다르게 나온다 (안쪽 0.5pt, 바깥 1pt, 머리행 `#F2F2F2`). 예시 문서 같은 모양은 템플릿의 표 종류로 만든다. 예: `variants: { 제출양식: { border: {width: 0.34pt}, border_outer: {width: 0.34pt}, header: {background: "#E5E5E5"} } }`. 0.12mm 가 약 0.34pt 다.

| 설정 | hwpx 표현 |
|---|---|
| `border`, `border_outer` | 한글 테두리는 칸마다 있다. 칸마다 `borderFill` 을 만든다: 표 바깥에 닿는 변은 `border_outer`, 안쪽 변은 `border`. 굵기는 pt 를 mm 로 바꿔 한글 굵기 목록(B-4)에서 가장 가까운 값을 쓴다 (같은 거리면 굵은 쪽, 알리지 않음). 0.5pt → `0.2 mm`, 1pt → `0.4 mm`, 0.34pt → `0.12 mm`. 같은 조합은 `borderFill` 하나를 함께 쓴다 |
| `header.background` / `body.zebra` / `first_column.background` | 칸 배경. 겹치면 머리행 > 첫 열 > 줄무늬 순 (Word 의 조건부 서식 우선순위와 같음). 줄무늬는 본문 짝수 행 |
| `header.repeat` | 머리행 칸 `header="1"`, 표 `repeatHeader="1"`. 표 쪽 넘김은 칸 단위(`pageBreak="CELL"`, 예시 문서와 같음) |
| `header.bold`, `header.align`, `first_column.bold`, colspec 정렬 | 필터가 모든 형식에 이미 적용한다 (굵게는 `Strong`, 정렬은 칸·열 정렬). hwpx 는 칸 정렬을 칸 문단 정렬로 쓴다 |
| `header.valign`, `body.valign` | `subList vertAlign` (`top`·`middle`·`bottom` → `TOP`·`CENTER`·`BOTTOM`) |
| `cell_padding` | 칸 안쪽 여백 네 변: 표 `inMargin` 네 변 = 여백, 칸마다 `cellMargin` 도 같은 값, `hasMargin="0"` (B-6) |
| `font_size`, `line_height` | 칸 문단의 글자 크기와 줄 간격. 칸 문단의 앞뒤 간격은 0 (docx 내장 그릇과 같음) |

- `body.head` 행 (pandoc 의 본문 중간 머리행. MD 표 문법으로는 생기지 않는다)과 `table.foot` 행은 본문 행 모양이다. 필터가 머리행 굵게·정렬을 `table.head` 에만 넣으므로 그와 맞춘다.
- **첫 열은 격자 기준이다.** 위 행의 rowspan 이 덮은 행에서는 `row.content[0]` 이 0열이 아니다. 지금 필터의 `first_column.bold` 는 `row.content[0]` 을 굵게 해서 이런 행에서 엉뚱한 칸을 굵게 한다. M2b 에서 필터를 격자 0열 기준으로 고친다 (docx·pdf 도 같이 고쳐진다. `first_column.bold` 를 켠 표에서 첫 열을 rowspan 으로 묶은 경우에만 결과가 바뀐다). hwpx 의 첫 열 배경도 격자 0열에 칠한다.
- 표를 담은 문단은 지금 위치의 본문 문단 모양을 쓴다. 표는 **글자처럼 취급하지 않는다** (`treatAsChar="0"`, `horzRelTo="PARA"`): 글자처럼 취급한 표는 한글이 쪽을 넘겨 나누지 않는다 (B-5 정정, 2026-10-20 구현 중 확인). 표 위·아래 바깥 여백은 1mm(283)이고, 표 바로 다음 문단의 앞 간격을 아래 여백에 더한다 (한글은 떠 있는 표 바로 아래에 다음 문단을 놓아 그 문단의 앞 간격이 사라진다). 표가 쓸 수 있는 폭보다 좁으면 왼쪽에 둔다.
- **사용자 reference.hwpx 를 쓸 때도 표 모양 설정을 모두 적용한다.** hwpx 에는 docx 의 표 스타일 같은 "그릇이 가진 표 모양"이 없으므로, 템플릿에 쓴 값 + 내장 기본값으로 만든다. docx 는 사용자 그릇의 표 스타일이 이기므로 이 점이 다르다. README 에 적는다.

### 4.5 칸 내용

- 칸의 블록은 SectionWriter 로 만든 문단이 `subList` 에 들어간다. 글자 크기·줄 간격은 §4.4 의 표 값, 그 밖의 글자·문단 모양은 본문 모양에서 시작한다.
- 목록·인용·코드는 칸 안에서 같은 규칙으로 들여 쓴다 (기준은 칸의 왼쪽 안쪽).
- 칸 안 이미지는 칸 안쪽 폭을 최대 폭으로 쓴다 (§5.2).
- 칸 안 표는 칸 안쪽 폭을 쓸 수 있는 폭으로 하는 중첩 표다 (B-13 에서 한글이 받음을 확인).
- 칸 안의 쪽 나눔 표시는 무시한다.

### 4.6 캡션

캡션 글자는 지금처럼 번호 필터가 `<표 {n}> {text}` 형식으로 만들어 둔다. hwpx 에서는 **한글 캡션(`hp:caption`)** 에 자동 번호 없이 그 글자만 넣는다 (B-8 에서 확인: 자동 번호 없는 캡션이 표·그림에 붙어 그려진다). 캡션이 개체와 함께 움직인다. 위치는 `tables.caption.position` (`above` → `TOP`, `below` → `BOTTOM`). 캡션 문단은 `caption` 요소의 모양·스타일이다.

그림 캡션도 같은 방식이다 (`figures.caption.position`). 캡션을 잃은 경우(행·열이 없는 표)에는 캡션 문단만 쓴다.

## 5. 이미지

### 5.1 읽기

- 어댑터가 문서의 이미지를 docx·pdf 와 같은 규칙으로 읽는다: `writers/images.py` 의 로컬·원격 읽기, `--offline`, 시간 제한, 20MB 상한. 읽은 바이트는 `settings.images` 로 넘긴다. 파일로 쓸지(`localize_images` 재사용) 메모리로만 들고 있을지는 구현자가 정한다.
- 형식은 바이트로 판별한다. 지금 `_extension()` 에는 BMP 판별이 없으므로 더한다 (PDF 의 strict 허용 목록과 오류 문구는 그대로 둔다). hwpx 가 그대로 넣는 형식은 PNG·JPEG·GIF·BMP·SVG 다 (B-11).
- 한글이 보여 주지 못하는 형식은 **PNG 로 바꿔 넣는다.** B-11 결과 WebP 만 해당한다 (PNG·JPEG·GIF·BMP·SVG 는 그대로 넣는다). 바꾸는 데는 이미 실행 의존성인 typst 를 쓴다 (그림 하나만 든 쪽을 그림 크기로 만들어 PNG 로 내보낸다. 해상도는 구현자가 정하되 화면에서 흐리지 않게). 자리표시로 두면 docx·pdf 에서는 보이는 그림이 hwpx 에서만 사라진다.
- 읽지 못하거나 손상되었거나 PNG 로 바꾸지 못한 그림은 docx·pdf 와 같이 `[이미지: 설명]` 자리표시로 바꾸고 `IMAGE_FETCH_FAILED` 를 알린다. 그림을 잃은 그림 블록은 캡션 글자를 남긴 문단이 된다 (기존 `localize_images` 동작과 같음).
- M2a 의 "이미지는 M2b 에서 지원" 알림은 없앤다.
- 픽셀 크기와 DPI 는 PNG(`IHDR`, `pHYs`)·JPEG(SOF, JFIF 밀도)·GIF·BMP·WebP 머리에서 읽는다. SVG 는 루트의 `width`·`height` (단위 없음·`px` 는 px, `pt`·`mm`·`cm`·`in` 은 96dpi 로 환산), 없으면 `viewBox` 의 폭·높이, 그것도 없으면 300×150 (브라우저 기본값)으로 본다. 실행 의존성에 Pillow 가 없으므로 직접 읽는다 (어댑터 쪽 `writers/images.py`). DPI 정보가 없으면 96 으로 본다. PNG 로 바꾼 그림은 바꾼 결과에서 읽는다. 크기를 읽지 못한 그림은 자리표시로 바꾼다.

### 5.2 크기

1. 원래 크기 = 픽셀 ÷ DPI. (한글은 그림을 넣을 때 DPI 를 무시한다(B-9). mdcast 는 docx·pdf 와 같은 크기가 되도록 DPI 를 쓴다.)
2. pandoc 크기 속성 (`width`·`height`: `%`, `mm`, `cm`, `in`, `px`, 단위 없는 값은 px)이 있으면 그것을 쓴다. `%` 는 쓸 수 있는 폭에 대한 비율이다. 하나만 있으면 가로세로 비율을 지킨다.
3. 상한 = `figures.max_width` 가 비율이면 비율 × 쓸 수 있는 폭, 길이면 그 길이와 쓸 수 있는 폭 중 작은 값. 폭이 상한을 넘으면 비율을 지켜 줄인다. 이 상한은 인라인 이미지에도 적용한다 (쪽 밖으로 나가지 않게).
4. 쓸 수 있는 폭은 §4.2 와 같다 (칸 안이면 칸 안쪽 폭).

### 5.3 배치

- 인라인 이미지: 문단의 run 안에 글자처럼 취급하는 `hp:pic`.
- 그림(pandoc `Figure`): 그림만 든 문단을 `figure_align` 으로 정렬하고, 캡션은 §4.6 대로.
- 대체 문구(alt)는 `shapeComment` 에 넣는다.

### 5.4 패키지 등록

- 그림 파일은 `BinData/` 아래에 그릇의 기존 항목과 겹치지 않는 이름으로 넣고 (deflate 압축), `content.hpf` manifest 에 `isEmbeded="1"` 항목을 더한다 (예시 문서와 같음, B-9 로 재확인).
- 같은 바이트의 그림이 여러 번 나오면 파일 하나를 함께 참조한다 (B-14 에서 한글 자신이 그렇게 저장함을 확인).
- 그릇에 원래 있던 BinData(머리말 로고 등)는 그대로 둔다.

## 6. 각주

- pandoc `Note` 를 한글 각주 개체로 만든다. 번호는 한글이 매기고, 번호 모양·구분선·위치는 그릇의 `footNotePr` 를 따른다 (내장 그릇은 한글 기본값).
- 각주 내용의 블록은 SectionWriter 로 만든 문단이 각주 안에 들어간다. 모양은 `footnote` 요소의 모양과 스타일(기본 "각주")이다. 목록·코드도 같은 규칙.
- 칸 안 각주는 각주로 만든다 (B-12 확인).
- 각주 안의 표·그림도 개체로 만든다 (각주 안 표는 B-12 에서 확인. 그림은 같은 `hp:pic` 이므로 §8.3 한글 테스트로 확인한다). (각주 안 표는 docx 용 표 기록에서 빠진다(`_in_footnote`). hwpx 는 그 기록을 쓰지 않고 표 속성의 `mdcast-variant` 를 읽으므로 상관없다.)
- 한글이 각주를 담지 못하는 자리(각주 안 각주: B-12 에서 한글이 거부. 캡션 안 각주: 확인하지 않았으므로 같이 낮춘다)에서는 거부하지 않는다. 그 각주만 M2a 방식으로 낮춘다: 본문에 `[주 n]`, 문서 끝에 `[주 n] 내용` 문단. `n` 은 낮춘 각주끼리 따로 센다 (한글 각주 번호 1, 2, 3 과 겹쳐 보이지 않게 `주` 를 붙인다). 처음 한 번 `RENDER_WARNING` 으로 알린다.
- M2a 의 "각주는 M2b 에서 지원" 알림은 없앤다.

## 7. 알림

- `_DEGRADED` 의 table·image·footnote 항목은 없앤다. math 는 남긴다 (M4).
- 새로 낮춰 쓰는 경우(각주를 못 담을 때)는 M2a 와 같이 종류마다 문서당 한 번 `RENDER_WARNING`(`format=hwpx`, `element=<종류>`)으로 알린다.
- 이미지 실패는 docx·pdf 와 같은 `IMAGE_FETCH_FAILED` 다.
- 테두리 굵기 반올림, 열 너비 보정, 빈 칸 채우기는 알리지 않는다.

## 8. 검증

### 8.1 구조 테스트 (한글 없이, CI)

- 병합 표: `cellAddr`·`cellSpan`, 가려진 칸 생략, `rowCnt`·`colCnt`, 열 너비 합 = 표 폭, 병합 칸 폭 = 덮은 열의 합.
- 칸별 `borderFill`: 바깥 변 = `border_outer`, 안쪽 변 = `border`. 배경 우선순위. 머리행 `header="1"` 과 `repeatHeader`.
- 표 종류가 표마다 다른 모양을 쓰는지. 사용자 reference.hwpx 에서도 표 모양이 적용되는지.
- 그림: BinData 항목·manifest 항목·`binaryItemIDRef` 가 서로 맞는지, 크기 계산(원래 크기, `%`·mm 속성, 비율·길이 상한, 칸 안 상한), BMP 판별, 한글이 못 보여 주는 형식의 PNG 변환, 실패 시 자리표시와 `IMAGE_FETCH_FAILED`.
- 필터의 첫 열 굵게가 rowspan 표에서 격자 0열에 들어가는지 (docx·pdf 포함).
- 각주 XML, 각주 안 목록, 낮춰 쓰는 경우.
- 모든 XML 이 잘 짜였고, 참조하는 id(`borderFillIDRef`, `paraPrIDRef`, `charPrIDRef`, `binaryItemIDRef`)가 모두 있는지.

### 8.2 거부 금지

기존 무거부 속성 테스트에 더한다: 무작위 span 의 표, 칸이 모자란 행, 빈 표, 칸 안 표·그림·각주, 없는 이미지, 깨진 이미지, 각주 안 각주.

### 8.3 한글 COM 테스트 (`--run-hangul`)

M2a §8.3 에 더한다. 새 픽스처와 kitchen-sink 에 대해:
- `Open` 이 True, 손상·복구 안내 없음.
- `GetTextFile("UNICODE")` 에 칸 글자와 각주 글자가 있다.
- 개체 목록(`HeadCtrl` 부터 따라가기)에서 표·그림·각주 개수가 기대값과 같다.
- PDF 로 저장해 쪽 수를 확인하고, 긴 표가 다음 쪽에서 머리행을 반복하는지 본다.

### 8.4 픽스처

`tests/fixtures/md/tables-images.md` (합성, 예시 문서의 구조만 흉내):
- 2단 머리행 병합 표 (rowspan 2 + colspan 3, grid table 문법).
- 그림 + 설명을 2×2 로 둔 표 (칸 안 그림).
- 쪽을 넘기는 긴 표 (머리행 반복 확인).
- `제출양식` 같은 표 종류를 쓴 표 (§4.4 예시의 variant 는 픽스처용 템플릿에 둔다).
- 크기 속성이 있는 그림과 없는 큰 그림 (상한 확인), 인라인 이미지, 캡션 있는 그림.
- 본문 각주, 칸 안 각주, 목록이 든 각주.

### 8.5 시각 확인

`scripts/render_pages.py` 로 kitchen-sink 와 새 픽스처의 hwpx 를 PNG 로 만들어 사용자가 보고 승인한다. 같은 픽스처의 docx·pdf 와 나란히 놓고 표 모양이 같은 템플릿으로 보이는지 비교한다.

## 9. M2b 완료 기준

- 전체 테스트 통과 (`uv run python -m pytest -q`).
- kitchen-sink.hwpx 와 tables-images.hwpx 가 한글에서 오류·복구 안내 없이 열리고, §8.3 이 통과한다.
- 사용자 시각 확인 승인.
- README 의 "낮춰 출력하는 요소" 에서 표·이미지·각주가 빠지고, hwpx 표 모양 규칙(§4.4, 사용자 그릇에서도 표 설정 적용)과 이미지 형식 제한(B-11 결과)이 반영된다.

## 10. 구현자에게 맡기는 것

- 모듈 나누기와 클래스 구조 (§3.4).
- 이미지를 파일로 둘지 메모리로 들고 있을지 (§5.1).
- `width: auto` 의 최소 열 폭 같은 세부 수치를 견본 결과에 맞춰 조정하는 것 (§4.2).
- 견본 결과가 이 문서와 다르면 해당 절을 고치는 것. 다만 §1 의 범위·반목표를 바꾸는 변경이면 사용자에게 먼저 묻는다.

## 부록 B. 견본 채취 결과 (2026-10-20, 한글 2020 11.0.0.4011)

스크립트: `spikes/m2b_samples/` (`capture.py` 한글 동작으로 저장, `author.py`·`author2.py`·`author3.py` 손으로 쓴 변형, `judge.py` 한글로 열고 PDF·재저장, `show.py` XML 요약). 손으로 쓴 변형은 내장 그릇 위에 `linesegarray` 없이 썼고, 모두 한글에서 오류·복구 안내 없이 열렸다 (`Open → True`). PDF 를 그림으로 바꿔 눈으로 확인했다.

### B-1 표

```xml
<hp:run charPrIDRef="…"><hp:tbl id="N" zOrder="N" numberingType="TABLE" textWrap="TOP_AND_BOTTOM"
    textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="1"
    rowCnt="R" colCnt="C" cellSpacing="0" borderFillIDRef="<테두리 없는 fill>" noAdjust="0">
  <hp:sz width="<표 폭>" widthRelTo="ABSOLUTE" height="<행 최소 높이 합>" heightRelTo="ABSOLUTE" protect="0"/>
  <hp:pos treatAsChar="0" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0"
      vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>
  <hp:outMargin left="0" right="0" top="283" bottom="283 + 다음 문단 앞 간격"/>
  <hp:caption …/>                       <!-- 있을 때만, inMargin 앞 (B-8) -->
  <hp:inMargin left="P" right="P" top="P" bottom="P"/>
  <hp:tr>
    <hp:tc name="" header="0|1" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="…">
      <hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP|CENTER|BOTTOM"
          linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">
        <hp:p …>…</hp:p>
      </hp:subList>
      <hp:cellAddr colAddr="c" rowAddr="r"/><hp:cellSpan colSpan="1" rowSpan="1"/>
      <hp:cellSz width="…" height="…"/><hp:cellMargin left="P" right="P" top="P" bottom="P"/>
    </hp:tc>
  </hp:tr>
</hp:tbl><hp:t/></hp:run>
```

- 표는 문단의 run 안에 들어가고 뒤에 빈 `<hp:t/>` 가 온다 (그림도 같다).
- 한글이 COM 으로 만든 표는 `treatAsChar="0"`, `outMargin` 283 이다. 사용자 예시 문서처럼 `treatAsChar="1"` 로 써도 본문 폭에 맞게 그려지지만, **쪽을 넘기는 표가 나뉘지 않는다** (B-5 정정). 구현은 `treatAsChar="0"`, `horzRelTo="PARA"` (목록 들여쓰기를 따름), `outMargin` 위·아래 283 을 쓴다. `outMargin` 아래가 0 이면 다음 문단이 표 아래쪽에 겹친다.
- `id`·`zOrder`·`instId` 를 모두 0 으로 써도 열렸다. 구현은 문서 안에서 겹치지 않는 번호를 쓴다.

### B-2 병합

가려진 자리는 `hp:tc` 를 쓰지 않는다. 병합 칸의 `cellSz width` 는 덮은 열의 합이다. 3×3 표에서 (0,0) rowSpan 2, (1,0) colSpan 2 → 칸 7개로 열렸다.

### B-3 칸 높이

`cellSz height="100"` (내용보다 훨씬 작음)으로 써도 한글이 행 높이를 내용에 맞춰 늘려 그린다. 재저장하면 칸 `height` 는 100 그대로, 표 `sz height` 만 새로 계산된다.

### B-4 테두리 굵기

한글이 그대로 받는 굵기 (문자열 그대로): `0.1 mm`, `0.12 mm`, `0.15 mm`, `0.2 mm`, `0.25 mm`, `0.3 mm`, `0.4 mm`, `0.5 mm`, `0.6 mm`, `0.7 mm`, `1.0 mm`, `1.5 mm`, `2.0 mm`, `3.0 mm`, `4.0 mm`, `5.0 mm`. 목록 밖의 값은 다르게 읽힌다 (`0.18 mm` → 0.15, `0.35 mm` → 0.25, `1 mm` 도 목록 값이 아니다). 칸마다 변별로 다른 굵기를 준 `borderFill` (바깥 0.4, 안쪽 0.12)이 그대로 그려진다.

```xml
<hh:borderFill id="…" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">
  <hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
  <hh:leftBorder type="SOLID" width="0.4 mm" color="#000000"/> … right, top, bottom …
  <hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>
  <hc:fillBrush><hc:winBrush faceColor="#F2F2F2" hatchColor="#999999" alpha="0"/></hc:fillBrush>  <!-- 배경 있을 때만 -->
</hh:borderFill>
```

### B-5 머리행·쪽 넘김

`header="1"` 칸 + `repeatHeader="1"` + `pageBreak="CELL"` + **`treatAsChar="0"`**: 표가 쪽을 넘겨 나뉘고 다음 쪽 맨 위에 머리행이 다시 나온다. 머리행 배경은 칸 `borderFill` 의 `fillBrush`.

**정정 (2026-10-20 구현 중):** 처음 견본에서는 `treatAsChar="1"` 인 80행 표가 "2쪽으로 나뉘었다"고 적었으나 잘못 읽은 것이었다. 실제로는 표 전체가 2쪽으로 밀리고 쪽 아래에서 잘렸다 (나머지 행이 그려지지 않음). 같은 문서에서 `treatAsChar="0"` 만 바꾸면 마지막 행까지 그려진다. `tests/test_hangul.py::test_long_table_splits_across_pages` 가 한글 PDF 의 마지막 쪽에 마지막 행이 있는지 본다.

### B-6 칸 안쪽 여백

표 `inMargin` 네 변을 P 로, 칸 `cellMargin` 도 P, `hasMargin="0"` 으로 쓰면 여백이 적용된다 (한 줄 표의 높이: P=141 → 1282, 425 → 1850, 850 → 2700, 늘어난 양 = 2×(P−141)). 1mm = 283.46 HWPUNIT.

### B-7 세로 정렬

`subList vertAlign="CENTER"` 인 칸의 글자가 행 가운데에 온다 (여러 줄 칸 옆의 한 줄 칸에서 확인).

### B-8 캡션

```xml
<hp:caption side="TOP|BOTTOM" fullSz="0" width="8504" gap="850" lastWidth="<개체 폭>">
  <hp:subList … vertAlign="TOP" …><hp:p paraPrIDRef="<캡션>" styleIDRef="<캡션>" …>…</hp:p></hp:subList>
</hp:caption>
```

한글은 캡션 문단에 `autoNum`(`numType="TABLE"|"PICTURE"`)을 넣지만, 빼고 글자만 넣어도 표 위·아래와 그림 아래에 그려진다. 표에서는 `outMargin` 다음·`inMargin` 앞, 그림에서는 `outMargin` 다음·`shapeComment` 앞에 둔다.

**추가 (2026-10-20 시각 확인 중):** 위·아래 캡션의 상자 폭은 **개체 폭과 같다**. `lastWidth`·`width`·`fullSz="1"` 을 본문 폭으로 바꿔도 넓어지지 않았다. 8mm 그림의 캡션은 `[그림 / 1] 샘 / 플 / 그림` 처럼 네 줄로 쪼개졌고, kitchen-sink 의 1×1 그림(0.26mm)은 캡션이 아예 그려지지 않은 채 높이만 차지해 뒤 문단을 다음 쪽으로 밀었다. 그래서 캡션의 가장 긴 문단이 개체 폭 안에 한 줄로 들어가지 않으면 (`text_em` × 캡션 글자 크기 × 1.15 > 개체 폭), 한글 캡션 대신 개체 앞·뒤에 캡션 모양의 문단으로 쓴다. 그림과 `width: auto` 표 모두에 적용한다. docx·pdf 의 캡션은 본문 폭 문단이므로 이렇게 쓴 결과가 오히려 그쪽과 같아 보인다.

### B-9 그림

```xml
<hp:pic id="N" zOrder="N" numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0"
    dropcapstyle="None" href="" groupLevel="0" instid="N" reverse="0">
  <hp:offset x="0" y="0"/><hp:orgSz width="OW" height="OH"/><hp:curSz width="W" height="H"/>
  <hp:flip horizontal="0" vertical="0"/>
  <hp:rotationInfo angle="0" centerX="W/2" centerY="H/2" rotateimage="1"/>
  <hp:renderingInfo><hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>
    <hc:scaMatrix e1="W/OW" e2="0" e3="0" e4="0" e5="H/OH" e6="0"/>
    <hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/></hp:renderingInfo>
  <hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="OW" y="0"/><hc:pt2 x="OW" y="OH"/><hc:pt3 x="0" y="OH"/></hp:imgRect>
  <hp:imgClip left="0" right="DW" top="0" bottom="DH"/><hp:inMargin left="0" right="0" top="0" bottom="0"/>
  <hp:imgDim dimwidth="DW" dimheight="DH"/>
  <hc:img binaryItemIDRef="<manifest id>" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/><hp:effects/>
  <hp:sz width="W" widthRelTo="ABSOLUTE" height="H" heightRelTo="ABSOLUTE" protect="0"/>
  <hp:pos treatAsChar="1" … vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" …/>
  <hp:outMargin left="0" right="0" top="0" bottom="0"/>
  <hp:caption …/>   <!-- 있을 때만 -->
  <hp:shapeComment>대체 문구</hp:shapeComment>
</hp:pic>
```

- 한글이 넣은 그림의 값 (400×200px): 비트맵은 `orgSz` = px × 93.75, `imgDim` = px × 75. SVG 는 `orgSz` = px × 75, `imgDim` = px × 60. 한글은 DPI 를 무시한다 (96·300dpi·DPI 없음 모두 같은 값).
- W·H(표시 크기)는 mdcast 가 정하고 `curSz`·`sz` 에 같이 쓴다. 이 공식으로 쓴 원래 크기·절반 크기·칸 안 그림이 모두 바르게 그려졌다.
- 그림 파일: `BinData/<이름>` (deflate), `content.hpf` manifest 에 `<opf:item id="<이름에서 확장자 뺀 것>" href="BinData/<이름>" media-type="…" isEmbeded="1"/>`. `header.xml` 에는 아무것도 더하지 않는다. `mdcast1.png` 같은 이름도 열렸다.
- media-type: `image/png`, `image/jpg` (jpeg 아님), `image/gif`, `image/bmp`, `image/svg`.

### B-10 칸 안 그림

2×2 표의 윗줄 칸에 그림(칸 안쪽 폭에 맞춤), 아랫줄에 설명 — 예시 문서와 같은 배치가 그려졌다.

### B-11 형식

`InsertPicture` 결과: PNG·JPEG·GIF·BMP·SVG 는 들어가고 **WebP 는 실패**한다.

### B-12 각주

```xml
<hp:run …><hp:t>본문</hp:t><hp:ctrl><hp:footNote number="n" suffixChar="41" instId="N">
  <hp:subList … vertAlign="TOP" …>
    <hp:p paraPrIDRef="<각주>" styleIDRef="<각주>" …><hp:run charPrIDRef="<각주>">
      <hp:ctrl><hp:autoNum num="n" numType="FOOTNOTE"><hp:autoNumFormat type="DIGIT" userChar=""
          prefixChar="" suffixChar=")" supscript="0"/></hp:autoNum></hp:ctrl><hp:t> 내용</hp:t>
    </hp:run></hp:p>
    <hp:p …>둘째 문단</hp:p>
  </hp:subList>
</hp:footNote></hp:ctrl><hp:t>뒤 글자</hp:t></hp:run>
```

- 번호 모양(`autoNumFormat`)은 그릇 `secPr/footNotePr/autoNumFormat` 과 같다 (내장 그릇: DIGIT, 뒤 `)`).
- 칸 안 각주, 각주 안 표: 한글이 만들고 다시 연다. 손으로 쓴 본문·칸 안 각주도 열리고 쪽 아래에 `1)`, `2)`, `3)` 으로 그려졌다.
- 각주 안 각주: 한글이 `InsertFootnote` 를 거부한다 (§6 의 낮춰 쓰기 대상).

### B-13 중첩 표

칸 안 문단의 run 에 `hp:tbl` 을 그대로 넣는다. 한글이 만들고 다시 연다.

### B-14 같은 그림 두 번

한글은 같은 파일을 두 번 넣으면 BinData 하나를 두 `hp:pic` 이 참조하게 저장한다. 손으로 쓴 같은 구조도 열렸다.
