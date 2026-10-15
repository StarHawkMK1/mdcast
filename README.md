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

## M1 에서 미룬 항목

- 머리말/꼬리말 `logo`, PDF 셀 세로 정렬, docx 캡션 위치(pandoc 기본), 표 셀 안의 중첩 표
- `figures.max_width` / `figures.align` 은 검증만 하고 writer 에 아직 적용하지 않음
- typst 컴파일 타임아웃 없음 (spec §5.5 의 60 초 제한은 M4 로 이월)
- 코어가 로컬 이미지를 `base_dir`/cwd 기준으로 읽음 (로컬 모드 전용, 원격 모드 하드닝은 이월)
- hwpx 스파이크 S1 실행은 보류 중이며 M2 이전에 수행해야 함

설계: `docs/superpowers/specs/2026-10-15-mdcast-design.md`
