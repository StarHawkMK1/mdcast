"""Pictures on a PDF page: where they are and what they look like, drawn as PNG (D2)."""

from __future__ import annotations

import io

import pdfplumber

from mdcast.readers.pdf.model import Box

RESOLUTION = 150  # dpi
SMALL_PT = 20.0  # a picture shorter than this both ways is decoration


def image_boxes(page: pdfplumber.page.Page) -> list[Box]:
    """The boxes of ``page.images``, cut down to the page's box; a box with nothing left is dropped.

    A picture may run off the page (Review Focus 3); drawing reaches only what is on it.
    """
    x0, top, x1, bottom = page.bbox
    boxes = [
        Box(max(im["x0"], x0), max(im["top"], top), min(im["x1"], x1), min(im["bottom"], bottom))
        for im in page.images
    ]
    return [box for box in boxes if box.width > 0 and box.height > 0]


def is_small(box: Box) -> bool:
    return box.width < SMALL_PT and box.height < SMALL_PT


def render(page: pdfplumber.page.Page, box: Box) -> bytes:
    """The PNG of what ``box`` on ``page`` shows, text drawn over the picture included.

    The full-colour image is saved, not ``PageImage.save``'s 256-colour one.
    """
    image = page.crop((box.x0, box.top, box.x1, box.bottom)).to_image(resolution=RESOLUTION)
    out = io.BytesIO()
    image.original.save(out, format="PNG")
    return out.getvalue()
