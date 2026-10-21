from __future__ import annotations

import io
import zipfile

import pytest
from hwpx_builder import hwpx_bytes, p, run

from mdcast.readers.hwpx.package import CharStyle, HwpxError, ParaStyle, open_hwpx


def _replace(data: bytes, name: str, blob: bytes) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            target.writestr(info, blob if info.filename == name else source.read(info.filename))
    return out.getvalue()


def test_open_reads_spine_order_styles_and_meta():
    data = hwpx_bytes(
        p(run("첫")),
        p(run("둘")),
        title="제목",
        meta={"mdcast.generator": "mdcast 0.1", "creator": "홍"},
    )
    pkg = open_hwpx(data)
    assert len(pkg.sections) == 2 and pkg.title == "제목" and pkg.creator == "홍"
    assert pkg.generator == {"mdcast.generator": "mdcast 0.1"}
    assert pkg.styles.chars["1"].bold and pkg.styles.paras["3"] == ParaStyle("NUMBER", 0, "1")
    assert pkg.styles.numbering_start["2"] == 3


def test_sections_follow_spine_order_not_manifest_order():
    data = hwpx_bytes(p(run("첫")), p(run("둘")))
    content = zipfile.ZipFile(io.BytesIO(data)).read("Contents/content.hpf").decode()
    forward = '<opf:itemref idref="section0"/><opf:itemref idref="section1"/>'
    assert forward in content
    swapped = content.replace(
        forward, '<opf:itemref idref="section1"/><opf:itemref idref="section0"/>'
    )
    pkg = open_hwpx(_replace(data, "Contents/content.hpf", swapped.encode()))
    assert ["".join(section.itertext()) for section in pkg.sections] == ["둘", "첫"]


def test_fixed_header_ids_map_to_styles():
    styles = open_hwpx(hwpx_bytes(p(run("a")))).styles
    assert styles.chars == {
        "0": CharStyle(),
        "1": CharStyle(bold=True),
        "2": CharStyle(italic=True),
        "3": CharStyle(superscript=True),
        "4": CharStyle(subscript=True),
        "5": CharStyle(strike=True),
    }
    assert styles.paras == {
        "0": ParaStyle(),
        "1": ParaStyle("OUTLINE", 0),
        "2": ParaStyle("OUTLINE", 1),
        "3": ParaStyle("NUMBER", 0, "1"),
        "4": ParaStyle("NUMBER", 1, "1"),
        "5": ParaStyle("BULLET", 0, "1"),
        "6": ParaStyle("NUMBER", 0, "2"),
    }
    assert styles.numbering_start == {"1": 1, "2": 3}


def test_empty_meta_values_are_absent():
    pkg = open_hwpx(hwpx_bytes(p(run("a")), meta={"mdcast.generator": "", "mdcast.template": "t"}))
    assert pkg.title is None and pkg.creator is None
    assert pkg.generator == {"mdcast.template": "t"}


def test_bin_data_keyed_by_manifest_id():
    pkg = open_hwpx(hwpx_bytes(p(run("a")), bin_data={"image1.png": b"PNGDATA"}))
    assert pkg.bin_data == {"image1": ("image1.png", b"PNGDATA")}


def test_not_a_zip_is_hwpx_error():
    with pytest.raises(HwpxError):
        open_hwpx(b"x")


def test_missing_content_hpf_is_hwpx_error():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        target.writestr("mimetype", "application/hwp+zip")
    with pytest.raises(HwpxError):
        open_hwpx(out.getvalue())


def test_encrypted_package_is_hwpx_error_naming_security():
    with pytest.raises(HwpxError, match="암호|보안"):
        open_hwpx(hwpx_bytes(p(run("a")), encrypted=True))


def test_unreadable_section_is_hwpx_error_naming_security():
    data = _replace(hwpx_bytes(p(run("a"))), "Contents/section0.xml", b"\x93\x11\xfe garbled")
    with pytest.raises(HwpxError, match="암호|보안"):
        open_hwpx(data)
