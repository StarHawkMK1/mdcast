"""Input values of the hwpx writer (spec §4.3) and its notices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

ELEMENTS = ("body", "quote", "code", "caption", "footnote", *(f"heading{i}" for i in range(1, 7)))


@dataclass(frozen=True)
class Look:
    """One element's look. ``None`` keeps the container's value."""

    font: str | None = None
    font_hangul: str | None = None  # face for Hangul text when ``font`` has none (code)
    size: float | None = None  # pt
    bold: bool | None = None
    italic: bool | None = None
    color: str | None = None  # "#RRGGBB"
    align: str | None = None  # left | center | right | justify
    line_height: float | None = None  # ratio of the font size, 1.8 = 180%
    space_before: float | None = None  # pt
    space_after: float | None = None  # pt
    indent_left: float | None = None  # mm
    background: str | None = None  # "#RRGGBB"
    keep_with_next: bool | None = None


@dataclass(frozen=True)
class PageNumber:
    kind: str  # "page" | "pages"


Piece = str | PageNumber


@dataclass(frozen=True)
class Slots:
    left: tuple[Piece, ...] = ()
    center: tuple[Piece, ...] = ()
    right: tuple[Piece, ...] = ()
    line: str = "none"  # below | above | none


@dataclass(frozen=True)
class PageSetup:
    """Paper (portrait dimensions) and margins in mm; ``None`` keeps the container's value."""

    width: float | None = None
    height: float | None = None
    landscape: bool | None = None
    top: float | None = None
    bottom: float | None = None
    left: float | None = None
    right: float | None = None


@dataclass(frozen=True)
class Border:
    width: float = 0.5  # pt
    color: str = "#000000"


@dataclass(frozen=True)
class TableLook:
    """One table kind (spec 2026-10-20 §4.4); header bold/alignment come from the tables filter."""

    width: str = "full"  # full | auto
    font_size: float | None = None  # pt; None: the body size
    line_height: float | None = None  # ratio
    padding: float = 1.5  # mm, every side of every cell
    border: Border = Border(0.5)
    border_outer: Border = Border(1.0)
    header_background: str | None = None
    header_valign: str = "middle"  # top | middle | bottom
    header_repeat: bool = True
    body_valign: str = "middle"
    zebra: str | None = None
    first_column_background: str | None = None


@dataclass(frozen=True)
class Image:
    data: bytes
    ext: str  # png | jpg | gif | bmp | svg
    width_px: int
    height_px: int
    dpi: float = 96.0


@dataclass(frozen=True)
class Metadata:
    title: str = ""
    author: str = ""
    keywords: str = ""
    created: str = ""  # UTC "YYYY-MM-DDThh:mm:ssZ"
    extra: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Notice:
    kind: str  # "degraded" | "style-missing"
    element: str
    message: str


class Notices:
    """Notices, at most one per kind and element (spec §5.6: once per document)."""

    def __init__(self) -> None:
        self.items: list[Notice] = []
        self._seen: set[tuple[str, str]] = set()

    def add(self, kind: str, element: str, message: str) -> None:
        if (kind, element) not in self._seen:
            self._seen.add((kind, element))
            self.items.append(Notice(kind, element, message))


@dataclass
class Settings:
    looks: dict[str, Look] = field(default_factory=dict)
    styles: dict[str, str] = field(default_factory=dict)  # element -> container style name
    page: PageSetup = field(default_factory=PageSetup)
    header: Slots | None = None  # None: keep the container's header (source: reference)
    footer: Slots | None = None
    fill: Callable[[str], list[Piece]] = lambda text: [text]  # "{{key}}" text in kept headers
    list_marker: Callable[[bool, int, int], str] = lambda ordered, level, n: f"{n}." if ordered else "-"
    list_indent: float = 5.0  # mm per list level
    body_size: float = 11.0  # pt: list hanging indents, header placement
    body_line_height: float = 1.3
    table_caption_above: bool = True
    figure_caption_above: bool = False
    metadata: Metadata = field(default_factory=Metadata)
    tables: dict[str | None, TableLook] = field(default_factory=lambda: {None: TableLook()})
    images: dict[str, Image] = field(default_factory=dict)  # image url -> picture
    figure_max_ratio: float | None = 1.0  # of the available width (figures.max_width as %)
    figure_max_mm: float | None = None  # figures.max_width as a length
    figure_align: str = "center"
