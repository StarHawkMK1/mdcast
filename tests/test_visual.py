import os
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageChops

from mdcast import pipeline
from mdcast.types import Format, Options, Source

FIXTURE = Path(__file__).parent / "fixtures" / "md" / "korean-report.md"
GOLDEN = Path(__file__).parent / "golden" / "pdf" / "korean-report-p1.png"
DIFF_DIR = Path(".test-output") / "visual"
TOLERANCE = 0.005  # share of pixels allowed to differ


@pytest.mark.visual
def test_korean_report_first_page_matches_golden(tmp_path):
    source = Source(FIXTURE.read_bytes(), FIXTURE.name, Format.MD, base_dir=FIXTURE.parent)
    result = pipeline.convert(source, [Format.PDF], options=Options(offline=True, cwd=tmp_path, home=tmp_path / "home"))
    image = pdfium.PdfDocument(result.outputs[0].data)[0].render(scale=1.0).to_pil().convert("RGB")
    if os.environ.get("MDCAST_UPDATE_GOLDEN") == "1" or not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        image.save(GOLDEN)
        pytest.skip(f"golden written to {GOLDEN} — review it and commit")
    golden = Image.open(GOLDEN).convert("RGB")
    assert golden.size == image.size
    diff = ImageChops.difference(golden, image).convert("L").point(lambda v: 255 if v > 32 else 0)
    changed = sum(1 for v in diff.getdata() if v) / (image.size[0] * image.size[1])
    if changed > TOLERANCE:
        DIFF_DIR.mkdir(parents=True, exist_ok=True)
        image.save(DIFF_DIR / "actual.png")
        diff.save(DIFF_DIR / "diff.png")
    assert changed <= TOLERANCE, f"{changed:.2%} of pixels differ — see {DIFF_DIR}"
