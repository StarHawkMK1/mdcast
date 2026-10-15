from __future__ import annotations

import copy
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from mdcast.counters import parse_pattern
from mdcast.report import Codes, Report
from mdcast.units import (
    PAGE_SIZES_MM,
    normalize_color,
    page_size_mm,
    parse_length_mm,
    parse_pt,
    parse_ratio,
)

BUILTIN_DIR = Path(__file__).resolve().parent.parent / "builtin_templates"
DEFAULT_NAME = "default"
TEMPLATE_FILE = "template.yaml"

COLOR_KEYS = frozenset({"color", "background", "zebra"})
LENGTH_KEYS = frozenset({"space_before", "space_after", "indent_left", "cell_padding", "indent_per_level", "height"})
FONT_SIZE_KEYS = frozenset({"size", "font_size"})
RATIO_KEYS = frozenset({"line_height"})
BOOL_KEYS = frozenset({"bold", "italic", "keep_with_next", "repeat", "skip_first"})
# keys whose value may always be null (null means "unset"), whatever the default holds
NULLABLE_KEYS = frozenset({"color", "background", "zebra", "logo", "extends"})
ENUM_KEYS = {
    "align": {"left", "center", "right", "justify"},
    "valign": {"top", "middle", "bottom"},
}
ENUM_PATHS = {
    "page.orientation": {"portrait", "landscape"},
    "tables.width": {"full", "auto"},
    "tables.caption.position": {"above", "below"},
    "figures.caption.position": {"above", "below"},
    "header.source": {"yaml", "reference"},
    "footer.source": {"yaml", "reference"},
    "header.line": {"none", "below", "above"},
    "footer.line": {"none", "below", "above"},
    "header.logo.position": {"left", "center", "right"},
}
PATTERN_LISTS = ("lists.ordered", "headings.numbering")
STRING_LISTS = frozenset({"lists.bullet", "lists.ordered", "headings.numbering"})
PAGE_BREAK_LEVELS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
LOGO_REFERENCE: dict[str, Any] = {"file": "", "position": "left", "height": None}
MAX_LENGTH_MM = 2000.0
MAX_FONT_PT = 1000.0
MIN_CONTENT_MM = 10.0
_MISSING = object()


def load_yaml(path: Path, report: Report) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        report.warn(Codes.TEMPLATE_INVALID, f"template.yaml 을 읽을 수 없어 상위/내장 값을 씁니다: {exc}", template=str(path))
        return {}
    if data is None:
        return {}
    if not isinstance(data, dict):
        report.warn(Codes.TEMPLATE_INVALID, "template.yaml 최상위는 매핑이어야 합니다 — 내장 값을 씁니다", template=str(path))
        return {}
    return data


@lru_cache(maxsize=1)
def _builtin_default() -> dict[str, Any]:
    text = (BUILTIN_DIR / DEFAULT_NAME / TEMPLATE_FILE).read_text(encoding="utf-8")
    return yaml.safe_load(text)


def load_builtin_default() -> dict[str, Any]:
    return copy.deepcopy(_builtin_default())


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float)) and not isinstance(value, bool)


def _drop(report: Report, dotted: str, reason: str) -> None:
    report.warn(Codes.TEMPLATE_INVALID, f"템플릿 키 '{dotted}' {reason} — 무시합니다", key=dotted)


def _validate_logo(value: Any, report: Report, dotted: str) -> tuple[bool, Any]:
    if not isinstance(value, dict):
        _drop(report, dotted, "는 매핑(file, position, height)이어야 합니다")
        return False, None
    logo = validate_against(value, LOGO_REFERENCE, report, dotted)
    if not isinstance(logo.get("file"), str) or not logo["file"].strip():
        _drop(report, dotted, "에 file 이 없습니다")
        return False, None
    return True, logo


def _validate_list(key: str, dotted: str, value: Any, report: Report) -> tuple[bool, Any]:
    if not isinstance(value, list):
        _drop(report, dotted, "는 목록이어야 합니다")
        return False, None
    if not all(_is_scalar(item) for item in value):
        _drop(report, dotted, "의 항목 형식이 올바르지 않습니다")
        return False, None
    if dotted in STRING_LISTS or key == "fallback":
        return True, [str(item) for item in value]
    return True, list(value)


def validate_against(user: dict[str, Any], reference: dict[str, Any], report: Report, path: str = "") -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in user.items():
        key = str(key)
        dotted = f"{path}.{key}" if path else key
        if key not in reference:
            report.warn(Codes.TEMPLATE_INVALID, f"알 수 없는 템플릿 키 '{dotted}' 를 무시합니다", key=dotted)
            continue
        ref = reference[key]

        if value is None:
            if ref is None or key in NULLABLE_KEYS:
                clean[key] = None
            else:
                _drop(report, dotted, "는 비워 둘 수 없습니다")
            continue

        if dotted == "fields.defaults":
            if isinstance(value, dict):
                clean[key] = value
            else:
                _drop(report, dotted, "는 매핑이어야 합니다")
            continue

        if dotted == "tables.variants":
            if not isinstance(value, dict):
                _drop(report, dotted, "는 매핑이어야 합니다")
                continue
            variant_ref = {k: v for k, v in reference.items() if k != "variants"}
            variants: dict[str, Any] = {}
            for name, variant in value.items():
                sub = f"{dotted}.{name}"
                if not isinstance(variant, dict):
                    _drop(report, sub, "는 매핑이어야 합니다")
                    continue
                variants[str(name)] = validate_against(variant, variant_ref, report, sub)
            clean[key] = variants
            continue

        if key == "logo":
            ok, logo = _validate_logo(value, report, dotted)
            if ok:
                clean[key] = logo
            continue

        if isinstance(ref, dict):
            if not isinstance(value, dict):
                _drop(report, dotted, "는 매핑이어야 합니다")
                continue
            clean[key] = validate_against(value, ref, report, dotted)
            continue

        if isinstance(ref, list):
            ok, items = _validate_list(key, dotted, value, report)
            if ok:
                clean[key] = items
            continue

        if not _is_scalar(value) and not isinstance(value, bool):
            _drop(report, dotted, "의 값 형식이 올바르지 않습니다")
            continue
        if isinstance(ref, bool) or key in BOOL_KEYS:
            if not isinstance(value, bool):
                _drop(report, dotted, "는 true/false 여야 합니다")
                continue
            clean[key] = value
            continue
        if isinstance(value, bool):
            _drop(report, dotted, "의 값 형식이 올바르지 않습니다")
            continue
        if isinstance(ref, str) and not isinstance(value, str):
            clean[key] = str(value)
            continue
        clean[key] = value
    return clean


def _finite(number: float) -> float:
    if not math.isfinite(number):
        raise ValueError("유한한 숫자가 아닙니다")
    return number


def _check_length(value: Any) -> None:
    mm = _finite(parse_length_mm(value))
    if mm < 0 or mm > MAX_LENGTH_MM:
        raise ValueError(f"길이 범위를 벗어났습니다: {value!r}")


def _check_font_size(value: Any) -> None:
    pt = _finite(parse_pt(value))
    if pt <= 0 or pt > MAX_FONT_PT:
        raise ValueError(f"글자 크기 범위를 벗어났습니다: {value!r}")


def _check_ratio(value: Any) -> None:
    ratio = _finite(parse_ratio(value))
    if ratio <= 0 or ratio > 20:
        raise ValueError(f"비율 범위를 벗어났습니다: {value!r}")


def _check_max_width(value: Any) -> None:
    if isinstance(value, str) and value.strip().endswith("%"):
        ratio = _finite(parse_ratio(value))
        if ratio <= 0 or ratio > 1:
            raise ValueError(f"비율 범위를 벗어났습니다: {value!r}")
    else:
        _check_length(value)
        if parse_length_mm(value) <= 0:
            raise ValueError(f"길이 범위를 벗어났습니다: {value!r}")


def _allowed(values: set[str]) -> str:
    return "허용값: " + ", ".join(sorted(values))


def _problem(dotted: str, key: str, value: Any) -> str | None:
    if value is None:
        return None
    try:
        if dotted == "page.size":
            if str(value).upper() not in PAGE_SIZES_MM:
                return "허용값: " + ", ".join(PAGE_SIZES_MM)
        elif key in BOOL_KEYS:
            if not isinstance(value, bool):
                return "true/false 여야 합니다"
        elif key in COLOR_KEYS:
            normalize_color(value)
        elif key in FONT_SIZE_KEYS:
            _check_font_size(value)
        elif key in LENGTH_KEYS or dotted.startswith("page.margin.") or dotted.endswith(("border.width", "border_outer.width")):
            _check_length(value)
        elif key in RATIO_KEYS:
            _check_ratio(value)
        elif dotted == "figures.max_width":
            _check_max_width(value)
        elif dotted in ENUM_PATHS:
            if str(value) not in ENUM_PATHS[dotted]:
                return _allowed(ENUM_PATHS[dotted])
        elif key in ENUM_KEYS:
            if str(value) not in ENUM_KEYS[key]:
                return _allowed(ENUM_KEYS[key])
        elif dotted in PATTERN_LISTS:
            if not isinstance(value, list):
                return "목록이어야 합니다"
            if dotted == "lists.ordered" and not value:
                return "비어 있을 수 없습니다"
            for item in value:
                parse_pattern(str(item))
        elif dotted == "lists.bullet":
            if not isinstance(value, list) or not value or any(not str(item) for item in value):
                return "비어 있지 않은 목록이어야 합니다"
        elif dotted == "layout.page_break.before":
            if not isinstance(value, list) or any(str(item).lower() not in PAGE_BREAK_LEVELS for item in value):
                return "허용값: h1 ~ h6"
        elif key == "family" and dotted.startswith("fonts."):
            if not isinstance(value, str) or not value.strip():
                return "비어 있을 수 없습니다"
        elif key == "format" and dotted.endswith("caption.format"):
            str(value).format(n=1, text="x")
    except (ValueError, KeyError, IndexError, AttributeError, TypeError) as exc:
        return str(exc)
    return None


def _default_at(default: dict[str, Any], parts: list[str]) -> Any:
    node: Any = default
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _rule_path(parts: list[str]) -> str:
    """Variant entries are checked like the matching key under ``tables``."""
    if len(parts) >= 3 and parts[0] == "tables" and parts[1] == "variants":
        return ".".join(["tables", *parts[3:]])
    return ".".join(parts)


def _walk(node: dict[str, Any], path: list[str], default: dict[str, Any], report: Report) -> None:
    for key in list(node):
        value = node[key]
        parts = [*path, str(key)]
        dotted = ".".join(parts)
        if dotted == "fields.defaults":
            continue
        if isinstance(value, dict):
            _walk(value, parts, default, report)
            continue
        problem = _problem(_rule_path(parts), str(key), value)
        if problem is None:
            continue
        fallback = _default_at(default, parts)
        report.warn(
            Codes.TEMPLATE_INVALID,
            f"템플릿 값 {dotted}={value!r} 이(가) 올바르지 않아 기본값을 씁니다 ({problem})",
            key=dotted,
        )
        if fallback is _MISSING:
            del node[key]
        else:
            node[key] = copy.deepcopy(fallback)


def _check_margins(out: dict[str, Any], default: dict[str, Any], report: Report) -> None:
    page = out.get("page")
    if not isinstance(page, dict) or not isinstance(page.get("margin"), dict):
        return
    margin = page["margin"]
    try:
        width, height = page_size_mm(page.get("size", "A4"), page.get("orientation", "portrait"))
        left, right, top, bottom = (parse_length_mm(margin[k]) for k in ("left", "right", "top", "bottom"))
    except (KeyError, ValueError, TypeError):
        return
    if width - left - right >= MIN_CONTENT_MM and height - top - bottom >= MIN_CONTENT_MM:
        return
    fallback = _default_at(default, ["page", "margin"])
    report.warn(
        Codes.TEMPLATE_INVALID,
        "템플릿 여백이 용지보다 커서 기본 여백을 씁니다",
        key="page.margin",
    )
    if fallback is _MISSING:
        del page["margin"]
    else:
        page["margin"] = copy.deepcopy(fallback)


def sanitize(config: dict[str, Any], default: dict[str, Any], report: Report) -> dict[str, Any]:
    out = copy.deepcopy(config)
    _walk(out, [], default, report)
    _check_margins(out, default, report)
    return out
