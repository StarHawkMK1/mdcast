import re
from pathlib import Path

import pytest
from helpers import HWPX_NS as NS
from helpers import builtin_hwpx, hwpx_integrity, hwpx_settings

from mdcast.ast import md_to_doc
from mdcast.hwpx import ContainerError, Metadata, Package, write

FIXTURES = Path(__file__).parent / "fixtures" / "md"
SRC = Path(__file__).resolve().parents[1] / "src" / "mdcast" / "hwpx"
OPF = f"{{{NS['opf']}}}"
META = Metadata(title="제목", author="작성자", keywords="mdcast", created="2026-10-16T00:00:00Z",
                extra=(("mdcast.generator", "mdcast 0.1"),))


@pytest.mark.parametrize("name", ["kitchen-sink", "edge-cases", "korean-report"])
def test_fixtures_give_sound_packages(name):
    text = (FIXTURES / f"{name}.md").read_text(encoding="utf-8")
    data, _ = write(md_to_doc(text), builtin_hwpx(), hwpx_settings(metadata=META))
    hwpx_integrity(data)


def test_metadata_preview_and_caret():
    data, _ = write(md_to_doc("# 첫 제목\n\n본문\n"), builtin_hwpx(), hwpx_settings(metadata=META))
    parts = hwpx_integrity(data)
    content = parts["Contents/content.hpf"]
    assert content.find(f"{OPF}metadata/{OPF}title").text == "제목"
    values = {m.get("name"): m.text for m in content.iter(f"{OPF}meta")}
    assert values["creator"] == "작성자" and values["keyword"] == "mdcast"
    assert values["mdcast.generator"] == "mdcast 0.1" and values["CreatedDate"] == "2026-10-16T00:00:00Z"
    preview = Package.read(data).get("Preview/PrvText.txt").decode("utf-8")
    assert preview.startswith("첫 제목\r\n본문")
    caret = parts["settings.xml"].find("{http://www.hancom.co.kr/hwpml/2011/app}CaretPosition")
    assert (caret.get("paraIDRef"), caret.get("pos")) == ("0", "0")


def test_outline_numbers_are_blanked_in_the_output():
    data, _ = write(md_to_doc("# 제목\n"), builtin_hwpx(), hwpx_settings())
    heads = hwpx_integrity(data)["Contents/header.xml"].findall(".//hh:numbering[@id='1']/hh:paraHead", NS)
    assert all(not (h.text or "") for h in heads)


def test_empty_document_keeps_the_section_settings():
    data, _ = write(md_to_doc(""), builtin_hwpx(), hwpx_settings())
    section = hwpx_integrity(data)["Contents/section0.xml"]
    assert len(section.findall("hp:p", NS)) == 1


def test_extra_sections_of_a_container_are_dropped():
    package = Package.read(builtin_hwpx())
    package.set("Contents/section1.xml", package.get("Contents/section0.xml"))
    content = package.xml("Contents/content.hpf")
    manifest = content.find(f"{OPF}manifest")
    item = manifest.makeelement(f"{OPF}item", {"id": "section1", "href": "Contents/section1.xml",
                                               "media-type": "application/xml"})
    manifest.append(item)
    spine = content.find(f"{OPF}spine")
    spine.append(spine.makeelement(f"{OPF}itemref", {"idref": "section1", "linear": "yes"}))
    package.set_xml("Contents/content.hpf", content)
    data, _ = write(md_to_doc("본문\n"), package.write(), hwpx_settings())
    out = Package.read(data)
    assert "Contents/section1.xml" not in out.names()
    assert b"section1" not in out.get("Contents/content.hpf")


def test_broken_container_raises():
    with pytest.raises(ContainerError):
        write(md_to_doc("본문\n"), b"junk", hwpx_settings())


def test_hwpx_package_imports_only_itself():
    pattern = re.compile(r"^\s*(?:from|import)\s+mdcast(?:\.(\w+))?", re.MULTILINE)
    for path in SRC.glob("*.py"):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            assert match.group(1) == "hwpx", f"{path.name}: {match.group(0).strip()}"
