"""Pictures: sizes, BinData and manifest entries, ``hp:pic`` (spec 2026-10-20 §5, appendix B-9)."""

from __future__ import annotations

import hashlib
import re

from lxml import etree

from mdcast.hwpx.container import Package
from mdcast.hwpx.look import Image
from mdcast.hwpx.units import hwpunit

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
OPF = "http://www.idpf.org/2007/opf/"
MEDIA = {"png": "image/png", "jpg": "image/jpg", "gif": "image/gif", "bmp": "image/bmp", "svg": "image/svg"}
# HWPUNIT per pixel Hangul writes for a picture it places (appendix B-9): (orgSz, imgDim)
_PER_PX = {"svg": (75.0, 60.0)}
_RASTER_PER_PX = (93.75, 75.0)
_LENGTH = re.compile(r"\s*([0-9]*\.?[0-9]+)\s*(%|mm|cm|in|pt|px)?\s*$")
_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72, "px": 25.4 / 96, None: 25.4 / 96}


def _hp(tag: str) -> str:
    return f"{{{HP}}}{tag}"


def _hc(tag: str) -> str:
    return f"{{{HC}}}{tag}"


def parse_length(value: str, available_mm: float) -> float | None:
    """A pandoc image ``width``/``height`` in mm: ``%`` of ``available_mm``, units, or bare px."""
    match = _LENGTH.match(value or "")
    if not match:
        return None
    number, unit = float(match.group(1)), match.group(2)
    return number / 100 * available_mm if unit == "%" else number * _MM[unit]


def picture_size(image: Image, width: str | None, height: str | None, available_mm: float,
                 max_ratio: float | None, max_mm: float | None) -> tuple[float, float]:
    """Display size in mm: attributes or pixels at the image's dpi, within the width limit (spec §5.2)."""
    natural_w = image.width_px / image.dpi * 25.4
    natural_h = image.height_px / image.dpi * 25.4
    w = parse_length(width, available_mm) if width else None
    h = parse_length(height, available_mm) if height else None
    if w and h:
        size_w, size_h = w, h
    elif w:
        size_w, size_h = w, w * natural_h / natural_w
    elif h:
        size_w, size_h = h * natural_w / natural_h, h
    else:
        size_w, size_h = natural_w, natural_h
    limit = available_mm
    if max_ratio is not None:
        limit = min(limit, max_ratio * available_mm)
    elif max_mm is not None:
        limit = min(limit, max_mm)
    if size_w > limit:
        size_w, size_h = limit, size_h * limit / size_w
    return size_w, size_h


class Pictures:
    """Picture files of one package: one BinData entry per distinct image."""

    def __init__(self, package: Package, content: etree._Element) -> None:
        self.package = package
        self.content = content
        self._ids: dict[str, str] = {}

    def add(self, image: Image) -> str:
        """The manifest item id holding ``image``; new ones go under ``BinData/mdcastimg<n>.<ext>``."""
        digest = hashlib.sha256(image.data).hexdigest()
        if digest in self._ids:
            return self._ids[digest]
        manifest = self.content.find(f"{{{OPF}}}manifest")
        names = set(self.package.names())
        ids = {item.get("id") for item in manifest} if manifest is not None else set()
        number = 1
        while f"mdcastimg{number}" in ids or any(n.startswith(f"BinData/mdcastimg{number}.") for n in names):
            number += 1
        item_id = f"mdcastimg{number}"
        href = f"BinData/{item_id}.{image.ext}"
        self.package.set(href, image.data)
        if manifest is not None:
            etree.SubElement(manifest, f"{{{OPF}}}item", {
                "id": item_id, "href": href, "media-type": MEDIA.get(image.ext, "image/png"), "isEmbeded": "1",
            })
        self._ids[digest] = item_id
        return item_id


def picture_element(item_id: str, image: Image, width_mm: float, height_mm: float, alt: str,
                    number: int, caption: etree._Element | None) -> etree._Element:
    """``hp:pic`` as Hangul writes it (appendix B-9); ``alt`` must already be XML-safe."""
    org_per_px, dim_per_px = _PER_PX.get(image.ext, _RASTER_PER_PX)
    org_w, org_h = round(image.width_px * org_per_px), round(image.height_px * org_per_px)
    dim_w, dim_h = round(image.width_px * dim_per_px), round(image.height_px * dim_per_px)
    width, height = hwpunit(width_mm), hwpunit(height_mm)
    n = str(number)
    pic = etree.Element(_hp("pic"), id=n, zOrder=n, numberingType="PICTURE", textWrap="TOP_AND_BOTTOM",
                        textFlow="BOTH_SIDES", lock="0", dropcapstyle="None", href="", groupLevel="0",
                        instid=n, reverse="0")
    etree.SubElement(pic, _hp("offset"), x="0", y="0")
    etree.SubElement(pic, _hp("orgSz"), width=str(org_w), height=str(org_h))
    etree.SubElement(pic, _hp("curSz"), width=str(width), height=str(height))
    etree.SubElement(pic, _hp("flip"), horizontal="0", vertical="0")
    etree.SubElement(pic, _hp("rotationInfo"), angle="0", centerX=str(width // 2), centerY=str(height // 2),
                     rotateimage="1")
    rendering = etree.SubElement(pic, _hp("renderingInfo"))
    identity = {"e1": "1", "e2": "0", "e3": "0", "e4": "0", "e5": "1", "e6": "0"}
    etree.SubElement(rendering, _hc("transMatrix"), identity)
    etree.SubElement(rendering, _hc("scaMatrix"), {**identity, "e1": f"{width / org_w:.6f}",
                                                   "e5": f"{height / org_h:.6f}"})
    etree.SubElement(rendering, _hc("rotMatrix"), identity)
    rect = etree.SubElement(pic, _hp("imgRect"))
    for name, (x, y) in zip(("pt0", "pt1", "pt2", "pt3"), ((0, 0), (org_w, 0), (org_w, org_h), (0, org_h))):
        etree.SubElement(rect, _hc(name), x=str(x), y=str(y))
    etree.SubElement(pic, _hp("imgClip"), left="0", right=str(dim_w), top="0", bottom=str(dim_h))
    etree.SubElement(pic, _hp("inMargin"), left="0", right="0", top="0", bottom="0")
    etree.SubElement(pic, _hp("imgDim"), dimwidth=str(dim_w), dimheight=str(dim_h))
    etree.SubElement(pic, _hc("img"), binaryItemIDRef=item_id, bright="0", contrast="0", effect="REAL_PIC",
                     alpha="0")
    etree.SubElement(pic, _hp("effects"))
    etree.SubElement(pic, _hp("sz"), width=str(width), widthRelTo="ABSOLUTE", height=str(height),
                     heightRelTo="ABSOLUTE", protect="0")
    etree.SubElement(pic, _hp("pos"), treatAsChar="1", affectLSpacing="0", flowWithText="1", allowOverlap="0",
                     holdAnchorAndSO="0", vertRelTo="PARA", horzRelTo="PARA", vertAlign="TOP", horzAlign="LEFT",
                     vertOffset="0", horzOffset="0")
    etree.SubElement(pic, _hp("outMargin"), left="0", right="0", top="0", bottom="0")
    if caption is not None:
        pic.append(caption)
    etree.SubElement(pic, _hp("shapeComment")).text = alt
    return pic
