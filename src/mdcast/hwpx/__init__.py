"""Standalone OWPML (hwpx) writer: pandoc AST in, hwpx bytes out.

Imports nothing from mdcast outside this package (spec 2026-10-15 §2).
"""

from mdcast.hwpx.container import ContainerError, Package
from mdcast.hwpx.header import Header
from mdcast.hwpx.look import (
    ELEMENTS,
    Border,
    Image,
    Look,
    Metadata,
    Notice,
    PageNumber,
    PageSetup,
    Piece,
    Settings,
    Slots,
    TableLook,
)
from mdcast.hwpx.writer import write

__all__ = [
    "ELEMENTS",
    "Border",
    "ContainerError",
    "Header",
    "Image",
    "Look",
    "Metadata",
    "Notice",
    "Package",
    "PageNumber",
    "PageSetup",
    "Piece",
    "Settings",
    "Slots",
    "TableLook",
    "write",
]
