"""THROWAWAY: hand-written M2b variants on the built-in container, as mdcast would write them.

usage: author.py <img dir from capture.py> <out dir>
"""

import sys
from pathlib import Path

from lxml import etree

from mdcast.hwpx.container import Package
from mdcast.hwpx.header import HC, HH, Header
from mdcast.hwpx.section import HP

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "src/mdcast/builtin_templates/default/reference.hwpx"
IMG = Path(sys.argv[1])
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
NS = f'xmlns:hp="{HP}" xmlns:hc="{HC}" xmlns:hh="{HH}"'
OPF = "http://www.idpf.org/2007/opf/"


def border_fill(header, left, right, top, bottom, fill=None):
    """Each side: (type, width) or None."""
    sides = []
    for name, side in (("leftBorder", left), ("rightBorder", right), ("topBorder", top), ("bottomBorder", bottom)):
        kind, width = side or ("NONE", "0.1 mm")
        sides.append(f'<hh:{name} type="{kind}" width="{width}" color="#000000"/>')
    brush = f'<hc:fillBrush><hc:winBrush faceColor="{fill}" hatchColor="#999999" alpha="0"/></hc:fillBrush>' if fill else ""
    xml = (f'<hh:borderFill {NS} id="0" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
           '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
           + "".join(sides) + '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>' + brush + "</hh:borderFill>")
    return header._add("borderFills", etree.fromstring(xml))


def para(text="", inner=""):
    t = f"<hp:t>{text}</hp:t>" if text else ""
    return (f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="0">{t}{inner}</hp:run></hp:p>')


def sublist(body, valign="CENTER"):
    return (f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="{valign}" linkListIDRef="0" '
            f'linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">{body}</hp:subList>')


def cell(col, row, width, body, fill_id, header=False, span=(1, 1), height=100, margin=None):
    has = "1" if margin else "0"
    m = margin or (510, 510, 141, 141)
    return (f'<hp:tc name="" header="{1 if header else 0}" hasMargin="{has}" protect="0" editable="0" dirty="0" '
            f'borderFillIDRef="{fill_id}">{sublist(body)}<hp:cellAddr colAddr="{col}" rowAddr="{row}"/>'
            f'<hp:cellSpan colSpan="{span[0]}" rowSpan="{span[1]}"/><hp:cellSz width="{width}" height="{height}"/>'
            f'<hp:cellMargin left="{m[0]}" right="{m[1]}" top="{m[2]}" bottom="{m[3]}"/></hp:tc>')


def table(rows_xml, n_rows, n_cols, width, fill_id, caption="", repeat=True):
    return (f'<hp:tbl id="0" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" '
            f'dropcapstyle="None" pageBreak="CELL" repeatHeader="{1 if repeat else 0}" rowCnt="{n_rows}" colCnt="{n_cols}" '
            f'cellSpacing="0" borderFillIDRef="{fill_id}" noAdjust="0"><hp:sz width="{width}" widthRelTo="ABSOLUTE" '
            f'height="{n_rows * 1000}" heightRelTo="ABSOLUTE" protect="0"/><hp:pos treatAsChar="1" affectLSpacing="0" '
            f'flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" '
            f'horzAlign="LEFT" vertOffset="0" horzOffset="0"/><hp:outMargin left="0" right="0" top="0" bottom="0"/>'
            f'{caption}<hp:inMargin left="510" right="510" top="141" bottom="141"/>{rows_xml}</hp:tbl>')


def caption_xml(text, side, width):
    body = (f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="0"><hp:t>{text}</hp:t></hp:run></hp:p>')
    return (f'<hp:caption side="{side}" fullSz="0" width="8504" gap="850" lastWidth="{width}">'
            f'{sublist(body, "TOP")}</hp:caption>')


class Doc:
    def __init__(self):
        self.package = Package.read(SEED.read_bytes())
        self.header = Header(self.package.xml("Contents/header.xml"))
        self.section = self.package.xml("Contents/section0.xml")
        self.content = self.package.xml("Contents/content.hpf")
        self.body = []

    def add_image(self, name, data, media):
        self.package.set(f"BinData/{name}", data)
        manifest = self.content.find(f"{{{OPF}}}manifest")
        item = etree.SubElement(manifest, f"{{{OPF}}}item", id=Path(name).stem, href=f"BinData/{name}",
                                **{"media-type": media, "isEmbeded": "1"})
        return item.get("id")

    def save(self, name):
        first = self.section.find(f"{{{HP}}}p")
        for extra in self.section.findall(f"{{{HP}}}p")[1:]:
            self.section.remove(extra)
        for run in first.findall(f"{{{HP}}}run")[1:]:
            first.remove(run)
        for xml in self.body:
            self.section.append(etree.fromstring(xml.replace("<hp:p ", f"<hp:p {NS} ", 1)))
        self.package.set_xml("Contents/header.xml", self.header.root)
        self.package.set_xml("Contents/section0.xml", self.section)
        self.package.set_xml("Contents/content.hpf", self.content)
        (OUT / name).write_bytes(self.package.write())
        print("wrote", name)


BODY = 48189  # 170mm


def bordered_table(doc, rows, cols, outer, inner, header_fill=None, n_header=1, caption="", span_demo=False):
    width = BODY // cols
    out = []
    for r in range(rows):
        cells = []
        for c in range(cols):
            if span_demo and r == 0 and c == 2:
                continue  # covered by (1,0) colspan 2
            if span_demo and r == 1 and c == 0:
                continue  # covered by (0,0) rowspan 2
            left = outer if c == 0 else inner
            span = (1, 1)
            if span_demo and r == 0 and c == 0:
                span = (1, 2)
            if span_demo and r == 0 and c == 1:
                span = (2, 1)
            right = outer if c + span[0] == cols else inner
            top = outer if r == 0 else inner
            bottom = outer if r + span[1] == rows else inner
            is_head = r < n_header
            fid = border_fill(doc.header, left, right, top, bottom, header_fill if is_head else None)
            text = f"{'머리' if is_head else '칸'} {r}-{c} " + ("긴 글자 " * (6 if (r, c) == (n_header, 1) else 0))
            cells.append(cell(c, r, width * span[0], para(text), fid, header=is_head, span=span))
        out.append("<hp:tr>" + "".join(cells) + "</hp:tr>")
    plain = border_fill(doc.header, None, None, None, None)
    return para("", table("".join(out), rows, cols, width * cols, plain, caption) + "<hp:t/>")


def t_borders():
    d = Doc()
    d.body.append(para("앞 문단: 바깥 0.4mm, 안쪽 0.12mm, 머리행 회색, 칸 높이 100(작게)"))
    d.body.append(bordered_table(d, 4, 3, ("SOLID", "0.4 mm"), ("SOLID", "0.12 mm"), "#F2F2F2"))
    d.body.append(para("임의 굵기 0.18 mm / 0.35 mm"))
    d.body.append(bordered_table(d, 3, 3, ("SOLID", "0.35 mm"), ("SOLID", "0.18 mm"), "#E5E5E5"))
    d.body.append(para("뒤 문단"))
    d.save("a_borders.hwpx")


def t_merge():
    d = Doc()
    d.body.append(bordered_table(d, 3, 3, ("SOLID", "0.4 mm"), ("SOLID", "0.12 mm"), "#F2F2F2", span_demo=True))
    d.save("a_merge.hwpx")


def t_repeat():
    d = Doc()
    d.body.append(bordered_table(d, 80, 3, ("SOLID", "0.4 mm"), ("SOLID", "0.12 mm"), "#F2F2F2"))
    d.save("a_repeat.hwpx")


def t_caption():
    d = Doc()
    cap = caption_xml("&lt;표 1&gt; 위 캡션 (자동 번호 없음)", "TOP", BODY)
    d.body.append(bordered_table(d, 2, 2, ("SOLID", "0.4 mm"), ("SOLID", "0.12 mm"), caption=cap))
    cap = caption_xml("&lt;표 2&gt; 아래 캡션", "BOTTOM", BODY)
    d.body.append(bordered_table(d, 2, 2, ("SOLID", "0.4 mm"), ("SOLID", "0.12 mm"), caption=cap))
    d.save("a_caption.hwpx")


def pic(item_id, px_w, px_h, cur_w, cur_h, org_per_px=93.75, dim_per_px=75, comment="설명", caption=""):
    org_w, org_h = round(px_w * org_per_px), round(px_h * org_per_px)
    dim_w, dim_h = round(px_w * dim_per_px), round(px_h * dim_per_px)
    sx, sy = cur_w / org_w, cur_h / org_h
    return (f'<hp:pic id="0" zOrder="0" numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" '
            f'dropcapstyle="None" href="" groupLevel="0" instid="0" reverse="0"><hp:offset x="0" y="0"/>'
            f'<hp:orgSz width="{org_w}" height="{org_h}"/><hp:curSz width="{cur_w}" height="{cur_h}"/>'
            f'<hp:flip horizontal="0" vertical="0"/><hp:rotationInfo angle="0" centerX="{cur_w // 2}" centerY="{cur_h // 2}" rotateimage="1"/>'
            f'<hp:renderingInfo><hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
            f'<hc:scaMatrix e1="{sx:.6f}" e2="0" e3="0" e4="0" e5="{sy:.6f}" e6="0"/>'
            f'<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/></hp:renderingInfo>'
            f'<hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="{org_w}" y="0"/><hc:pt2 x="{org_w}" y="{org_h}"/><hc:pt3 x="0" y="{org_h}"/></hp:imgRect>'
            f'<hp:imgClip left="0" right="{dim_w}" top="0" bottom="{dim_h}"/><hp:inMargin left="0" right="0" top="0" bottom="0"/>'
            f'<hp:imgDim dimwidth="{dim_w}" dimheight="{dim_h}"/>'
            f'<hc:img binaryItemIDRef="{item_id}" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/><hp:effects/>'
            f'<hp:sz width="{cur_w}" widthRelTo="ABSOLUTE" height="{cur_h}" heightRelTo="ABSOLUTE" protect="0"/>'
            f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" '
            f'horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
            f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>{caption}<hp:shapeComment>{comment}</hp:shapeComment></hp:pic>')


def t_pictures():
    d = Doc()
    png = d.add_image("mdcast1.png", (IMG / "a96.png").read_bytes(), "image/png")
    jpg = d.add_image("mdcast2.jpg", (IMG / "a.jpg").read_bytes(), "image/jpg")
    svg = d.add_image("mdcast3.svg", (IMG / "a.svg").read_bytes(), "image/svg")
    # 400x200 px at 96 dpi = 105.8 x 52.9 mm = 30000 x 15000 HWPUNIT
    d.body.append(para("원래 크기(96dpi): ", pic(png, 400, 200, 30000, 15000) + "<hp:t/>"))
    d.body.append(para("반으로: ", pic(png, 400, 200, 15000, 7500) + "<hp:t/>"))
    d.body.append(para("같은 파일 다시: ", pic(png, 400, 200, 15000, 7500) + "<hp:t/>"))
    d.body.append(para("jpg: ", pic(jpg, 400, 200, 15000, 7500) + "<hp:t/>"))
    d.body.append(para("svg: ", pic(svg, 400, 200, 15000, 7500, org_per_px=75, dim_per_px=60) + "<hp:t/>"))
    cap = caption_xml("[그림 1] 아래 캡션", "BOTTOM", 30000)
    d.body.append(para("", pic(png, 400, 200, 30000, 15000, caption=cap) + "<hp:t/>"))
    fid = border_fill(d.header, ("SOLID", "0.12 mm"), ("SOLID", "0.12 mm"), ("SOLID", "0.12 mm"), ("SOLID", "0.12 mm"))
    half = BODY // 2
    inner = half - 1020
    w, h = inner, inner // 2
    row1 = cell(0, 0, half, para("", pic(png, 400, 200, w, h) + "<hp:t/>"), fid) + cell(1, 0, half, para("", pic(jpg, 400, 200, w, h) + "<hp:t/>"), fid)
    row2 = cell(0, 1, half, para("설명 1"), fid) + cell(1, 1, half, para("설명 2"), fid)
    d.body.append(para("", table(f"<hp:tr>{row1}</hp:tr><hp:tr>{row2}</hp:tr>", 2, 2, BODY, fid) + "<hp:t/>"))
    d.save("a_pictures.hwpx")


def footnote(number, paragraphs):
    first, *rest = paragraphs
    num = (f'<hp:ctrl><hp:autoNum num="{number}" numType="FOOTNOTE"><hp:autoNumFormat type="DIGIT" userChar="" '
           f'prefixChar="" suffixChar=")" supscript="0"/></hp:autoNum></hp:ctrl>')
    body = (f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="0">{num}<hp:t> {first}</hp:t></hp:run></hp:p>')
    body += "".join(para(text) for text in rest)
    return (f'<hp:ctrl><hp:footNote number="{number}" suffixChar="41" instId="0">{sublist(body, "TOP")}'
            f'</hp:footNote></hp:ctrl>')


def t_footnotes():
    d = Doc()
    d.body.append(para("본문 하나", footnote(1, ["첫 각주"]) + "<hp:t> 본문 둘</hp:t>" + footnote(2, ["둘째 첫 문단", "둘째 둘째 문단"]) + "<hp:t> 끝</hp:t>"))
    fid = border_fill(d.header, ("SOLID", "0.12 mm"), ("SOLID", "0.12 mm"), ("SOLID", "0.12 mm"), ("SOLID", "0.12 mm"))
    row = cell(0, 0, BODY, para("칸 글자", footnote(3, ["칸 안 각주"]) + "<hp:t/>"), fid)
    d.body.append(para("", table(f"<hp:tr>{row}</hp:tr>", 1, 1, BODY, fid) + "<hp:t/>"))
    d.save("a_footnotes.hwpx")


def t_padding():
    d = Doc()
    fid = border_fill(d.header, ("SOLID", "0.12 mm"), ("SOLID", "0.12 mm"), ("SOLID", "0.12 mm"), ("SOLID", "0.12 mm"))
    pad = 425  # 1.5mm
    row = (cell(0, 0, BODY // 2, para("여백 1.5mm (hasMargin=1)"), fid, margin=(pad, pad, pad, pad))
           + cell(1, 0, BODY // 2, para("표 기본 여백"), fid))
    d.body.append(para("", table(f"<hp:tr>{row}</hp:tr>", 1, 2, BODY, fid) + "<hp:t/>"))
    d.save("a_padding.hwpx")


for build in (t_borders, t_merge, t_repeat, t_caption, t_pictures, t_footnotes, t_padding):
    build()
