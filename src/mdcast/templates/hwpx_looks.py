"""Which template values an hwpx is written with: shared by the hwpx writer and the mdcast hwpx import.

The writer sets code, a code block and a block quote apart only by these values (no named
style), so reading an mdcast hwpx back has to derive them exactly the same way (R17).
"""

from __future__ import annotations

from typing import Any

from mdcast.templates.resolve import ResolvedTemplate
from mdcast.units import normalize_color


def custom_container(template: ResolvedTemplate) -> bool:
    """The hwpx is written into the template's own ``reference.hwpx``."""
    container = template.container_for("hwpx")
    return container.source == "custom" and container.path is not None


def look_values(template: ResolvedTemplate, custom: bool) -> dict[str, Any]:
    """The values element looks come from: only what the template wrote itself in a custom
    container (the rest is the container's own shapes), the full config otherwise."""
    return template.explicit if custom else template.config


def role(element: str) -> str:
    """The ``fonts`` entry an element takes its face from."""
    if element.startswith("heading"):
        return "heading"
    return "code" if element == "code" else "body"


def hex_color(value: Any) -> str | None:
    """A template colour as hwpx writes it: ``#RRGGBB``, upper case (``f6f8fa``, ``#555`` too)."""
    color = normalize_color(value)
    return None if color is None else f"#{color}"


def family(values: dict[str, Any], element: str) -> str | None:
    """The face an element is written in, or None (a custom container's own)."""
    name = ((values.get("fonts") or {}).get(role(element)) or {}).get("family")
    return str(name) if name else None
