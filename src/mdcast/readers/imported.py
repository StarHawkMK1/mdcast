from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import panflute as pf

# the class of the hint spans an mdcast hwpx is read with (readers/hwpx), taken out by filters/importing/mdcast_doc (R17)
HINT_CLASS = "mdcast-hwpx"


@dataclass
class ImportedDocument:
    doc: pf.Doc
    source_text: list[str]
    frontmatter: dict[str, Any]
    media: dict[str, bytes]
    generator: dict[str, str]
    table_styles: list[str | None] = field(default_factory=list)
