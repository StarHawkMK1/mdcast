"""Drawing objects in a run: pictures, text boxes and shapes, groups, and objects with no text."""

from __future__ import annotations

import re

from lxml import etree

from mdcast.readers.hwpx.package import HP

HC = "http://www.hancom.co.kr/hwpml/2011/core"


def _hp(tag: str) -> str:
    return f"{{{HP}}}{tag}"


PIC, CONTAINER = _hp("pic"), _hp("container")
# shapes whose hp:drawText holds paragraphs (a text box is a rectangle with text)
SHAPES = tuple(_hp(t) for t in ("rect", "ellipse", "polygon", "arc", "curve", "connectLine"))
# objects whose content is not text: Hancom text art, charts, OLE objects
NO_TEXT = tuple(_hp(t) for t in ("textart", "chart", "ole"))
OBJECTS = (PIC, CONTAINER, *SHAPES, *NO_TEXT)
DRAW_TEXT, CAPTION, SUB = _hp("drawText"), _hp("caption"), _hp("subList")
_COMMENT, _CUR_SIZE = _hp("shapeComment"), _hp("curSz")
_IMG = (f"{{{HC}}}img", _hp("img"))  # Hancom writes hc:img; hp:img is read too

# the description Hancom writes itself when a picture is placed: a fixed first line, then the
# original file's name and size (and for some pictures the program that made it)
_AUTO_FIRST = "그림입니다."
_AUTO_LINE = re.compile(r"(원본 그림의 이름|원본 그림의 크기|프로그램 이름)\s*:")


def is_object(e: etree._Element) -> bool:
    """A drawing object this reader places: a known one, or any other with text to draw."""
    return e.tag in OBJECTS or e.find(DRAW_TEXT) is not None


def comment(obj: etree._Element) -> str:
    """The object's ``hp:shapeComment``, line ends as ``\n``; empty when it has none."""
    found = obj.find(_COMMENT)
    text = "".join(found.itertext()) if found is not None else ""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def human_comment(obj: etree._Element) -> str:
    """The comment, unless it is the description Hancom writes for every picture."""
    text = comment(obj)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if lines and lines[0] == _AUTO_FIRST and all(_AUTO_LINE.match(line) for line in lines[1:]):
        return ""
    return text


def picture_ref(pic: etree._Element) -> str:
    """The manifest item id of a picture's file; empty when it names none."""
    img = next((e for e in map(pic.find, _IMG) if e is not None), None)
    return (img.get("binaryItemIDRef") or "") if img is not None else ""


def height(obj: etree._Element) -> int | None:
    """The object's current height (``hp:curSz``) in HWPUNIT, or None."""
    size = obj.find(_CUR_SIZE)
    try:
        return int(size.get("height") or "") if size is not None else None
    except ValueError:
        return None


def sub_list(obj: etree._Element, owner: str) -> etree._Element | None:
    """The ``hp:subList`` of the object's ``owner`` child (its drawText or caption)."""
    found = obj.find(owner)
    return found.find(SUB) if found is not None else None
