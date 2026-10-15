from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mdcast.fields import ResolvedFields
from mdcast.report import Report
from mdcast.templates import ResolvedTemplate
from mdcast.types import Format, Options


class RenderError(Exception):
    """A target format could not be rendered."""


@dataclass
class WriterContext:
    target: Format
    template: ResolvedTemplate
    fields: ResolvedFields
    report: Report
    options: Options
    base_dir: Path | None
    work_dir: Path
    state: dict[str, Any] = field(default_factory=dict)
    generator: dict[str, Any] = field(default_factory=dict)
