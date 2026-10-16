# line_height 의미 통일 설계 (2026-10-16)

상위 스펙: `2026-10-15-mdcast-design.md` (§0.4 같은 모양, §3 템플릿). 이 문서는 템플릿 키 `line_height` 의 뜻을 하나로 정하고, docx·pdf writer 가 그 뜻을 똑같이 구현하도록 바꾼다.

## 1. 배경

같은 `template.yaml` 로 만든 docx 와 pdf 의 줄 간격이 크게 다르다. 2026-10-16 측정(Word 로 docx 를 PDF 로 내보낸 뒤 글자 위치 측정, 본문 11pt·160%):

| | Word (docx) | Typst (pdf) |
|---|---|---|
| 본문 줄 피치 | 30.5pt (글자 크기의 2.77배) | 18pt (1.64배) |

원인:
- docx writer 는 `line_height` 를 Word 의 "배수" 줄 간격으로 쓴다. Word 는 배수를 **글꼴 고유의 1줄 높이**에 곱하는데, 맑은 고딕의 Word 1줄은 글자 크기의 약 1.73배다.
- pdf writer 는 `_leading()` 으로 "1줄 = 1.2em" 을 가정해 근사한다. 160% 에서는 우연히 1.64배가 되지만 100% 에서는 0.92배가 된다.
- 목록(Compact 스타일이 본문 줄 간격을 상속)과 표 행 높이의 차이도 같은 원인이다.

한글(hwp)의 줄 간격 "글자에 따라 160%" 는 줄 피치가 글자 크기의 1.6배다. M2 의 hwpx 까지 생각하면 이 정의로 맞추는 것이 자연스럽다.

## 2. 정의

`line_height: N%` 는 **그 요소의 줄 하나가 차지하는 높이(줄 피치)가 글자 크기 × N/100** 이라는 뜻이다.

- 한 줄짜리 문단도 그 높이를 차지한다. 문단 높이 = 줄 수 × 글자 크기 × N/100.
- `space_before`·`space_after` 는 그 바깥에 더한다.
- 글자 크기는 그 요소의 `size` 다. 없으면 `elements.body.size` 를 쓴다.
- docx·pdf 가 이 정의를 따르고, M2 의 hwpx 는 문단 모양 줄 간격(글자에 따라, N%)으로 같은 뜻을 낸다.

## 3. 새 키

- `tables.line_height` (비율, 기본 `130%`): 표 셀 안 문단의 줄 높이. 글자 크기는 `tables.font_size`. 표 종류(`tables.variants.<이름>`)에서 덮어쓸 수 있다. 스키마의 비율 키 처리(`RATIO_KEYS`)를 그대로 쓴다.

## 4. 내장 default 템플릿 값

내장 템플릿은 모든 요소에 값을 명시해, 내장 템플릿 결과가 두 형식에서 같도록 한다.

| 요소 | line_height |
|---|---|
| heading1–6, code, caption, footnote | 130% |
| body, quote | 160% (body 는 지금과 같음) |
| tables.line_height | 130% |

## 5. docx

적용 범위는 기존 원칙을 따른다. 내장 그릇이면 위 값을 모두 적용하고, 사용자 reference.docx 면 yaml 에 명시한 값만 적용한다(`ResolvedTemplate.explicit`).

1. **스타일:** `line_height` 가 있는 요소의 스타일에 `w:spacing w:line="round(N/100 × 글자 크기pt × 20)" w:lineRule="exact"` 를 쓴다. 글자 크기는 yaml 의 `size`, 없으면 그 스타일의 docx 상 실효 크기(상속 포함), 그것도 없으면 `elements.body.size` 다. 지금의 `fmt.line_spacing = 비율`(배수)을 대체한다.
2. **이미지·수식이 든 문단:** 문서 본문과 각주·미주의 문단 안에 `w:drawing`, `w:pict`, `w:object`, `m:oMath` 가 있으면 그 문단에 같은 값을 `lineRule="atLeast"` 로 직접 서식으로 준다. "고정" 에서는 큰 인라인 요소가 잘리기 때문이다. 이미지만 든 그림 문단도 여기에 해당한다.
3. **좁은 목록:** 내장 그릇에서 Compact 스타일의 앞뒤 간격을 0 으로 한다. 목록 항목의 줄 피치가 본문과 같아지고, PDF 의 좁은 목록(항목 사이 간격 없음)과 맞는다. Compact 는 지금처럼 글자 모양만 따로 받는(`CHARACTER_ONLY`) 스타일로 남고, 줄 높이는 기반 스타일(Body Text)의 "고정" 값을 상속한다.
4. **표 셀:** 내장 그릇에서 셀 안 문단에 `exact` 줄 높이(`tables.line_height` × `tables.font_size`)와 앞뒤 간격 0 을 직접 서식으로 준다. 5681cc8 의 "1줄(line=240 auto)" 을 이것으로 바꾼다. 셀 문단 안에 이미지·수식이 있으면 2 와 같이 `atLeast` 로 한다. 사용자 그릇이면 yaml 에 `tables.line_height` 가 명시되었을 때만 적용한다.

## 6. PDF

1. **줄 상자 모델:** 요소마다 `text(top-edge: (0.8 + h) em, bottom-edge: -(0.2 + h) em)` 와 `par(leading: 0em)` 을 쓴다. 여기서 h = (N/100 − 1) / 2 다. 줄 상자 높이가 정확히 N/100 em 이 되어, 줄 피치와 문단 높이가 정의와 같아진다. 2026-10-16 실험에서 11pt 기준 100%·130%·160% 모두 피치 11.0·14.4·17.6pt, 문단 높이 오차 0 으로 확인했다.
2. **적용 위치(내장 pdf.typ):** 문서 전체에 body, 제목은 수준별 show 규칙, 그리고 code 블록·quote·figure.caption·footnote.entry·`mdcast-table` 안에서 각 요소의 값을 쓴다. 좁은 목록의 항목 사이는 Typst 기본(`spacing: auto` 가 좁은 목록에 `par.leading` = 0 을 씀)으로 0 이 된다. 넓은 목록은 `par.spacing` 을 쓴다.
3. **설정 JSON:** `elements.<요소>.leading` 을 없애고 `elements.<요소>.line_height`(비율, 예: 1.6)를 넣는다. 표 설정에 `line_height` 를 넣는다. `_leading()` 은 지운다.
4. **사용자 pdf.typ 계약:** 사용자 pdf.typ 가 `leading` 을 읽고 있었다면 컴파일에 실패하고, 기존 규칙대로 내장 레이아웃으로 대체되며 `TEMPLATE_INVALID` 경고가 나간다(무거부 유지). README 의 pdf.typ 계약 설명을 새 키로 고친다.

## 7. 값이 비어 있을 때 (null)

- 내장 템플릿은 4절대로 모두 명시하므로 해당 없음.
- 사용자 템플릿에서 비어 있으면(상속받은 값도 없으면): docx 는 reference.docx 스타일 자체 설정을 그대로 두고, PDF 는 130% 를 쓴다. 두 형식을 맞추려면 값을 명시해야 한다. README 의 템플릿 설명에 이 점과 2절의 정의를 적는다.

## 8. 테스트

- **docx 단위:** 내장 그릇에서 Body Text·Heading 1·Table Caption 등의 `w:spacing` 이 `exact` 이고 값이 비율 × 크기 × 20 인지. 사용자 그릇에서 명시하지 않은 요소는 바뀌지 않는지. 이미지가 든 문단은 `atLeast` 인지. Compact 앞뒤 간격 0. 셀 문단 `exact` 와 `tables.line_height` 덮어쓰기(종류별).
- **PDF 측정:** pdfium 글자 위치로 본문·목록·표 셀의 줄 피치가 비율 × 크기와 같은지(±0.3pt). 기존 `_line_pitch` 도우미를 쓴다. 기존 `test_table_cells_are_single_spaced_while_body_is_wider` 는 이 테스트로 바꾼다.
- **Word 대조(선택 실행):** `--run-word` 옵션을 줄 때만 돈다. Word COM 으로 docx 를 PDF 로 내보내 본문·목록·표 셀의 줄 피치를 PDF writer 결과와 비교한다. 허용 오차 5%. 이번처럼 두 형식이 함께 어긋나는 것을 잡는 유일한 테스트다.
- **설정·스키마:** `tables.line_height` 기본값과 종류별 덮어쓰기, 잘못된 값이면 상위 값으로 대체(기존 sanitize 규칙).
- **시각 골든:** PDF 1쪽이 바뀌므로 다시 만들고 사용자가 승인한다.
- 전체 테스트, `ruff check`, `--run-visual`.

## 9. 범위 밖

- 번호 뒤 간격(두 자리 번호 자리를 남기는 의도된 동작).
- hwpx 구현(M2 에서 2절 정의로 구현).
- 한 줄 안에서 글자 기준선 위치의 미세한 차이(Word 와 Typst 가 줄 상자 안에 글자를 놓는 위치).
- 머리말·꼬리말 문단의 줄 높이.

## 10. 검토한 다른 방식

- **"최소" 줄 간격:** 맑은 고딕의 Word 1줄(1.73배)이 1.6배보다 커서 효과가 없다.
- **배수를 글꼴 정보로 보정:** docx 는 읽는 사람 PC 의 글꼴로 배치되므로, 변환 시점에 그 글꼴의 1줄 높이를 정확히 알 수 없다. 글꼴 파일을 읽을 의존성(fontTools)도 새로 필요하다.
