from __future__ import annotations

import re

PAGE_SIZES_MM: dict[str, tuple[float, float]] = {
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "B5": (182.0, 257.0),
    "LETTER": (215.9, 279.4),
    "LEGAL": (215.9, 355.6),
}
_MM_PER = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72.0}
_NUM = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*([a-z%]*)\s*$", re.IGNORECASE)
_HEX = re.compile(r"^[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?$")


def _split(value: object) -> tuple[float, str]:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"숫자 값이 필요합니다: {value!r}")
    if isinstance(value, (int, float)):
        return float(value), ""
    match = _NUM.match(str(value))
    if not match:
        raise ValueError(f"값을 해석할 수 없습니다: {value!r}")
    return float(match.group(1)), match.group(2).lower()


def parse_length_mm(value: object) -> float:
    number, unit = _split(value)
    unit = unit or "mm"
    if unit not in _MM_PER:
        raise ValueError(f"지원하지 않는 길이 단위입니다: {value!r}")
    return round(number * _MM_PER[unit], 6)


def parse_pt(value: object) -> float:
    number, unit = _split(value)
    unit = unit or "pt"
    if unit not in _MM_PER:
        raise ValueError(f"지원하지 않는 크기 단위입니다: {value!r}")
    return round(number * _MM_PER[unit] / _MM_PER["pt"], 6)


def parse_ratio(value: object) -> float:
    number, unit = _split(value)
    if unit == "%":
        return number / 100.0
    if unit:
        raise ValueError(f"비율 값이 아닙니다: {value!r}")
    return number


def normalize_color(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lstrip("#")
    if not _HEX.match(text):
        raise ValueError(f"색상 값이 아닙니다: {value!r}")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    return text.upper()


def page_size_mm(size: str, orientation: str) -> tuple[float, float]:
    width, height = PAGE_SIZES_MM[str(size).upper()]
    if orientation == "landscape":
        return height, width
    return width, height
