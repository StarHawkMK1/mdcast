# mdcast

Markdown ↔ docx · hwpx · pdf, 템플릿 기반 변환기. (M1: MD → docx, pdf · M2: MD → hwpx)

## 설치 (개발)

    uv sync

## 사용

    uv run mdcast convert 보고서.md --to docx,hwpx,pdf
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
    uv run python -m pytest tests/test_hangul.py --run-hangul   # 한글로 열기·줄 간격·위치 비교 (Windows + 한글, 선택)
    uv run python scripts/render_pages.py out.hwpx   # 한글 → PDF → PNG

## 템플릿: 줄 높이

`line_height: 160%` 는 그 요소의 줄 하나가 글자 크기의 1.6배 높이를 차지한다는 뜻입니다(한글의 "글자에 따라 160%" 와 같음). 문단 앞뒤 간격은 그 바깥에 더합니다.

- `elements.<요소>.line_height`: 제목·본문·인용·코드·캡션·각주. 내장 템플릿은 모두 값을 가집니다(본문·인용 180%, 코드 160%, 나머지 130%).
- `tables.line_height`: 표 셀 안 줄 높이(기본 130%, 글자 크기는 `tables.font_size`). 표 종류(`tables.variants.<이름>`)에서 덮어쓸 수 있습니다.
- docx 는 Word 의 "고정" 줄 간격으로 씁니다. 줄보다 큰 이미지나 쌓인 수식(분수 등)이 든 문단만 "최소" 로 두어 잘리지 않게 합니다. 사용자 reference.docx 의 "고정" 줄 간격도 그런 문단에서는 "최소" 로 바뀝니다.
- 사용자 reference.docx 를 쓰면 yaml 에 적은 줄 높이만 적용하고, 적지 않은 요소는 그 문서의 설정을 따릅니다. 이때 PDF 는 상속받은 값(내장 기본값)을 쓰므로, 두 형식을 맞추려면 값을 적어 주세요.
- 사용자 `pdf.typ` 는 `cfg.elements.<요소>.line_height`, `cfg.tables.<이름>.line_height` (비율, 1.6 = 160%)를 읽습니다. 예전의 `leading` 키는 없어졌습니다.

## hwpx 출력

- 내장 그릇은 한글 빈 문서입니다. 템플릿에 `reference.hwpx` 를 두면 그 문서의 스타일·쪽 설정을 쓰고 yaml 에 적은 값만 덮어씁니다.
- 스타일 매핑은 `styles.<요소>.hwpx` (기본: 제목 → "개요 N", 본문·인용·코드 → "바탕글", 캡션 → "캡션", 각주 → "각주"). 한글 개요 번호는 끄고 mdcast 번호 설정을 씁니다.
- 개조식 목록 기호는 글자로 들어갑니다 (한글에서 항목을 끼워 넣어도 번호가 자동으로 바뀌지 않음).
- 표는 한글 표로 만듭니다: 병합 칸(grid table), 머리행(쪽을 넘기면 반복), 안쪽·바깥 테두리, 머리행·첫 열 배경, 줄무늬, 칸 정렬, 표 종류(`<!-- table: 이름 -->`), 캡션(한글 캡션, 번호는 mdcast 형식). 모양은 템플릿 `tables` 설정을 따르고, **사용자 `reference.hwpx` 를 써도 표 설정이 모두 적용됩니다** (hwpx 에는 그릇이 가진 표 스타일이 없음. docx 는 그릇의 표 스타일이 이깁니다). 테두리 굵기는 한글 굵기 목록에서 가장 가까운 값을 씁니다 (0.5pt → 0.2mm, 1pt → 0.4mm).
- 제출 양식처럼 가는 테두리·회색 머리행 표는 표 종류로 만듭니다. 예: `tests/fixtures/templates/submission/template.yaml` 의 `제출양식`.
- 이미지는 문서 안에 넣습니다. PNG·JPEG·GIF·BMP·SVG 는 그대로, WebP 는 PNG 로 바꿔 넣습니다. 크기는 이미지의 DPI(없으면 96) 기준이고 `{width=50%}`·`{width=60mm}` 속성을 따르며, `figures.max_width` 와 그 자리의 폭(목록·인용 들여쓰기, 표 칸)을 넘지 않습니다. 그림 캡션은 한글 캡션으로 붙습니다.
- 각주는 한글 각주입니다 (번호는 한글이 매김). 한글은 각주 안에 각주를 넣을 수 없어, 각주 안·캡션 안의 각주만 본문에 `[주 n]`, 문서 끝에 내용으로 모아 씁니다.
- 낮춰 출력하는 요소: 수식은 LaTeX 원문(M4 에서 이미지), 위의 `[주 n]` 각주.
- 알려진 차이: 한글은 줄의 남는 높이를 글자 아래에 둡니다. 줄 간격은 같지만 본문 줄이 PDF 보다 약 1.4mm 위에 놓입니다.

## 개발: 한글 COM 보안 모듈 (선택)

한글 자동화(테스트, 렌더 스크립트)는 파일에 접근할 때마다 "접근 허용" 을 묻습니다. 무인으로 돌리려면 한컴 개발자 사이트(developer.hancom.com)의 보안 모듈 `FilePathCheckerModuleExample.dll` 을 받아 두고, 레지스트리 `HKEY_CURRENT_USER\Software\HNC\HwpAutomation\Modules` 에 문자열 값 `FilePathCheckerModule` = DLL 전체 경로(따옴표 없이)를 넣습니다. mdcast 사용자에게는 필요 없습니다.

## M1 에서 미룬 항목

- 머리말/꼬리말 `logo`, PDF 셀 세로 정렬, docx 캡션 위치(pandoc 기본), 표 셀 안의 중첩 표
- `figures.max_width` / `figures.align` 은 검증만 하고 writer 에 아직 적용하지 않음
- typst 컴파일 타임아웃 없음 (spec §5.5 의 60 초 제한은 M4 로 이월)
- 코어가 로컬 이미지를 `base_dir`/cwd 기준으로 읽음 (로컬 모드 전용, 원격 모드 하드닝은 이월)

## M2a 에서 미룬 항목

- 표·이미지·각주 (M2b), 한글 고유 번호 목록, 문서 안 링크 책갈피, 다른 한글 버전 그릇 시험
