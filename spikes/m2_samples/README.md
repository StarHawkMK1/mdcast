# M2a hwpx 견본 채취 (버리는 코드)

Windows + 한글 + pywin32 가 필요하다. 실행마다 한글의 "접근 허용" 대화상자가 뜰 수 있다.

    uv run python spikes/m2_samples/capture.py <out>                       # 한글 동작으로 견본 저장
    uv run python spikes/m2_samples/author.py <out>/pagebreak.hwpx <dir>   # 손으로 만든 변형 (author2–4 도 같은 인자)
    uv run python spikes/m2_samples/judge.py <dir> <파일.hwpx> ...         # 한글로 열기, PDF·재저장
    uv run python spikes/m2_samples/show.py <파일.hwpx>                    # section0.xml 요약

`author2.py`–`author4.py` 는 `author.py`(또는 그 앞 번호)를 읽어 함수들을 재사용한다.
