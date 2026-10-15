from __future__ import annotations

from dataclasses import dataclass

_SEQUENCES = {
    "가": "가나다라마바사아자차카타파하",
    "ㄱ": "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ",
    "①": "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳",
    "Ⅰ": "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ",
    "ⅰ": "ⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹⅺⅻ",
}
_TOKENS = ("1", "Ⅰ", "ⅰ", "I", "i", "A", "a", "가", "ㄱ", "①")
_WORD_NUMFMT = {
    "1": "decimal",
    "Ⅰ": "upperRoman",
    "I": "upperRoman",
    "ⅰ": "lowerRoman",
    "i": "lowerRoman",
    "A": "upperLetter",
    "a": "lowerLetter",
    "가": "ganada",
    "ㄱ": "chosung",
    "①": "decimalEnclosedCircle",
}
_TYPST_TOKEN = {"Ⅰ": "I", "ⅰ": "i"}
_ROMAN = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
    (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]


@dataclass(frozen=True)
class Pattern:
    prefix: str
    token: str
    suffix: str


def parse_pattern(pattern: str) -> Pattern:
    for index, ch in enumerate(pattern):
        if ch in _TOKENS:
            return Pattern(pattern[:index], ch, pattern[index + 1 :])
    raise ValueError(f"번호 패턴에 번호 기호(1, Ⅰ, 가, ㄱ, ①, a, i …)가 없습니다: {pattern!r}")


def _roman(n: int) -> str:
    out = []
    for value, symbol in _ROMAN:
        while n >= value:
            out.append(symbol)
            n -= value
    return "".join(out)


def _letters(n: int) -> str:
    out = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def format_counter(pattern: str | Pattern, n: int) -> str:
    p = parse_pattern(pattern) if isinstance(pattern, str) else pattern
    t = p.token
    if t == "1":
        body = str(n)
    elif t in ("I", "i"):
        body = _roman(n) if t == "I" else _roman(n).lower()
    elif t in ("A", "a"):
        body = _letters(n) if t == "A" else _letters(n).lower()
    else:
        seq = _SEQUENCES[t]
        body = seq[n - 1] if 1 <= n <= len(seq) else str(n)
    return f"{p.prefix}{body}{p.suffix}"


def word_level(pattern: str, level_index: int) -> tuple[str, str]:
    p = parse_pattern(pattern)
    return _WORD_NUMFMT[p.token], f"{p.prefix}%{level_index + 1}{p.suffix}"


def typst_pattern(pattern: str) -> str:
    p = parse_pattern(pattern)
    return f"{p.prefix}{_TYPST_TOKEN.get(p.token, p.token)}{p.suffix}"
