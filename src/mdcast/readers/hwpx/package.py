"""Open an hwpx package: sections in spine order, header styles, binary data and metadata."""

from __future__ import annotations

import io
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from lxml import etree

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS = "http://www.hancom.co.kr/hwpml/2011/section"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
# Hancom writes the OPF namespace with a trailing slash; accept the textbook form too.
_OPFS = ("http://www.idpf.org/2007/opf/", "http://www.idpf.org/2007/opf")
_ODF = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
_CONTENT = "Contents/content.hpf"
_HEADER = "Contents/header.xml"
_MANIFEST = "META-INF/manifest.xml"
_NO_STRIKE = ("NONE", "3D")  # Hancom writes shape="3D" on text that is not struck through
_SECURED = "암호가 걸렸거나 문서 보안(DRM)이 적용된 hwpx 는 읽을 수 없습니다. 한글에서 보안을 푼 뒤 다시 저장해 주십시오."
# a package part that is not XML: plain damage, or a secured document whose parts are scrambled
_UNREADABLE = "hwpx 파일의 {} 을(를) XML 로 읽을 수 없습니다. 파일이 깨졌거나 보안(암호)이 걸려 있을 수 있습니다."


class HwpxError(Exception):
    """A broken or encrypted package. The message is shown to the user."""


@dataclass(frozen=True)
class CharStyle:
    bold: bool = False
    italic: bool = False
    superscript: bool = False
    subscript: bool = False
    strike: bool = False


@dataclass(frozen=True)
class ParaStyle:
    kind: str = "NONE"  # "NONE" | "OUTLINE" | "NUMBER" | "BULLET"  (hh:paraPr/hh:heading@type)
    level: int = 0  # hh:heading@level
    list_id: str | None = None  # hh:heading@idRef (NUMBER → hh:numbering, BULLET → hh:bullet)
    align: str = ""  # hh:align@horizontal (LEFT, RIGHT, CENTER, JUSTIFY …)


@dataclass(frozen=True)
class CharLook:
    """What the mdcast hwpx writer sets a code or quote run apart by (read only for mdcast documents)."""

    font: str = ""  # the Latin face (hh:fontRef@latin → hh:fontface lang="LATIN")
    color: str = ""  # hh:charPr@textColor, upper case


@dataclass(frozen=True)
class ParaLook:
    """What the mdcast hwpx writer sets a code block or horizontal rule apart by."""

    fill: str = ""  # the border fill's face colour, upper case; "" for none
    rule: bool = False  # the border fill draws a bottom line and no other


@dataclass
class Styles:
    chars: dict[str, CharStyle]
    paras: dict[str, ParaStyle]
    numbering_start: dict[
        str, int
    ]  # hh:numbering@id → first-level start (hh:paraHead@start, default 1)
    char_looks: dict[str, CharLook] = field(default_factory=dict)
    para_looks: dict[str, ParaLook] = field(default_factory=dict)


@dataclass
class HwpxPackage:
    sections: list[etree._Element]  # content.hpf spine order
    styles: Styles
    bin_data: dict[str, tuple[str, bytes]]  # manifest item id → (BinData/ file name, bytes)
    title: str | None
    creator: str | None
    generator: dict[str, str]  # content.hpf opf:meta named "mdcast.*" with a value


def hh(tag: str) -> str:
    return f"{{{HH}}}{tag}"


def _int(value: str | None, default: int) -> int:
    try:
        return int(value or "")
    except ValueError:
        return default


def _read(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError:
        raise HwpxError(f"hwpx 파일이 깨져 있습니다: {name} 이(가) 없습니다.") from None
    except RuntimeError:  # a password-protected zip entry
        raise HwpxError(_SECURED) from None
    except (zipfile.BadZipFile, NotImplementedError, zlib.error, OSError, EOFError) as exc:
        raise HwpxError(
            f"hwpx 파일이 깨져 있습니다: {name} 을(를) 풀 수 없습니다 ({exc})."
        ) from None


def _parse(archive: zipfile.ZipFile, name: str, unreadable: str | None = None) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    try:
        return etree.fromstring(_read(archive, name), parser)
    except etree.XMLSyntaxError:
        raise HwpxError(
            unreadable or f"hwpx 파일이 깨져 있습니다: {name} 을(를) XML 로 읽을 수 없습니다."
        ) from None


def _opf(root: etree._Element, path: str) -> list[etree._Element]:
    """Elements at ``path`` ("metadata/meta") in either OPF namespace spelling."""
    for ns in _OPFS:
        found = root.findall("/".join(f"{{{ns}}}{step}" for step in path.split("/")))
        if found:
            return found
    return []


def _text(element: etree._Element | None) -> str | None:
    value = "".join(element.itertext()).strip() if element is not None else ""
    return value or None


def _is_encrypted(archive: zipfile.ZipFile) -> bool:
    if _MANIFEST not in archive.namelist():
        return False
    manifest = _parse(archive, _MANIFEST, _SECURED)
    return next(manifest.iter(f"{{{_ODF}}}encryption-data"), None) is not None


def _char_style(element: etree._Element) -> CharStyle:
    strike = element.find(hh("strikeout"))
    return CharStyle(
        bold=element.find(hh("bold")) is not None,
        italic=element.find(hh("italic")) is not None,
        superscript=element.find(hh("supscript")) is not None,
        subscript=element.find(hh("subscript")) is not None,
        strike=strike is not None and (strike.get("shape") or "NONE").upper() not in _NO_STRIKE,
    )


def _para_style(element: etree._Element) -> ParaStyle:
    # paraPr children may sit inside hp:switch case/default copies
    align_el = next(element.iter(hh("align")), None)
    align = (align_el.get("horizontal") or "").upper() if align_el is not None else ""
    heading = next(element.iter(hh("heading")), None)
    if heading is None:
        return ParaStyle(align=align)
    kind = (heading.get("type") or "NONE").upper()
    list_id = heading.get("idRef") if kind in ("NUMBER", "BULLET") else None
    return ParaStyle(kind, _int(heading.get("level"), 0), list_id, align)


def _numbering_start(numbering: etree._Element) -> int:
    heads = numbering.findall(hh("paraHead"))
    first = next((head for head in heads if head.get("level") == "1"), heads[0] if heads else None)
    return _int(first.get("start") if first is not None else None, 1)


def _styles(header: etree._Element | None) -> Styles:
    if header is None:
        return Styles({}, {}, {})
    chars = {
        e.get("id"): _char_style(e) for e in header.iter(hh("charPr")) if e.get("id") is not None
    }
    paras = {
        e.get("id"): _para_style(e) for e in header.iter(hh("paraPr")) if e.get("id") is not None
    }
    starts = {
        e.get("id"): _numbering_start(e)
        for e in header.iter(hh("numbering"))
        if e.get("id") is not None
    }
    return Styles(chars, paras, starts, _char_looks(header), _para_looks(header))


def _char_looks(header: etree._Element) -> dict[str, CharLook]:
    latin = {
        font.get("id"): font.get("face") or ""
        for fontface in header.iter(hh("fontface"))
        if (fontface.get("lang") or "").upper() == "LATIN"
        for font in fontface.iter(hh("font"))
    }
    looks = {}
    for e in header.iter(hh("charPr")):
        ref = e.find(hh("fontRef"))
        face = latin.get(ref.get("latin")) or "" if ref is not None else ""
        looks[e.get("id")] = CharLook(face, (e.get("textColor") or "").upper())
    return looks


def _para_looks(header: etree._Element) -> dict[str, ParaLook]:
    fills = {}
    for e in header.iter(hh("borderFill")):
        brush = next(e.iter(f"{{{HC}}}winBrush"), None)
        face = (brush.get("faceColor") or "").upper() if brush is not None else ""
        sides = {
            side: (e.find(hh(side)).get("type") if e.find(hh(side)) is not None else "NONE") or "NONE"
            for side in ("leftBorder", "rightBorder", "topBorder", "bottomBorder")
        }
        rule = sides.pop("bottomBorder").upper() != "NONE" and all(t.upper() == "NONE" for t in sides.values())
        fills[e.get("id")] = ParaLook("" if face == "NONE" else face, rule)
    looks = {}
    for e in header.iter(hh("paraPr")):
        border = next(e.iter(hh("border")), None)
        looks[e.get("id")] = fills.get(border.get("borderFillIDRef") if border is not None else None, ParaLook())
    return looks


def open_hwpx(data: bytes) -> HwpxPackage:
    """Open an hwpx package; a broken or secured package raises :class:`HwpxError`."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, EOFError, ValueError):
        raise HwpxError(
            "hwpx 파일로 열 수 없습니다. 파일이 깨졌거나 문서 보안(DRM)이 걸려 있을 수 있습니다."
        ) from None
    with archive:
        if _is_encrypted(archive):
            raise HwpxError(_SECURED)
        content = _parse(archive, _CONTENT, _UNREADABLE.format(_CONTENT))
        items = {item.get("id"): item.get("href") or "" for item in _opf(content, "manifest/item")}
        names = set(archive.namelist())

        header_href = items.get("header") or _HEADER
        header = _parse(archive, header_href, _UNREADABLE.format(header_href)) if header_href in names else None

        sections = []
        for ref in _opf(content, "spine/itemref"):
            href = items.get(ref.get("idref"))
            if not href or href == header_href:
                continue
            root = _parse(archive, href, _SECURED)
            if root.tag == f"{{{HS}}}sec":
                sections.append(root)
        if not sections:
            raise HwpxError("hwpx 파일이 깨져 있습니다: 본문 구역(section)이 없습니다.")

        bin_data = {
            item_id: (PurePosixPath(href).name, _read(archive, href))
            for item_id, href in items.items()
            if item_id and href.startswith("BinData/") and href in names
        }

        metas = {meta.get("name") or "": _text(meta) for meta in _opf(content, "metadata/meta")}
        titles = _opf(content, "metadata/title")
        return HwpxPackage(
            sections=sections,
            styles=_styles(header),
            bin_data=bin_data,
            title=_text(titles[0]) if titles else None,
            creator=metas.get("creator"),
            generator={
                name: value for name, value in metas.items() if name.startswith("mdcast.") and value
            },
        )
