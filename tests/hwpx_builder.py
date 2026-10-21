"""Build small hwpx packages for reader tests.

Header ids are fixed (every hwpx reader test relies on them):

- charPr: "0" plain, "1" bold, "2" italic, "3" superscript, "4" subscript, "5" strikeout.
- paraPr: "0" none, "1" OUTLINE 0, "2" OUTLINE 1, "3" NUMBER 0 (numbering "1", start 1),
  "4" NUMBER 1 (numbering "1"), "5" BULLET 0 (bullet "1"), "6" NUMBER 0 (numbering "2", start 3).
"""

from __future__ import annotations

import io
import mimetypes
import zipfile
from pathlib import PurePosixPath
from xml.sax.saxutils import escape, quoteattr

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS = "http://www.hancom.co.kr/hwpml/2011/section"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
OPF = "http://www.idpf.org/2007/opf/"
ODF = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
_NS = f'xmlns:hp="{HP}" xmlns:hs="{HS}" xmlns:hh="{HH}" xmlns:hc="{HC}"'
_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'

# Hancom writes strikeout shape="3D" on characters that are not struck through.
_NO_STRIKE = '<hh:strikeout shape="3D" color="#000000"/>'
_CHAR_FLAGS = {
    "0": _NO_STRIKE,
    "1": "<hh:bold/>" + _NO_STRIKE,
    "2": "<hh:italic/>" + _NO_STRIKE,
    "3": _NO_STRIKE + "<hh:supscript/>",
    "4": _NO_STRIKE + "<hh:subscript/>",
    "5": '<hh:strikeout shape="SOLID" color="#000000"/>',
}
_PARA_HEADINGS = {
    "0": ("NONE", "0", "0"),
    "1": ("OUTLINE", "0", "0"),
    "2": ("OUTLINE", "0", "1"),
    "3": ("NUMBER", "1", "0"),
    "4": ("NUMBER", "1", "1"),
    "5": ("BULLET", "1", "0"),
    "6": ("NUMBER", "2", "0"),
}
_NUMBERING_STARTS = {"1": 1, "2": 3}


def _char_pr(cid: str, flags: str) -> str:
    return (
        f'<hh:charPr id="{cid}" height="1000" textColor="#000000" shadeColor="none" useFontSpace="0" '
        f'useKerning="0" symMark="NONE" borderFillIDRef="1">'
        '<hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
        f"{flags}</hh:charPr>"
    )


def _para_pr(pid: str, kind: str, ref: str, level: str) -> str:
    return (
        f'<hh:paraPr id="{pid}" tabPrIDRef="0" condense="0"><hh:align horizontal="JUSTIFY" vertical="BASELINE"/>'
        f'<hh:heading type="{kind}" idRef="{ref}" level="{level}"/></hh:paraPr>'
    )


def _para_heads(start: int) -> str:
    return "".join(
        f'<hh:paraHead start="{start if level == 1 else 1}" level="{level}" align="LEFT" numFormat="DIGIT">^{level}.</hh:paraHead>'
        for level in range(1, 4)
    )


def _header() -> str:
    chars = "".join(_char_pr(cid, flags) for cid, flags in _CHAR_FLAGS.items())
    paras = "".join(_para_pr(pid, *heading) for pid, heading in _PARA_HEADINGS.items())
    numberings = "".join(
        f'<hh:numbering id="{nid}" start="0">{_para_heads(start)}</hh:numbering>'
        for nid, start in _NUMBERING_STARTS.items()
    )
    bullets = '<hh:bullet id="1" char="•" useImage="0"><hh:paraHead level="0" align="LEFT" numFormat="DIGIT"/></hh:bullet>'
    return (
        f'{_DECL}<hh:head {_NS} version="1.3" secCnt="1"><hh:refList>'
        f'<hh:charProperties itemCnt="{len(_CHAR_FLAGS)}">{chars}</hh:charProperties>'
        f'<hh:paraProperties itemCnt="{len(_PARA_HEADINGS)}">{paras}</hh:paraProperties>'
        f'<hh:numberings itemCnt="{len(_NUMBERING_STARTS)}">{numberings}</hh:numberings>'
        f'<hh:bullets itemCnt="1">{bullets}</hh:bullets>'
        "</hh:refList></hh:head>"
    )


def run(text: str, char: str = "0") -> str:
    return f'<hp:run charPrIDRef="{char}"><hp:t>{escape(text)}</hp:t></hp:run>'


def p(*runs: str, para: str = "0", page_break: bool = False) -> str:
    return (
        f'<hp:p id="0" paraPrIDRef="{para}" styleIDRef="0" pageBreak="{int(page_break)}" columnBreak="0" merged="0">'
        f"{''.join(runs)}</hp:p>"
    )


def cell(
    *paras: str, col: int, row: int, colspan: int = 1, rowspan: int = 1, header: bool = False
) -> str:
    return (
        f'<hp:tc name="" header="{int(header)}" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="1">'
        f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER">{"".join(paras)}</hp:subList>'
        f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/><hp:cellSpan colSpan="{colspan}" rowSpan="{rowspan}"/>'
        f'<hp:cellSz width="{4000 * colspan}" height="1000"/></hp:tc>'
    )


def tbl(rows: list[list[str]], *, cols: int) -> str:
    body = "".join(f"<hp:tr>{''.join(cells)}</hp:tr>" for cells in rows)
    return (
        f'<hp:run charPrIDRef="0"><hp:tbl id="1" zOrder="0" numberingType="TABLE" rowCnt="{len(rows)}" colCnt="{cols}" '
        f'cellSpacing="0" borderFillIDRef="1"><hp:sz width="{4000 * cols}" widthRelTo="ABSOLUTE" height="{1000 * len(rows)}" '
        f'heightRelTo="ABSOLUTE" protect="0"/><hp:pos treatAsChar="1"/>{body}</hp:tbl></hp:run>'
    )


def _content_hpf(sections: int, title: str, meta: dict[str, str], bin_names: list[str]) -> str:
    metas = "".join(
        f'<opf:meta name={quoteattr(name)} content="text">{escape(value)}</opf:meta>'
        for name, value in meta.items()
    )
    items = ['<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>']
    for name in bin_names:
        media = mimetypes.guess_type(name)[0] or "application/octet-stream"
        items.append(
            f"<opf:item id={quoteattr(PurePosixPath(name).stem)} href={quoteattr('BinData/' + name)} "
            f'media-type="{media}" isEmbeded="1"/>'
        )
    items += [
        f'<opf:item id="section{i}" href="Contents/section{i}.xml" media-type="application/xml"/>'
        for i in range(sections)
    ]
    spine = '<opf:itemref idref="header" linear="no"/>' + "".join(
        f'<opf:itemref idref="section{i}"/>' for i in range(sections)
    )
    return (
        f'{_DECL}<opf:package xmlns:opf="{OPF}" version="" unique-identifier="" id="">'
        f"<opf:metadata><opf:title>{escape(title)}</opf:title><opf:language>ko</opf:language>{metas}</opf:metadata>"
        f"<opf:manifest>{''.join(items)}</opf:manifest><opf:spine>{spine}</opf:spine></opf:package>"
    )


def _manifest(sections: int, encrypted: bool) -> str:
    entries = ""
    if encrypted:
        entries = "".join(
            f'<odf:file-entry odf:full-path="Contents/section{i}.xml" odf:media-type="application/xml" odf:size="100">'
            '<odf:encryption-data odf:checksum-type="SHA1" odf:checksum="AAAA">'
            '<odf:algorithm odf:algorithm-name="Blowfish CFB" odf:initialisation-vector="AAAA"/>'
            '<odf:key-derivation odf:key-derivation-name="PBKDF2" odf:iteration-count="1024" odf:salt="AAAA"/>'
            "</odf:encryption-data></odf:file-entry>"
            for i in range(sections)
        )
    return f'{_DECL}<odf:manifest xmlns:odf="{ODF}">{entries}</odf:manifest>'


def hwpx_bytes(
    *sections: str,
    meta: dict[str, str] | None = None,
    title: str = "",
    bin_data: dict[str, bytes] | None = None,
    encrypted: bool = False,
) -> bytes:
    """One section per positional argument (its body XML). ``bin_data`` maps file names to bytes."""
    bin_data = bin_data or {}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr(
            zipfile.ZipInfo("mimetype"), "application/hwp+zip", compress_type=zipfile.ZIP_STORED
        )
        package.writestr(
            "version.xml",
            f'{_DECL}<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" '
            'tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="0" buildNumber="1" xmlVersion="1.3"/>',
        )
        package.writestr(
            "Contents/content.hpf", _content_hpf(len(sections), title, meta or {}, list(bin_data))
        )
        package.writestr("Contents/header.xml", _header())
        for i, body in enumerate(sections):
            package.writestr(f"Contents/section{i}.xml", f"{_DECL}<hs:sec {_NS}>{body}</hs:sec>")
        for name, blob in bin_data.items():
            package.writestr(f"BinData/{name}", blob)
        package.writestr("META-INF/manifest.xml", _manifest(len(sections), encrypted))
    return out.getvalue()
