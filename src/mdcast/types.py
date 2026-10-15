from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mdcast.report import Report


class Format(str, Enum):
    MD = "md"
    DOCX = "docx"
    HWPX = "hwpx"
    PDF = "pdf"

    @classmethod
    def parse(cls, value: str) -> Format:
        return cls(value.strip().lower().lstrip("."))

    @classmethod
    def from_filename(cls, name: str) -> Format:
        suffix = Path(name).suffix.lower().lstrip(".")
        if suffix == "markdown":
            suffix = "md"
        return cls(suffix)


@dataclass(frozen=True)
class Source:
    data: bytes
    name: str
    format: Format
    base_dir: Path | None = None


@dataclass(frozen=True)
class Options:
    offline: bool = False
    keep_temp: bool = False
    temp_root: Path | None = None
    cwd: Path | None = None
    home: Path | None = None
    url_timeout_s: float = 10.0


@dataclass
class Output:
    format: Format
    name: str
    data: bytes | None
    assets: dict[str, bytes] = field(default_factory=dict)


@dataclass
class Result:
    outputs: list[Output]
    report: Report
