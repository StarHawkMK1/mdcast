"""hwpx (zip) package: read, edit parts, write with ``mimetype`` first and stored."""

from __future__ import annotations

import io
import zipfile

from lxml import etree

REQUIRED = ("mimetype", "Contents/header.xml", "Contents/section0.xml", "Contents/content.hpf")
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
_EPOCH = (1980, 1, 1, 0, 0, 0)
_UNREADABLE = (zipfile.BadZipFile, OSError, ValueError, RuntimeError, NotImplementedError, EOFError)


class ContainerError(Exception):
    """The container is not a usable hwpx."""


class Package:
    def __init__(self, entries: list[tuple[str, bytes, int]]) -> None:
        self._entries = entries

    @classmethod
    def read(cls, data: bytes) -> Package:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = [
                    (info.filename, archive.read(info), info.compress_type)
                    for info in archive.infolist()
                    if not info.is_dir()
                ]
        except _UNREADABLE as exc:
            raise ContainerError(f"hwpx(zip) 로 읽을 수 없습니다: {exc}") from exc
        package = cls(entries)
        missing = [name for name in REQUIRED if name not in package.names()]
        if missing:
            raise ContainerError(f"hwpx 에 필요한 파일이 없습니다: {', '.join(missing)}")
        for name in REQUIRED[1:]:
            package.xml(name)
        return package

    def names(self) -> list[str]:
        return [name for name, _, _ in self._entries]

    def get(self, name: str) -> bytes:
        for entry, data, _ in self._entries:
            if entry == name:
                return data
        raise KeyError(name)

    def set(self, name: str, data: bytes) -> None:
        for index, (entry, _, compress) in enumerate(self._entries):
            if entry == name:
                self._entries[index] = (name, data, compress)
                return
        self._entries.append((name, data, zipfile.ZIP_DEFLATED))

    def remove(self, name: str) -> None:
        self._entries = [entry for entry in self._entries if entry[0] != name]

    def xml(self, name: str) -> etree._Element:
        try:
            root = etree.fromstring(self.get(name), _PARSER)
        except etree.XMLSyntaxError as exc:
            raise ContainerError(f"{name} 의 XML 이 올바르지 않습니다: {exc}") from exc
        if root.getroottree().docinfo.internalDTD is not None:
            raise ContainerError(f"{name} 에 DTD 가 들어 있습니다")
        return root

    def set_xml(self, name: str, root: etree._Element) -> None:
        self.set(name, etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))

    def write(self) -> bytes:
        ordered = sorted(self._entries, key=lambda entry: entry[0] != "mimetype")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, data, compress in ordered:
                info = zipfile.ZipInfo(name, date_time=_EPOCH)
                info.compress_type = zipfile.ZIP_STORED if name == "mimetype" else compress
                archive.writestr(info, data)
        return buffer.getvalue()
