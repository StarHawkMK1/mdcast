"""``write``: pandoc AST + container + settings → hwpx bytes (spec §4.1)."""

from __future__ import annotations

import panflute as pf

from mdcast.hwpx.container import Package
from mdcast.hwpx.header import Header
from mdcast.hwpx.look import Notice, Notices, Settings
from mdcast.hwpx.meta import apply_metadata, keep_first_section, preview_text, reset_caret
from mdcast.hwpx.page import assemble, find_sec_pr_run
from mdcast.hwpx.section import SectionWriter, hp
from mdcast.hwpx.shapes import build_shapes


def write(doc: pf.Doc, container: bytes, settings: Settings) -> tuple[bytes, list[Notice]]:
    """Raises ``ContainerError`` when ``container`` is not a usable hwpx."""
    package = Package.read(container)
    header = Header(package.xml("Contents/header.xml"))
    section = package.xml("Contents/section0.xml")
    content = package.xml("Contents/content.hpf")
    notices = Notices()
    sec_pr = find_sec_pr_run(section).find(hp("secPr"))
    header.blank_numbering(sec_pr.get("outlineShapeIDRef", "1"))
    shapes = build_shapes(header, settings, notices)
    paragraphs = SectionWriter(header, shapes, settings, notices).build(doc)
    assemble(section, paragraphs, header, shapes, settings)
    apply_metadata(content, settings.metadata)
    keep_first_section(package, content)
    package.set_xml("Contents/header.xml", header.root)
    package.set_xml("Contents/section0.xml", section)
    package.set_xml("Contents/content.hpf", content)
    if "Preview/PrvText.txt" in package.names():
        package.set("Preview/PrvText.txt", preview_text(paragraphs))
    if "settings.xml" in package.names():
        app = package.xml("settings.xml")
        reset_caret(app)
        package.set_xml("settings.xml", app)
    return package.write(), list(notices.items)
