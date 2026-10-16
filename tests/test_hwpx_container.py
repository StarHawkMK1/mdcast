import importlib.util
import io
import zipfile
from pathlib import Path

import pytest
from helpers import HWPX_NS, builtin_hwpx, hwpx_integrity

from mdcast.hwpx.container import ContainerError, Package
from mdcast.hwpx.units import hwpunit, hwpunit_pt, para_unit, para_unit_pt
from mdcast.report import Report
from mdcast.templates import resolve_template
from mdcast.types import Format

ROOT = Path(__file__).resolve().parents[1]
OPF_META = f"{{{HWPX_NS['opf']}}}meta"


def test_units_follow_hangul_measurements():
    assert hwpunit(15.0) == 4252  # page margins: plain HWPUNIT (appendix A-9)
    assert hwpunit_pt(10) == 1000
    assert para_unit(5.0) == 2834  # paragraph margins and tab positions: twice (A-4, A-12)
    assert para_unit_pt(10) == 2000


def test_doubled_units_are_even():
    # Hangul reads an odd value as another unit: a 3321 footer gap pushed it off the page
    assert all(para_unit(n / 7) % 2 == 0 for n in range(200))
    assert all(para_unit_pt(n / 7) % 2 == 0 for n in range(200))


def test_builtin_container_is_sound_and_anonymous():
    parts = hwpx_integrity(builtin_hwpx())
    values = {m.get("name"): (m.text or "") for m in parts["Contents/content.hpf"].iter(OPF_META)}
    assert values.get("creator", "") == ""
    assert values.get("CreatedDate", "") == ""


def test_builtin_container_path(tmp_path):
    tpl = resolve_template(None, cwd=tmp_path, home=tmp_path, report=Report("d.md", Format.MD))
    path = tpl.builtin_container("hwpx").path
    assert path.name == "reference.hwpx" and path.is_file()


def test_round_trip_keeps_entries():
    package = Package.read(builtin_hwpx())
    out = Package.read(package.write())
    assert out.names()[0] == "mimetype"
    assert sorted(out.names()) == sorted(package.names())
    hwpx_integrity(package.write())


def test_mimetype_is_written_first_and_stored():
    package = Package.read(builtin_hwpx())
    data = package.get("mimetype")
    package.remove("mimetype")
    package.set("mimetype", data)
    assert package.names()[-1] == "mimetype"
    first = zipfile.ZipFile(io.BytesIO(package.write())).infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED


@pytest.mark.parametrize("data", [b"not a zip", b""])
def test_unreadable_container(data):
    with pytest.raises(ContainerError):
        Package.read(data)


def test_container_missing_section():
    package = Package.read(builtin_hwpx())
    package.remove("Contents/section0.xml")
    with pytest.raises(ContainerError, match="section0"):
        Package.read(package.write())


def test_container_with_broken_xml():
    package = Package.read(builtin_hwpx())
    package.set("Contents/header.xml", b"<hh:head")
    with pytest.raises(ContainerError):
        Package.read(package.write())


def test_xml_with_doctype_is_rejected():
    package = Package.read(builtin_hwpx())
    package.set("Contents/header.xml", b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>')
    with pytest.raises(ContainerError):
        Package.read(package.write())


def test_reference_script_clears_personal_metadata():
    spec = importlib.util.spec_from_file_location("make_ref", ROOT / "scripts" / "make_reference_hwpx.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    package = Package.read(builtin_hwpx())
    content = package.xml("Contents/content.hpf")
    for meta in content.iter(OPF_META):
        if meta.get("name") in ("creator", "CreatedDate"):
            meta.text = "someone"
    package.set_xml("Contents/content.hpf", content)
    cleaned = Package.read(module.normalize(package.write())).xml("Contents/content.hpf")
    assert all(not (m.text or "") for m in cleaned.iter(OPF_META) if m.get("name") in ("creator", "CreatedDate"))
