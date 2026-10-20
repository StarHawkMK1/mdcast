from __future__ import annotations

import re

HANGUL = "가나다라마바사아자차카타파하"
_H = f"[{HANGUL}]"
_ROMAN = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ"
_BULLETS = "□■○●◦-·∙▪▫◇◆➢▶"
_CIRCLED_FIRST = 0x2460  # ① .. ⑳ is U+2460..U+2473

_DECIMAL = re.compile(r"^(\d+(?:\.\d+)*)(\.?)\s")
_HEADING_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("roman", re.compile(rf"^[{_ROMAN}]+\.\s")),
    ("hangul", re.compile(rf"^{_H}\.\s")),
    ("paren_decimal", re.compile(r"^\(\d+\)\s")),
    ("paren_hangul", re.compile(rf"^\({_H}\)\s")),
)
_BULLET = re.compile(rf"^([{re.escape(_BULLETS)}])\s")
_ORDERED: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("decimal_dot", re.compile(r"^(\d+)\.\s")),
    ("decimal_paren", re.compile(r"^(\d+)\)\s")),
    ("paren_decimal", re.compile(r"^\((\d+)\)\s")),
    ("circled", re.compile(r"^([①-⑳])\s")),
    ("hangul_dot", re.compile(rf"^({_H})\.\s")),
    ("hangul_paren", re.compile(rf"^({_H})\)\s")),
    ("paren_hangul", re.compile(rf"^\(({_H})\)\s")),
)


def heading_shape(text: str) -> tuple[str, int] | None:
    """(shape key, dot level) of a numbered heading prefix; the number must be followed by whitespace."""
    m = _DECIMAL.match(text)
    if m:
        count = m.group(1).count(".") + 1
        if count == 1 and not m.group(2):
            return None
        return "decimal", count
    for key, pattern in _HEADING_SHAPES:
        if pattern.match(text):
            return key, 1
    return None


def _number(key: str, token: str) -> int:
    if key == "circled":
        return ord(token) - _CIRCLED_FIRST + 1
    if key.startswith(("hangul", "paren_hangul")):
        return HANGUL.index(token) + 1
    return int(token)


def match_list_marker(text: str) -> tuple[str, str, int | None, re.Pattern[str]] | None:
    """(shape key, "bullet"|"ordered", number, matching pattern) of a list marker prefix, or None."""
    m = _BULLET.match(text)
    if m:
        return m.group(1), "bullet", None, _BULLET
    for key, pattern in _ORDERED:
        m = pattern.match(text)
        if m:
            return key, "ordered", _number(key, m.group(1)), pattern
    return None


def list_marker(text: str) -> tuple[str, str, int | None] | None:
    """(shape key, "bullet"|"ordered", number) of a list marker prefix, or None."""
    found = match_list_marker(text)
    return found[:3] if found else None


def strip_leading_marker(text: str) -> str:
    for pattern in (_BULLET, *(p for _, p in _HEADING_SHAPES), *(p for _, p in _ORDERED), _DECIMAL):
        if pattern is _DECIMAL and heading_shape(text) is None:
            continue
        m = pattern.match(text)
        if m:
            return text[m.end():].lstrip()
    return text
