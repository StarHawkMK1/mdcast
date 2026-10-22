"""What the pdf reader works with: boxes on a page and the text lines read off it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Box:
    """A rectangle in pdfplumber coordinates (points, the top of the page is 0)."""

    x0: float
    top: float
    x1: float
    bottom: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.top <= y <= self.bottom


@dataclass(frozen=True)
class Run:
    text: str
    bold: bool


@dataclass
class Line:
    page: int  # from 0
    box: Box
    size: float  # the font size most of its characters have
    runs: list[Run]  # neighbouring characters of the same boldness are one run; words split by " "

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)

    @property
    def bold(self) -> bool:
        """Every character that is not a space is bold."""
        return all(run.bold for run in self.runs if run.text.strip())
