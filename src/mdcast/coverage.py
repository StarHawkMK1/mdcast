from __future__ import annotations

import re
from collections.abc import Sequence

import panflute as pf

from mdcast.filters.importing.markers import strip_leading_marker
from mdcast.readers.md import read_md
from mdcast.report import Codes, Report
from mdcast.types import Format, Source

_SPACE = re.compile(r"\s+")
_MAX_SNIPPETS = 3
_SNIPPET_LEN = 20


def _squash(text: str) -> str:
    return _SPACE.sub("", text)


def _forms(text: str, prefixes: Sequence[re.Pattern[str]]) -> list[str]:
    forms = [text, strip_leading_marker(text)]
    for pattern in prefixes:
        m = pattern.match(text)
        if m:
            forms.append(text[m.end():])
    return [f for f in (_squash(f) for f in forms) if f]


def measure_coverage(
    source_text: Sequence[str],
    md_text: str,
    report: Report,
    prefixes: Sequence[re.Pattern[str]] = (),
) -> float:
    """Share of source characters (whitespace excluded) still present in the MD read back."""
    scratch = Report(report.input_name, Format.MD)
    parsed = read_md(Source(md_text.encode("utf-8"), "out.md", Format.MD), scratch)
    output = _squash(pf.stringify(parsed.doc))
    total = found = 0
    missing: list[str] = []
    for paragraph in source_text:
        size = len(_squash(paragraph))
        if not size:
            continue
        total += size
        if any(form in output for form in _forms(paragraph, prefixes)):
            found += size
        else:
            missing.append(paragraph.strip())
    value = round(found / total, 4) if total else 1.0
    report.coverage = value
    if missing:
        shown = ", ".join(
            f"'{m[:_SNIPPET_LEN]}{'…' if len(m) > _SNIPPET_LEN else ''}'" for m in missing[:_MAX_SNIPPETS]
        )
        report.warn(
            Codes.IMPORT_TEXT_MISSING,
            f"원본 글 일부가 MD 에 없습니다 ({len(missing)}문단): {shown}",
        )
    return value
