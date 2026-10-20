from __future__ import annotations

import sys

import pytest

from helpers import tiny_png, tiny_wmf
from mdcast.readers.media import to_png


@pytest.mark.skipif(sys.platform != "win32", reason="Pillow renders WMF only on Windows")
def test_wmf_becomes_png():
    png, name = to_png(tiny_wmf(), "image3.wmf")
    assert name == "image3.png" and png.startswith(b"\x89PNG")


def test_png_passes_through_and_unknown_fails():
    assert to_png(tiny_png(), "a.png") == (tiny_png(), "a.png")
    assert to_png(b"garbage", "a.emf") is None
