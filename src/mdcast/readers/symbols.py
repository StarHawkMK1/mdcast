"""Symbol-font characters (Wingdings, Symbol) to the visible symbols they stand for.

A document written in a symbol font stores its glyphs as Private Use Area characters
(``U+F020``–``U+F0FF``: the font's byte plus ``0xF000``). Without the font they show as nothing or
as a box, so an agent reads a broken character where the writer saw a bullet. The table holds the
common bullet glyphs only; it cannot tell which font a character came from, so where Wingdings and
Symbol disagree on a code it follows the bullet the plan names.
"""

from __future__ import annotations

# checked against the glyphs of Windows' wingding.ttf and symbol.ttf
SYMBOLS: dict[str, str] = {
    "\uf0a7": "\u25aa",  # Wingdings 0xA7 small black square ▪
    "\uf0b7": "\u2022",  # Symbol 0xB7 bullet •
    "\uf06c": "\u25cf",  # Wingdings 0x6C black circle ●
    "\uf0a8": "\u25c6",  # Symbol 0xA8 diamond ◆ (the plan's choice; Wingdings draws a white square)
    "\uf076": "\u2756",  # Wingdings 0x76 black diamond minus white X ❖ (Word's bullet library)
    "\uf0d8": "\u27a2",  # Wingdings 0xD8 arrowhead ➢ (Word's bullet library)
    "\uf0fc": "\u2713",  # Wingdings 0xFC check mark ✓ (Word's bullet library)
}

_PUA_FIRST, _PUA_LAST = 0xE000, 0xF8FF


def map_symbols(text: str) -> tuple[str, int, int]:
    """``text`` with the table's characters replaced; how many were replaced, how many PUA ones left."""
    mapped = left = 0
    out: list[str] = []
    for ch in text:
        symbol = SYMBOLS.get(ch)
        if symbol is not None:
            mapped += 1
            out.append(symbol)
        else:
            left += _PUA_FIRST <= ord(ch) <= _PUA_LAST
            out.append(ch)
    return ("".join(out), mapped, left) if mapped else (text, 0, left)
