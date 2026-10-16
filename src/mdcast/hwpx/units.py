"""OWPML lengths (spec 2026-10-16 m2a §5.1, appendix A-4, A-12).

HWPUNIT is 1/7200 inch (1pt = 100). Hangul reads paragraph margins (left, right, intent, prev,
next) and tab positions at twice that unit; page sizes, page margins, border offsets and
header/footer list sizes are plain HWPUNIT.
"""

from __future__ import annotations


def hwpunit(mm: float) -> int:
    return round(mm * 7200 / 25.4)


def hwpunit_pt(pt: float) -> int:
    return round(pt * 100)


def para_unit(mm: float) -> int:
    return round(mm * 14400 / 25.4)


def para_unit_pt(pt: float) -> int:
    return round(pt * 200)
