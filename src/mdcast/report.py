from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from mdcast.types import Format, Output


class Level(str, Enum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


class Codes:
    TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
    TEMPLATE_INVALID = "TEMPLATE_INVALID"
    TEMPLATE_CONTAINER_FALLBACK = "TEMPLATE_CONTAINER_FALLBACK"
    STYLE_UNMAPPED = "STYLE_UNMAPPED"
    FIELD_EMPTY = "FIELD_EMPTY"
    FIELD_RESERVED = "FIELD_RESERVED"
    TABLE_VARIANT_UNKNOWN = "TABLE_VARIANT_UNKNOWN"
    IMAGE_FETCH_FAILED = "IMAGE_FETCH_FAILED"
    FONT_FALLBACK = "FONT_FALLBACK"
    PDF_HEADER_SIMPLIFIED = "PDF_HEADER_SIMPLIFIED"
    INPUT_ENCODING_FALLBACK = "INPUT_ENCODING_FALLBACK"
    FRONTMATTER_INVALID = "FRONTMATTER_INVALID"
    INPUT_UNSUPPORTED = "INPUT_UNSUPPORTED"
    INPUT_CORRUPT = "INPUT_CORRUPT"
    TARGET_UNSUPPORTED = "TARGET_UNSUPPORTED"
    RENDER_WARNING = "RENDER_WARNING"
    RENDER_FAILED = "RENDER_FAILED"
    OUTPUT_WRITE_FAILED = "OUTPUT_WRITE_FAILED"
    IMPORT_HEADING_INFERRED = "IMPORT_HEADING_INFERRED"
    IMPORT_LIST_INFERRED = "IMPORT_LIST_INFERRED"
    IMPORT_TEXT_MISSING = "IMPORT_TEXT_MISSING"
    IMPORT_IMAGE_TEXT = "IMPORT_IMAGE_TEXT"
    IMPORT_HEADER_SKIPPED = "IMPORT_HEADER_SKIPPED"
    IMAGE_CONVERT_FAILED = "IMAGE_CONVERT_FAILED"
    OUTPUT_EXISTS = "OUTPUT_EXISTS"


@dataclass(frozen=True)
class Event:
    level: Level
    code: str
    message: str
    where: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"level": self.level.value, "code": self.code, "message": self.message}
        if self.where:
            data["where"] = dict(self.where)
        return data


@dataclass
class TemplateInfo:
    name: str
    version: str
    source: str
    location: str | None
    per_format: dict[str, dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "source": self.source,
            "location": self.location,
            "per_format": {k: dict(v) for k, v in self.per_format.items()},
        }


class Report:
    def __init__(self, input_name: str, input_format: Format) -> None:
        self.input_name = input_name
        self.input_format = input_format
        self.events: list[Event] = []
        self.template: TemplateInfo | None = None
        self.outputs: list[dict[str, Any]] = []
        self.temp_dir: str | None = None
        self.coverage: float | None = None
        self._seen: set[tuple[Any, ...]] = set()

    def add(self, level: Level, code: str, message: str, *, once: bool = False, **where: Any) -> None:
        key = (level, code, message, tuple(sorted((k, repr(v)) for k, v in where.items())))
        if once and key in self._seen:
            return
        self._seen.add(key)
        self.events.append(Event(level, code, message, where))

    def info(self, code: str, message: str, *, once: bool = False, **where: Any) -> None:
        self.add(Level.INFO, code, message, once=once, **where)

    def warn(self, code: str, message: str, *, once: bool = False, **where: Any) -> None:
        self.add(Level.WARN, code, message, once=once, **where)

    def error(self, code: str, message: str, *, once: bool = False, **where: Any) -> None:
        self.add(Level.ERROR, code, message, once=once, **where)

    def events_for(self, fmt: Format) -> list[Event]:
        return [e for e in self.events if e.where.get("format") in (None, fmt.value)]

    def status_for(self, fmt: Format) -> str:
        events = self.events_for(fmt)
        if any(e.level is Level.ERROR for e in events):
            return "failed"
        if any(e.level is Level.WARN for e in events):
            return "degraded"
        return "ok"

    def set_outputs(self, outputs: Iterable[Output]) -> None:
        self.outputs = [
            {
                "format": o.format.value,
                "name": o.name,
                "status": "failed" if o.data is None else self.status_for(o.format),
            }
            for o in outputs
        ]

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "input": {"name": self.input_name, "format": self.input_format.value},
            "outputs": [dict(o) for o in self.outputs],
            "template": self.template.to_dict() if self.template else None,
            "events": [e.to_dict() for e in self.events],
        }
        if self.temp_dir:
            data["temp_dir"] = self.temp_dir
        if self.coverage is not None:
            data["coverage"] = self.coverage
        return data
