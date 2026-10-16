from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mdcast.report import Codes, Report, TemplateInfo
from mdcast.templates.schema import (
    BUILTIN_DIR,
    DEFAULT_NAME,
    TEMPLATE_FILE,
    deep_merge,
    load_builtin_default,
    load_yaml,
    sanitize,
    validate_against,
)

FORMATS = ("docx", "hwpx", "pdf")
DEFAULT_FILES = {"docx": "reference.docx", "hwpx": "reference.hwpx", "pdf": "pdf.typ"}
METADATA_KEYS = frozenset({"schema", "name", "version", "description", "extends", "files"})


@dataclass(frozen=True)
class Container:
    path: Path | None
    source: str


@dataclass(frozen=True)
class TemplateEntry:
    name: str
    origin: str
    path: Path


@dataclass
class ResolvedTemplate:
    name: str
    version: str
    source: str
    location: Path | None
    config: dict[str, Any]
    containers: dict[str, Container]
    # values the user/parent yaml actually set (sanitized); the built-in default's own are excluded
    explicit: dict[str, Any] = field(default_factory=dict)

    def container_for(self, fmt: str) -> Container:
        return self.containers.get(fmt, Container(None, "builtin"))

    def builtin_container(self, fmt: str) -> Container:
        """The built-in container for ``fmt``; ``path=None`` means the engine's own default."""
        if fmt in ("pdf", "hwpx"):
            return Container(BUILTIN_DIR / DEFAULT_NAME / DEFAULT_FILES[fmt], "builtin")
        return Container(None, "builtin")

    def info(self, formats: Iterable[str]) -> TemplateInfo:
        per_format = {
            fmt: {"container": self.container_for(fmt).source, "styles": self.source}
            for fmt in formats
        }
        location = str(self.location) if self.location else None
        return TemplateInfo(self.name, self.version, self.source, location, per_format)

    def note_container_fallbacks(self, fmt: str, report: Report) -> None:
        if self.source != "custom" or fmt == "pdf":
            return
        if self.container_for(fmt).source == "custom":
            return
        message = (
            f"커스텀 템플릿에 {fmt} 기준 문서가 없어 내장 그릇을 사용합니다 "
            "(모양 설정은 커스텀 값 적용)"
        )
        sources = (
            (self.config.get("header") or {}).get("source"),
            (self.config.get("footer") or {}).get("source"),
        )
        if "reference" in sources:
            report.warn(
                Codes.TEMPLATE_CONTAINER_FALLBACK,
                message + " — 기준 문서의 머리말/꼬리말은 적용되지 않습니다",
                format=fmt,
            )
        else:
            report.info(Codes.TEMPLATE_CONTAINER_FALLBACK, message, format=fmt)


def _roots(cwd: Path, home: Path) -> list[tuple[str, Path]]:
    return [
        ("project", cwd / ".mdcast" / "templates"),
        ("user", home / ".mdcast" / "templates"),
        ("builtin", BUILTIN_DIR),
    ]


def looks_like_path(ref: str) -> bool:
    return "/" in ref or "\\" in ref or ref.startswith(".") or Path(ref).is_absolute()


def find_template_dir(ref: str, cwd: Path, home: Path) -> tuple[Path, str] | None:
    if looks_like_path(ref):
        candidate = Path(ref)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        return (candidate, "path") if (candidate / TEMPLATE_FILE).is_file() else None
    for origin, root in _roots(cwd, home):
        candidate = root / ref
        if (candidate / TEMPLATE_FILE).is_file():
            return candidate, origin
    return None


def list_templates(cwd: Path, home: Path) -> list[TemplateEntry]:
    entries: list[TemplateEntry] = []
    for origin, root in _roots(cwd, home):
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if (child / TEMPLATE_FILE).is_file():
                entries.append(TemplateEntry(child.name, origin, child))
    return entries


def _same(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve()


def _container(fmt: str, config: dict[str, Any], dirs: list[tuple[Path, str]]) -> Container:
    filename = (config.get("files") or {}).get(fmt) or DEFAULT_FILES[fmt]
    for directory, source in dirs:
        candidate = directory / filename
        if candidate.is_file():
            return Container(candidate, source)
        fallback = directory / DEFAULT_FILES[fmt]
        if fallback.is_file():
            return Container(fallback, source)
    return Container(None, "builtin")


def _explicit_values(
    user: dict[str, Any], parent: dict[str, Any], final: dict[str, Any]
) -> dict[str, Any]:
    """Keys whose final value really came from the child or parent yaml.

    A leaf counts only if the sanitized ``final`` value equals what the child or the parent
    wrote; a value sanitize replaced with the built-in default is not explicit.
    """
    out: dict[str, Any] = {}
    for key in [*user, *(k for k in parent if k not in user)]:
        if key not in final:
            continue
        u, p = user.get(key), parent.get(key)
        if isinstance(final[key], dict) and (isinstance(u, dict) or isinstance(p, dict)):
            nested = _explicit_values(
                u if isinstance(u, dict) else {}, p if isinstance(p, dict) else {}, final[key]
            )
            if nested or u == {} or p == {}:
                out[key] = nested
        elif (key in user and final[key] == u) or (key in parent and final[key] == p):
            out[key] = final[key]
    return out


def resolve_template(
    ref: str | None, *, cwd: Path, home: Path, report: Report
) -> ResolvedTemplate:
    default_dir = BUILTIN_DIR / DEFAULT_NAME
    default_cfg = load_builtin_default()
    wanted = ref or DEFAULT_NAME
    found = find_template_dir(wanted, cwd, home)
    if found is None:
        if ref:
            report.warn(
                Codes.TEMPLATE_NOT_FOUND,
                f"템플릿 '{ref}' 을(를) 찾지 못해 내장 default 템플릿을 사용합니다",
                template=ref,
            )
        found = (default_dir, "builtin")
    tdir, origin = found
    source = "builtin" if origin == "builtin" else "custom"
    is_default = _same(tdir, default_dir)

    user_cfg: dict[str, Any] = {}
    if not is_default:
        user_cfg = validate_against(load_yaml(tdir / TEMPLATE_FILE, report), default_cfg, report)
    if user_cfg.get("schema") not in (None, 1):
        report.warn(
            Codes.TEMPLATE_INVALID,
            f"지원하지 않는 schema 버전 {user_cfg.get('schema')!r} — 1 로 간주합니다",
        )

    parent_cfg: dict[str, Any] = {}
    parent_dir: Path | None = None
    parent_ref = user_cfg.get("extends")
    if parent_ref and parent_ref != DEFAULT_NAME:
        parent = find_template_dir(str(parent_ref), cwd, home)
        if parent is None:
            report.warn(
                Codes.TEMPLATE_NOT_FOUND,
                f"상위 템플릿 '{parent_ref}' 을(를) 찾지 못해 내장 default 를 상위로 씁니다",
                template=str(parent_ref),
            )
        elif _same(parent[0], tdir):
            report.warn(
                Codes.TEMPLATE_INVALID, "템플릿이 자기 자신을 상속합니다 — extends 를 무시합니다"
            )
        elif not _same(parent[0], default_dir):
            parent_dir = parent[0]
            parent_cfg = validate_against(
                load_yaml(parent_dir / TEMPLATE_FILE, report), default_cfg, report
            )
            if parent_cfg.get("extends") not in (None, DEFAULT_NAME):
                report.warn(
                    Codes.TEMPLATE_INVALID,
                    f"다단계 상속은 지원하지 않아 '{parent_ref}' 의 extends 를 무시합니다",
                )
            parent_cfg.pop("extends", None)

    # invalid child values fall back to the parent's value, invalid parent values to the default
    parent_clean = sanitize(deep_merge(default_cfg, parent_cfg), default_cfg, report)
    config = sanitize(deep_merge(parent_clean, user_cfg), parent_clean, report)

    explicit = _explicit_values(user_cfg, parent_cfg, config)
    for key in METADATA_KEYS:
        explicit.pop(key, None)

    dirs: list[tuple[Path, str]] = []
    if not is_default:
        dirs.append((tdir, source))
    if parent_dir is not None:
        dirs.append((parent_dir, source))
    dirs.append((default_dir, "builtin"))
    containers = {fmt: _container(fmt, config, dirs) for fmt in FORMATS}

    if is_default:
        name, version = DEFAULT_NAME, str(default_cfg.get("version"))
    else:
        name = str(user_cfg.get("name") or tdir.name)
        version = str(user_cfg.get("version") or parent_cfg.get("version") or "0.0.0")
    location = tdir if source == "custom" else None
    return ResolvedTemplate(name, version, source, location, config, containers, explicit)
