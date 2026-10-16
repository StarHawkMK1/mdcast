"""THROWAWAY: third batch (units, first paragraph, textOffset, links, lists, landscape)."""

import sys

src = open(sys.argv[0].replace("author3.py", "author.py"), encoding="utf-8").read()
src = src[: src.index('variant("v_outline_blank.hwpx"')]
exec(compile(src, "author", "exec"))

LONGER = "목록 항목이 길어서 다음 줄로 넘어가는지 보려고 충분히 긴 문장을 씁니다. " * 3


def set_margin(head, pid, **values):
    m = head.find(f".//hh:paraPr[@id='{pid}']/hh:margin", NS)
    for key, value in values.items():
        m.find(f"hc:{key}", NS).set("value", str(value))


def line100(head, pid):
    head.find(f".//hh:paraPr[@id='{pid}']/hh:lineSpacing", NS).set("value", "100")


def into_first(sec, p):
    """Move the secPr run of the first paragraph into ``p`` and make ``p`` the first paragraph."""
    first = sec[0]
    sec.remove(p)
    secrun = first.find("hp:run", NS)
    p.insert(0, secrun)
    sec.remove(first)
    sec.insert(0, p)


def units(head, sec, hpf):
    # 10pt text, 100% lines: margin values known; plain HWPUNIT would give 10mm/5mm/7.06mm
    plain = add_parapr(head)
    line100(head, plain)
    set_margin(head, plain, left=0, intent=0, prev=0, next=0)
    probe = add_parapr(head)
    line100(head, probe)
    set_margin(head, probe, left=2834, intent=1417, prev=2000, next=2000)
    paragraph(sec, "가 기준 첫째", para=plain)
    paragraph(sec, "나 기준 둘째", para=plain)
    paragraph(sec, "다 시험 문단" + LONG, para=probe)
    paragraph(sec, "라 기준 셋째", para=plain)
    into_first(sec, sec[1])


def heading_first(head, sec, hpf):
    for ph in head.iterfind(".//hh:numbering[@id='1']/hh:paraHead", NS):
        ph.text = None
        ph.set("textOffset", "0")
    pid = add_parapr(head, base_id="2", left=0)
    body = add_parapr(head)
    paragraph(sec, "제목 맨 앞", para=pid, style="2")
    paragraph(sec, "본문 문단", para=body)
    into_first(sec, sec[1])


def link_field(run_parent, url, text, char="0"):
    command = url.replace("\\", "\\\\").replace(":", "\\:").replace(";", "\\;") + ";1;0;0;"
    r = etree.SubElement(run_parent, HP + "run", charPrIDRef=char)
    c = etree.SubElement(r, HP + "ctrl")
    fb = etree.SubElement(c, HP + "fieldBegin", id="1234567", type="HYPERLINK", name="", editable="0", dirty="0", zorder="-1", fieldid="627600491")
    ps = etree.SubElement(fb, HP + "parameters", cnt="6", name="")
    etree.SubElement(ps, HP + "integerParam", name="Prop").text = "0"
    etree.SubElement(ps, HP + "stringParam", name="Command").text = command
    etree.SubElement(ps, HP + "stringParam", name="Path").text = url
    etree.SubElement(ps, HP + "stringParam", name="Category").text = "HWPHYPERLINK_TYPE_URL"
    etree.SubElement(ps, HP + "stringParam", name="TargetType").text = "HWPHYPERLINK_TARGET_BOOKMARK"
    etree.SubElement(ps, HP + "stringParam", name="DocOpenType").text = "HWPHYPERLINK_JUMP_CURRENTTAB"
    r2 = etree.SubElement(run_parent, HP + "run", charPrIDRef=char)
    etree.SubElement(r2, HP + "t").text = text
    r3 = etree.SubElement(run_parent, HP + "run", charPrIDRef=char)
    c3 = etree.SubElement(r3, HP + "ctrl")
    etree.SubElement(c3, HP + "fieldEnd", beginIDRef="1234567", fieldid="627600491")
    etree.SubElement(r3, HP + "t").text = " 뒤"


def links(head, sec, hpf):
    p = paragraph(sec, "앞 ")
    link_field(p, "https://example.com/a?b=1&c=2;d=3#frag", "링크글")
    into_first(sec, p)


def lists(head, sec, hpf):
    # hanging indent: left 10mm, first line 5mm further left; values written doubled
    tab_variant = add_parapr(head)
    set_margin(head, tab_variant, left=2 * 2834, intent=-2 * 1417)
    space_variant = add_parapr(head)
    set_margin(head, space_variant, left=2 * 2834, intent=-2 * 1417)
    p = paragraph(sec, "", para=tab_variant)
    t = p.find(".//hp:t", NS)
    t.text = "□"
    tab = etree.SubElement(t, HP + "tab", width="0", leader="0", type="1")
    tab.tail = "탭" + LONGER
    paragraph(sec, "□ 공백" + LONGER, para=space_variant)
    into_first(sec, p)


def landscape(value, swap):
    def edit(head, sec, hpf):
        pp = sec.find(".//hp:pagePr", NS)
        pp.set("landscape", value)
        if swap:
            w, h = pp.get("width"), pp.get("height")
            pp.set("width", h)
            pp.set("height", w)
        p = paragraph(sec, "방향 시험")
        into_first(sec, p)
    return edit


variant("w_units.hwpx", units)
variant("w_heading_first.hwpx", heading_first)
variant("w_links.hwpx", links)
variant("w_lists.hwpx", lists)
variant("w_land_narrow.hwpx", landscape("NARROWLY", False))
variant("w_land_swap.hwpx", landscape("WIDELY", True))
