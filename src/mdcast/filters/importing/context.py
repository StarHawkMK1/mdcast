from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mdcast.report import Report


@dataclass
class ImportContext:
    report: Report
    frontmatter: dict[str, Any]
    generator: dict[str, str]
    cwd: Path
    home: Path
    prefixes: list[re.Pattern[str]] = field(default_factory=list)
    table_styles: list[str | None] = field(default_factory=list)
