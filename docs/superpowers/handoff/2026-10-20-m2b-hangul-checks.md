# M2b — 한글로 확인할 일 (2026-10-20)

브랜치 `m2b-hwpx` 의 구현은 끝났고 한글 없이 도는 테스트는 모두 통과한다 (502 passed). 아래는 **한글을 열어야만** 확인할 수 있어 남은 일이다. 설계: `docs/superpowers/specs/2026-10-20-mdcast-m2b-hwpx-design.md` §8.3·§8.5·§9.

## 0. 먼저

- 한글 보안 모듈이 등록되어 있지 않아, 한글이 파일을 열 때마다 **"접근 허용" 대화상자**가 뜬다. 자동 테스트 중에 뜨면 **"모두 허용"** 을 누른다. 등록하면 뜨지 않는다 (README "개발: 한글 COM 보안 모듈").
- 작업 관리자에 창 없는 `Hwp.exe` (오전 10:31 시작, 견본 채취 때 남은 것으로 보임)가 있으면 닫아도 된다. 열어 둔 예시 문서 창은 상관없다.

## 1. 자동 확인 (약 1분)

```
uv run python -m pytest tests/test_hangul.py --run-hangul -q
```

기대: 9 passed. 이 가운데 새로 생긴 것:

| 테스트 | 확인하는 것 |
|---|---|
| `test_hangul_opens_fixture[tables-images]` | 표·그림·각주 시험 문서가 오류 없이 열리고 PDF 로 저장된다 |
| `test_tables_pictures_footnotes_open_as_objects` | 한글이 표 4·그림 5·각주 3 을 개체로 읽는다 |
| `test_long_table_splits_across_pages` | 80행 표가 쪽을 넘겨 나뉘고, 마지막 쪽에 마지막 행·머리행·뒤 문단이 있다 |

**마지막 수정(표를 글자처럼 취급하지 않게 바꾼 것, 표 아래 여백) 이후로는 한글에서 아직 한 번도 열어 보지 못했다.** 특히 중첩 표, 각주 안 표, 표 다음 제목 간격은 이 실행으로 처음 확인된다.

## 2. 눈으로 확인 (승인 필요)

```
uv run python -m pytest tests/test_e2e.py -q
uv run python scripts/render_pages.py .test-output/e2e/tables-images.hwpx .test-output/e2e/tables-images.docx .test-output/e2e/tables-images.pdf .test-output/e2e/kitchen-sink.hwpx
```

PNG 는 `.test-output/pages/` 아래에 생긴다. 또는 `.test-output/e2e/tables-images.hwpx` 를 한글에서 바로 연다.

`tables-images.hwpx` 에서 볼 것:

- [ ] 열 때 "손상"·"복구" 안내가 없다
- [ ] 1쪽 `<표 1> 성능 기준표`: 머리행 2줄, 왼쪽 두 칸은 세로 병합, `성능 기준` 은 가로 3칸 병합, 머리행 연회색
- [ ] `화면 예시`: 2×2 표의 윗줄 칸에 화면 그림이 칸 폭에 맞게, 아랫줄에 설명. `목록 화면` 옆 각주 `1)` 이 그 쪽 아래에 있다
- [ ] `제출양식` 표: 가는 테두리(0.12mm), 머리행 `#E5E5E5`
- [ ] 표 바로 뒤의 제목(`화면 예시`, `그림`)이 표에 붙지 않고 간격이 있다
- [ ] 본문 안 작은 그림(8mm)이 글자처럼 줄 안에 있다. 넓은 그림은 본문 폭으로 줄고 아래에 `[그림 1] …` 캡션
- [ ] `폭 40%` 그림이 가운데, 아래 `[그림 2] 폭 40%`
- [ ] 각주 `2)`·`3)` 이 쪽 아래에 있고 `3)` 안에 □ 목록
- [ ] `긴 표` 60행이 두 쪽에 걸쳐 나뉘고, 다음 쪽 맨 위에 머리행(`번호 항목 값`)이 다시 나온다. 마지막 행 `60` 이 보인다
- [ ] 같은 문서의 docx·pdf 와 나란히 놓았을 때 같은 템플릿으로 보인다 (아래 "알려진 문제" 제외)

`kitchen-sink.hwpx`: 표·그림·각주가 있는 기존 시험 문서 전체가 자연스러운지.

## 3. 확인 뒤 내가 할 일

- 결과(통과·승인 날짜)를 설계 문서 §9 아래에 한 줄로 적는다.
- 문제가 있으면 고치고 1·2 를 다시 한다.
- 브랜치 마무리 (main 병합 여부는 그때 묻는다).

## 알려진 문제 (이번 범위 밖)

- **PDF**: 병합 칸이 있는 grid table(`성능 기준표`)이 PDF 에서 빈 열이 생기고 좁게 그려진다. M1 PDF writer 문제로, hwpx·docx 와 무관하다. 별도 작업으로 다룬다.
