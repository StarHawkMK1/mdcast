"""Each element's style, paragraph shape and character shape (spec §5.1)."""

from __future__ import annotations

from dataclasses import dataclass

from mdcast.hwpx.header import CharSpec, Header, ParaSpec
from mdcast.hwpx.look import ELEMENTS, Look, Notices, Settings

PADDING = 2.0  # mm around a paragraph background, as the PDF code block's inset (spec §5.4)


@dataclass(frozen=True)
class Shape:
    style: str
    para: str
    char: str
    look: Look


def char_spec(look: Look) -> CharSpec:
    return CharSpec(font=look.font, font_hangul=look.font_hangul, size=look.size, color=look.color,
                    bold=look.bold, italic=look.italic)


def para_spec(header: Header, look: Look) -> ParaSpec:
    left, right, prev, after = look.indent_left, None, look.space_before, look.space_after
    fill = offsets = connect = None
    if look.background:
        # the PDF block's inset: text 2mm inside the background, neighbours pushed 2mm away
        pad_pt = PADDING * 72 / 25.4
        fill = header.add_border_fill(fill=look.background)
        left, right = (look.indent_left or 0.0) + PADDING, PADDING
        prev, after = (look.space_before or 0.0) + pad_pt, (look.space_after or 0.0) + pad_pt
        # Hangul's background box already holds the paragraph's margins and gaps (visual check)
        offsets, connect = (0.0, 0.0, 0.0, 0.0), False
    return ParaSpec(
        align=look.align, line_height=look.line_height, prev=prev, next=after, left=left, right=right,
        keep_with_next=look.keep_with_next, border_fill=fill, offsets=offsets, connect=connect,
    )


def build_shapes(header: Header, settings: Settings, notices: Notices) -> dict[str, Shape]:
    shapes: dict[str, Shape] = {}
    for element in ELEMENTS:
        look = settings.looks.get(element) or Look()
        name = settings.styles.get(element)
        style_id = header.style_id(name) if name else None
        if style_id is None:
            if name:
                notices.add(
                    "style-missing", element,
                    f"hwpx 기준 문서에 스타일 '{name}' 이(가) 없어 첫 스타일(바탕글)을 씁니다",
                )
            style_id = header.first_style_id()
        style = header.style(style_id)
        para = header.add_para(style.get("paraPrIDRef", "0"), para_spec(header, look))
        char = header.add_char(style.get("charPrIDRef", "0"), char_spec(look))
        shapes[element] = Shape(style_id, para, char, look)
    return shapes
