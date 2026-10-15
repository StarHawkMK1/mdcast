from __future__ import annotations

import re
import tempfile
from pathlib import Path

FONT_ALIASES = {
    "맑은 고딕": "Malgun Gothic",
    "굴림": "Gulim",
    "굴림체": "GulimChe",
    "돋움": "Dotum",
    "돋움체": "DotumChe",
    "바탕": "Batang",
    "바탕체": "BatangChe",
    "궁서": "Gungsuh",
    "나눔고딕": "NanumGothic",
    "나눔명조": "NanumMyeongjo",
    "함초롬바탕": "HCR Batang",
    "함초롬돋움": "HCR Dotum",
}
BUNDLED_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
BUNDLED_FALLBACK = "Noto Sans KR"
_UNKNOWN = re.compile(r"^unknown font family:\s*(.+?)\s*$", re.IGNORECASE)


def latin_name(family: str) -> str:
    name = family.strip()
    return FONT_ALIASES.get(name, name)


def family_chain(font_cfg: dict) -> list[str]:
    names = [font_cfg.get("family"), *(font_cfg.get("fallback") or [])]
    chain: list[str] = []
    for name in names:
        if not name:
            continue
        latin = latin_name(str(name))
        if latin not in chain:
            chain.append(latin)
    if BUNDLED_FALLBACK not in chain:
        chain.append(BUNDLED_FALLBACK)
    return chain


def unknown_font_name(message: str) -> str | None:
    match = _UNKNOWN.match(message.strip())
    return match.group(1).lower() if match else None


def font_paths() -> list[str]:
    return [str(BUNDLED_FONT_DIR)] if BUNDLED_FONT_DIR.is_dir() else []


def missing_primary_fonts(fonts_cfg: dict) -> list[str]:
    import typst

    missing: list[str] = []
    with tempfile.TemporaryDirectory(prefix="mdcast-fontprobe-") as tmp:
        for role, font in fonts_cfg.items():
            family = (font or {}).get("family")
            if not family or family in missing:
                continue
            latin = latin_name(str(family)).replace('"', "")
            src = Path(tmp) / f"{role}.typ"
            src.write_text(f'#set text(font: "{latin}")\n가', encoding="utf-8")
            _, warnings = typst.compile_with_warnings(str(src), root=tmp, font_paths=font_paths())
            if any(unknown_font_name(w.message) == latin.lower() for w in warnings):
                missing.append(str(family))
    return missing
