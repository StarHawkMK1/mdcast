"""Generator facts written into every output (spec 2026-10-15 §5.6)."""

from __future__ import annotations

from typing import Any


def generator_values(generator: dict[str, Any]) -> dict[str, str]:
    template = generator.get("template") or {}
    mdcast = generator.get("generator")
    if not mdcast and generator.get("mdcast"):
        mdcast = f"mdcast {generator['mdcast']}"
    values = {
        "mdcast.generator": mdcast,
        "mdcast.template.name": template.get("name"),
        "mdcast.template.version": template.get("version"),
        "mdcast.template.source": template.get("source"),
        "mdcast.pandoc": generator.get("pandoc"),
        "mdcast.typst": generator.get("typst"),
    }
    return {k: str(v) for k, v in values.items() if v not in (None, "")}
