# M2b hwpx 견본 채취 (버리는 코드)

Windows + 한글 + pywin32 + Pillow(dev) 가 필요하다.

    uv run python spikes/m2b_samples/capture.py <out>                   # 한글 동작으로 견본 저장 (<out>/img 에 시험 그림)
    uv run python spikes/m2b_samples/author.py <out>/img <dir>          # 손으로 쓴 변형 (author2·author3 도 같은 인자)
    uv run python spikes/m2b_samples/judge.py <dir> <파일.hwpx> ...     # 한글로 열기, PDF·재저장
    uv run python spikes/m2b_samples/show.py <파일.hwpx>                # section0.xml·manifest 요약
