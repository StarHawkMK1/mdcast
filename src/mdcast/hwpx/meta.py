"""content.hpf metadata, preview text, caret position and extra sections (spec §6.3)."""

from __future__ import annotations

import re

from lxml import etree

from mdcast.hwpx.container import Package
from mdcast.hwpx.look import Metadata
from mdcast.hwpx.section import clean, hp

OPF = "http://www.idpf.org/2007/opf/"
HA = "http://www.hancom.co.kr/hwpml/2011/app"
MAX_PREVIEW = 1000
_SECTION = re.compile(r"Contents/section[1-9]\d*\.xml")


def _opf(tag: str) -> str:
    return f"{{{OPF}}}{tag}"


def _meta(metadata: etree._Element, name: str) -> etree._Element:
    for element in metadata.findall(_opf("meta")):
        if element.get("name") == name:
            return element
    return etree.SubElement(metadata, _opf("meta"), name=name, content="text")


def apply_metadata(package_root: etree._Element, md: Metadata) -> None:
    metadata = package_root.find(_opf("metadata"))
    if metadata is None:
        metadata = etree.Element(_opf("metadata"))
        package_root.insert(0, metadata)
    title = metadata.find(_opf("title"))
    if title is None:
        title = etree.SubElement(metadata, _opf("title"))
    title.text = clean(md.title) or None
    values = {"creator": md.author, "keyword": md.keywords, "CreatedDate": md.created,
              "ModifiedDate": md.created, "date": "", **dict(md.extra)}
    for name, value in values.items():
        _meta(metadata, name).text = clean(value or "") or None


def keep_first_section(package: Package, package_root: etree._Element) -> None:
    """A form's other sections would show its own text after mdcast's body: drop them."""
    manifest = package_root.find(_opf("manifest"))
    spine = package_root.find(_opf("spine"))
    for item in list(manifest if manifest is not None else []):
        if _SECTION.fullmatch(item.get("href", "")):
            manifest.remove(item)
            for ref in list(spine if spine is not None else []):
                if ref.get("idref") == item.get("id"):
                    spine.remove(ref)
    for name in package.names():
        if _SECTION.fullmatch(name):
            package.remove(name)


def preview_text(paragraphs: list[etree._Element]) -> bytes:
    lines = ["".join("".join(t.itertext()) for t in p.findall(f"{hp('run')}/{hp('t')}")) for p in paragraphs]
    return ("\r\n".join(lines)[:MAX_PREVIEW] + "\r\n").encode("utf-8")


def reset_caret(app_root: etree._Element) -> None:
    for caret in app_root.iter(f"{{{HA}}}CaretPosition"):
        caret.set("listIDRef", "0")
        caret.set("paraIDRef", "0")
        caret.set("pos", "0")
