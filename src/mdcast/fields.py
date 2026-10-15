from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from mdcast.report import Codes, Report

RESERVED = ("page", "pages", "today")
FIELD_RE = re.compile(r"\{\{\s*([A-Za-z0-9_\-가-힣]+)\s*\}\}")


@dataclass(frozen=True)
class Text:
    value: str


@dataclass(frozen=True)
class PageField:
    kind: str


Segment = Text | PageField


def keys_in(template: str) -> list[str]:
    return [m.group(1) for m in FIELD_RE.finditer(template or "")]


def format_date(d: date, fmt: str) -> str:
    return fmt.replace("YYYY", f"{d.year:04d}").replace("MM", f"{d.month:02d}").replace("DD", f"{d.day:02d}")


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(_to_str(v) for v in value)
    if isinstance(value, dict):
        return ""
    return str(value)


def _merge_text(segments: list[Segment]) -> list[Segment]:
    merged: list[Segment] = []
    for seg in segments:
        if isinstance(seg, Text) and merged and isinstance(merged[-1], Text):
            merged[-1] = Text(merged[-1].value + seg.value)
        elif not (isinstance(seg, Text) and seg.value == ""):
            merged.append(seg)
    return merged


@dataclass
class ResolvedFields:
    values: dict[str, str]
    report: Report

    def render(self, template: str) -> list[Segment]:
        template = template or ""
        segments: list[Segment] = []
        pos = 0
        for match in FIELD_RE.finditer(template):
            segments.append(Text(template[pos : match.start()]))
            key = match.group(1)
            if key in ("page", "pages"):
                segments.append(PageField(key))
            else:
                value = self.values.get(key, "")
                if value == "":
                    self.report.info(Codes.FIELD_EMPTY, f"필드 '{key}' 값이 없어 빈칸으로 둡니다", once=True, field=key)
                segments.append(Text(value))
            pos = match.end()
        segments.append(Text(template[pos:]))
        return _merge_text(segments)

    def text(self, template: str) -> str:
        return "".join(s.value for s in self.render(template) if isinstance(s, Text))


def resolve_fields(
    frontmatter: dict[str, Any],
    config: dict[str, Any],
    report: Report,
    today: date | None = None,
) -> ResolvedFields:
    fields_cfg = config.get("fields") or {}
    values = {str(k): _to_str(v) for k, v in (fields_cfg.get("defaults") or {}).items()}
    for key, value in frontmatter.items():
        if key in RESERVED:
            report.info(Codes.FIELD_RESERVED, f"'{key}' 는 예약 키라 frontmatter 값을 무시합니다", field=key)
            continue
        values[str(key)] = _to_str(value)
    values["today"] = format_date(today or date.today(), fields_cfg.get("date_format") or "YYYY-MM-DD")

    def expand(match: re.Match[str]) -> str:
        key = match.group(1)
        return match.group(0) if key in ("page", "pages") else values.get(key, "")

    for key in list(values):
        if key != "today" and "{{" in values[key]:
            values[key] = FIELD_RE.sub(expand, values[key])
    return ResolvedFields(values, report)
