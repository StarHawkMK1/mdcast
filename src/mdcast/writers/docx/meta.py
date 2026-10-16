from __future__ import annotations

import json
from typing import Any

from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from lxml import etree

from mdcast.fields import ResolvedFields
from mdcast.report import Codes, Report
from mdcast.writers.generator import generator_values

CUSTOM_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.custom-properties+xml"
_NS_CP = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
_NS_VT = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
_FMTID = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"


def _parse(blob: bytes):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    root = etree.fromstring(blob, parser)
    info = root.getroottree().docinfo
    if info.doctype or info.internalDTD is not None or next(root.iter(etree.Entity), None) is not None:
        raise etree.XMLSyntaxError("DOCTYPE or entity reference in custom properties", 0, 0, 0)
    if root.tag != f"{{{_NS_CP}}}Properties":
        raise etree.XMLSyntaxError("not a custom-properties part", 0, 0, 0)
    return root


def _merge_custom(blob: bytes | None, values: dict[str, str]) -> bytes:
    root = _parse(blob) if blob else None
    if root is None:
        root = etree.Element(f"{{{_NS_CP}}}Properties", nsmap={None: _NS_CP, "vt": _NS_VT})
    props = root.findall(f"{{{_NS_CP}}}property")
    for prop in list(props):
        if prop.get("name") in values:
            root.remove(prop)
    pids = [int(p.get("pid", 0)) for p in root.findall(f"{{{_NS_CP}}}property")]
    pid = max([1, *pids])
    for name, value in values.items():
        pid += 1
        prop = etree.SubElement(root, f"{{{_NS_CP}}}property", fmtid=_FMTID, pid=str(pid), name=name)
        etree.SubElement(prop, f"{{{_NS_VT}}}lpwstr").text = value
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _write_custom_properties(d, values: dict[str, str], report: Report | None) -> None:
    if not values:
        return
    package = d.part.package
    for rel in package.rels.values():
        if rel.reltype == RT.CUSTOM_PROPERTIES and not rel.is_external:
            try:
                _parse(rel.target_part.blob)
            except etree.XMLSyntaxError as exc:
                if report is not None:
                    report.warn(
                        Codes.TEMPLATE_INVALID,
                        f"기준 문서의 사용자 지정 속성(custom.xml)을 읽을 수 없어 새로 만듭니다: {exc}",
                        format="docx",
                    )
                rel.target_part._blob = _merge_custom(None, values)
                return
            rel.target_part._blob = _merge_custom(rel.target_part.blob, values)
            return
    part = Part(PackURI("/docProps/custom.xml"), CUSTOM_CONTENT_TYPE, _merge_custom(None, values), package)
    package.relate_to(part, RT.CUSTOM_PROPERTIES)


def apply_metadata(d, generator: dict[str, Any], fields: ResolvedFields, report: Report | None = None) -> None:
    props = d.core_properties
    props.comments = json.dumps(generator, ensure_ascii=False)
    props.keywords = "mdcast"
    title = fields.values.get("title")
    if title:
        props.title = title
    author = fields.values.get("author")
    if author:
        props.author = author
    _write_custom_properties(d, generator_values(generator), report)
