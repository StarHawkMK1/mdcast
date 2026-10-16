# mdcast

Markdown ↔ docx · hwpx · pdf, 템플릿 기반 변환기. (M1: MD → docx, pdf)

## 설치 (개발)

    uv sync

## 사용

    uv run mdcast convert 보고서.md --to docx,pdf
    uv run mdcast convert 보고서.md --to pdf --template company-report --verbose
    uv run mdcast template list
    uv run mdcast template describe default
    uv run mdcast template validate ./my-template

- 템플릿 탐색 순서: 경로 → `./.mdcast/templates/<이름>` → `~/.mdcast/templates/<이름>` → 내장 `default`
- 쪽 나눔: `<!-- pagebreak -->` 또는 템플릿 `layout.page_break.before`
- 표 종류: 표 바로 위에 `<!-- table: 이름 -->`
- 병합 셀 표: HTML `<table>` + `<thead>`/`<tbody>` + `rowspan`/`colspan`
- 이벤트 코드 `FRONTMATTER_INVALID`: YAML 머리말이 깨지면 경고하고 변환은 계속한다

## 테스트

    uv run pytest -q
    uv run pytest tests/test_visual.py --run-visual   # PDF 시각 골든 (이 PC 글꼴 기준, 선택)
    uv run python scripts/render_pages.py out.docx out.pdf   # PNG 는 .test-output/pages/ (docx 는 Windows + Word 필요)
    uv run pytest tests/test_word_parity.py --run-word   # Word 로 내보낸 docx 와 PDF 의 줄 간격 비교 (Windows + Word, 선택)

## 템플릿: 줄 높이

`line_height: 160%` 는 그 요소의 줄 하나가 글자 크기의 1.6배 높이를 차지한다는 뜻입니다(한글의 "글자에 따라 160%" 와 같음). 문단 앞뒤 간격은 그 바깥에 더합니다.

- `elements.<요소>.line_height`: 제목·본문·인용·코드·캡션·각주. 내장 템플릿은 모두 값을 가집니다(본문·인용 160%, 나머지 130%).
- `tables.line_height`: 표 셀 안 줄 높이(기본 130%, 글자 크기는 `tables.font_size`). 표 종류(`tables.variants.<이름>`)에서 덮어쓸 수 있습니다.
- docx 는 Word 의 "고정" 줄 간격으로 씁니다. 이미지나 수식이 든 문단만 "최소" 로 두어 잘리지 않게 합니다.
- 사용자 reference.docx 를 쓰면 yaml 에 적은 줄 높이만 적용하고, 적지 않은 요소는 그 문서의 설정을 따릅니다. 이때 PDF 는 상속받은 값(내장 기본값)을 쓰므로, 두 형식을 맞추려면 값을 적어 주세요.
- 사용자 `pdf.typ` 는 `cfg.elements.<요소>.line_height`, `cfg.tables.<이름>.line_height` (비율, 1.6 = 160%)를 읽습니다. 예전의 `leading` 키는 없어졌습니다.

## M1 에서 미룬 항목

- 머리말/꼬리말 `logo`, PDF 셀 세로 정렬, docx 캡션 위치(pandoc 기본), 표 셀 안의 중첩 표
- `figures.max_width` / `figures.align` 은 검증만 하고 writer 에 아직 적용하지 않음
- typst 컴파일 타임아웃 없음 (spec §5.5 의 60 초 제한은 M4 로 이월)
- 코어가 로컬 이미지를 `base_dir`/cwd 기준으로 읽음 (로컬 모드 전용, 원격 모드 하드닝은 이월)

설계: `docs/superpowers/specs/2026-10-15-mdcast-design.md`
