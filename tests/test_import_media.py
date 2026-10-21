from __future__ import annotations

import sys

import pytest
from helpers import tiny_bmp, tiny_png, tiny_wmf

from mdcast.readers.media import Assets, to_png
from mdcast.report import Codes, Report
from mdcast.types import Format


@pytest.mark.skipif(sys.platform != "win32", reason="Pillow renders WMF only on Windows")
def test_wmf_becomes_png():
    png, name = to_png(tiny_wmf(), "image3.wmf")
    assert name == "image3.png" and png.startswith(b"\x89PNG")


def test_png_passes_through_and_unknown_fails():
    assert to_png(tiny_png(), "a.png") == (tiny_png(), "a.png")
    assert to_png(b"garbage", "a.emf") is None


def _assets() -> tuple[Assets, Report]:
    report = Report("a.hwpx", Format.HWPX)
    return Assets("a b_assets", report), report


def test_assets_add_names_inside_the_folder():
    assets, _ = _assets()
    b = chr(92)
    assert assets.add(f"..{b}..{b}evil.png", tiny_png()) == "a b_assets/evil.png"
    assert assets.add('a:b*c?d"e<f>g|h.png', b"2") == "a b_assets/a_b_c_d_e_f_g_h.png"
    assert assets.add("..", b"3") == "a b_assets/image3.png"
    assert assets.media == {"evil.png": tiny_png(), "a_b_c_d_e_f_g_h.png": b"2", "image3.png": b"3"}


def test_assets_add_tells_clashing_names_apart_and_repeats_paths():
    assets, _ = _assets()
    first = assets.add("media/image1.png", tiny_png())
    assert assets.add("media/image1.png", tiny_png()) == first == "a b_assets/image1.png"
    assert assets.add("other/image1.png", b"different") == "a b_assets/image1-2.png"
    assert assets.add("image1.png", tiny_png()) == first  # same name, same bytes: one file
    assert list(assets.media) == ["image1.png", "image1-2.png"]


def test_assets_add_converts_to_png_or_warns():
    assets, report = _assets()
    assert assets.add("pic.bmp", tiny_bmp()) == "a b_assets/pic.png"
    assert assets.media["pic.png"].startswith(b"\x89PNG")
    assert assets.add("bad.bmp", b"garbage") == "a b_assets/bad.bmp"
    warns = [e for e in report.events if e.code == Codes.IMAGE_CONVERT_FAILED]
    assert [(e.message, e.where) for e in warns] == [
        ("그림 형식을 PNG로 바꾸지 못해 원본 그대로 가져옵니다", {"name": "bad.bmp"})
    ]
