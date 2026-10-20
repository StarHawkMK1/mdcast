"""Prepare a docx package for pandoc's reader and collect facts pandoc drops."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from lxml import etree

PAGEBREAK_SENTINEL = "⁣MDCAST-PAGEBREAK⁣"

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DC = "http://purl.org/dc/elements/1.1/"
_CP = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
_XML = "http://www.w3.org/XML/1998/namespace"
_SEPARATORS = {"separator", "continuationSeparator", "continuationNotice"}
_TABLE_KIND = re.compile(r"^Table \((.+)\)$")
_HEADER_FOOTER = re.compile(r"word/(header|footer)\d*\.xml")
_OFF = ("0", "false", "off")


def _w(tag: str) -> str:
    return f"{{{_W}}}{tag}"


@dataclass
class PreparedDocx:
    data: bytes
    source_text: list[str] = field(default_factory=list)
    title: str | None = None
    author: str | None = None
    generator: dict[str, str] = field(default_factory=dict)
    has_header_footer: bool = False
    has_comments: bool = False
    table_styles: list[str | None] = field(default_factory=list)


def _parse(blob: bytes) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    return etree.fromstring(blob, parser)


def _dump(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _paragraph_text(p: etree._Element) -> str:
    parts = []
    for t in p.iter(_w("t")):
        owner = next(t.iterancestors(_w("p")), None)
        if owner is p:
            parts.append(t.text or "")
    return "".join(parts)


def _texts(root: etree._Element, skip_separators: bool = False) -> list[str]:
    out = []
    for p in root.iter(_w("p")):
        if skip_separators:
            note = next(p.iterancestors(_w("footnote"), _w("endnote")), None)
            if note is not None and note.get(_w("type")) in _SEPARATORS:
                continue
        if text := _paragraph_text(p):
            out.append(text)
    return out


def _style_maps(styles: etree._Element | None) -> tuple[dict[str, int], dict[str, str]]:
    """styleId -> outline level (own, or inherited through basedOn) and styleId -> name."""
    own: dict[str, int] = {}
    based: dict[str, str] = {}
    names: dict[str, str] = {}
    if styles is not None:
        for style in styles.iter(_w("style")):
            sid = style.get(_w("styleId"))
            if not sid:
                continue
            name = style.find(_w("name"))
            names[sid] = name.get(_w("val"), "") if name is not None else ""
            level = style.find(f"{_w('pPr')}/{_w('outlineLvl')}")
            if level is not None:
                own[sid] = int(level.get(_w("val"), "9"))
            parent = style.find(_w("basedOn"))
            if parent is not None:
                based[sid] = parent.get(_w("val"), "")
    levels: dict[str, int] = {}
    for sid in names:
        current, seen = sid, set()
        while current and current not in seen:
            if current in own:
                levels[sid] = own[current]
                break
            seen.add(current)
            current = based.get(current, "")
    return levels, names


def _sentinel() -> etree._Element:
    p = etree.Element(_w("p"))
    t = etree.SubElement(etree.SubElement(p, _w("r")), _w("t"))
    t.set(f"{{{_XML}}}space", "preserve")
    t.text = PAGEBREAK_SENTINEL
    return p


def _rewrite_body(document: etree._Element, levels: dict[str, int]) -> None:
    for p in list(document.iter(_w("p"))):
        ppr = p.find(_w("pPr"))
        style = ppr.find(_w("pStyle")) if ppr is not None else None
        own = ppr.find(_w("outlineLvl")) if ppr is not None else None
        sid = style.get(_w("val")) if style is not None else None
        level = int(own.get(_w("val"), "9")) if own is not None else levels.get(sid or "")
        if level is not None and 0 <= level <= 8 and _paragraph_text(p).strip():
            if ppr is None:
                ppr = etree.Element(_w("pPr"))
                p.insert(0, ppr)
            if style is None:
                style = etree.Element(_w("pStyle"))
                ppr.insert(0, style)
            style.set(_w("val"), f"MdcastH{level + 1}")

        parent = p.getparent()
        before = ppr.find(_w("pageBreakBefore")) if ppr is not None else None
        if before is not None:
            if before.get(_w("val"), "true") not in _OFF:
                parent.insert(parent.index(p), _sentinel())
            ppr.remove(before)
        for br in list(p.iter(_w("br"))):
            if br.get(_w("type")) != "page":
                continue
            parent.insert(parent.index(p), _sentinel())
            run = br.getparent()
            run.remove(br)
            if run.tag == _w("r") and not [c for c in run if c.tag != _w("rPr")]:
                run.getparent().remove(run)


def _inject_styles(styles: etree._Element) -> None:
    for n in range(1, 10):
        style = etree.SubElement(styles, _w("style"))
        style.set(_w("type"), "paragraph")
        style.set(_w("styleId"), f"MdcastH{n}")
        etree.SubElement(style, _w("name")).set(_w("val"), f"heading {n}")


def _has_content(root: etree._Element) -> bool:
    if _texts(root):
        return True
    return next(root.iter(_w("fldSimple"), _w("instrText"), _w("drawing"), _w("pict"), _w("object")), None) is not None


def _generator(blob: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for prop in _parse(blob).iter(f"{{{_CP}}}property"):
        name = prop.get("name") or ""
        if name.startswith("mdcast."):
            out[name] = "".join(prop.itertext())
    return out


def prepare_docx(data: bytes) -> PreparedDocx:
    source = zipfile.ZipFile(io.BytesIO(data))
    names = set(source.namelist())
    document = _parse(source.read("word/document.xml"))
    styles = _parse(source.read("word/styles.xml")) if "word/styles.xml" in names else None
    levels, style_names = _style_maps(styles)

    result = PreparedDocx(data=b"")
    result.source_text = _texts(document)
    for part in ("word/footnotes.xml", "word/endnotes.xml"):
        if part in names:
            result.source_text.extend(_texts(_parse(source.read(part)), skip_separators=True))

    for tbl in document.iter(_w("tbl")):
        ref = tbl.find(f"{_w('tblPr')}/{_w('tblStyle')}")
        match = _TABLE_KIND.match(style_names.get(ref.get(_w("val")), "")) if ref is not None else None
        result.table_styles.append(match.group(1) if match else None)

    if "docProps/core.xml" in names:
        core = _parse(source.read("docProps/core.xml"))
        title, author = core.find(f"{{{_DC}}}title"), core.find(f"{{{_DC}}}creator")
        result.title = (title.text or None) if title is not None else None
        result.author = (author.text or None) if author is not None else None
    if "docProps/custom.xml" in names:
        result.generator = _generator(source.read("docProps/custom.xml"))
    result.has_header_footer = any(
        _HEADER_FOOTER.fullmatch(name) and _has_content(_parse(source.read(name))) for name in names
    )
    if "word/comments.xml" in names:
        result.has_comments = next(_parse(source.read("word/comments.xml")).iter(_w("comment")), None) is not None

    _rewrite_body(document, levels)
    changed = {"word/document.xml": _dump(document)}
    if styles is not None:
        _inject_styles(styles)
        changed["word/styles.xml"] = _dump(styles)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            target.writestr(info, changed.get(info.filename, source.read(info.filename)))
    result.data = out.getvalue()
    return result
