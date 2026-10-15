from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mdcast.report import Report
from mdcast.types import Format


@dataclass
class FilterContext:
    target: Format
    config: dict[str, Any]
    frontmatter: dict[str, Any]
    report: Report
    state: dict[str, Any] = field(default_factory=dict)
