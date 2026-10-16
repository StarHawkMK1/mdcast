import sys
sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2]]
src = open(sys.argv[0].replace("author2.py", "author.py"), encoding="utf-8").read()
src = src[: src.index('variant("v_outline_blank.hwpx"')]
exec(compile(src, "author", "exec"))

def headers2(head, sec, hpf):
    tabs = head.find(".//hh:tabProperties", NS)
    tab = etree.SubElement(tabs, HH + "tabPr", id=str(len(tabs)), autoTabLeft="0", autoTabRight="0")
    etree.SubElement(tab, HH + "tabItem", pos=str(21260 * 2), type="CENTER", leader="NONE")
    etree.SubElement(tab, HH + "tabItem", pos=str(42520 * 2), type="RIGHT", leader="NONE")
    bump(tabs)
    hpara = add_parapr(head, base_id="9")
    head.find(f".//hh:paraPr[@id='{hpara}']", NS).set("tabPrIDRef", tab.get("id"))
    run = etree.SubElement(sec[0], HP + "run", charPrIDRef="0")
    run.append(header_ctrl("header", [["왼쪽칸"], ["가운데칸"], ["오른칸"]], tab.get("id"), hpara, "2"))
    run.append(header_ctrl("footer", [[""], ["PAGE", " / ", "TOTAL_PAGE"], [""]], tab.get("id"), hpara, "2"))
    etree.SubElement(run, HP + "t").text = "본문 첫 쪽"

def outline0(head, sec, hpf):
    for ph in head.iterfind(".//hh:numbering[@id='1']/hh:paraHead", NS):
        ph.text = None
    for lv in (1, 2, 3):
        pid = add_parapr(head, base_id=str(lv + 1), left=0)
        paragraph(sec, f"제목 수준{lv}", para=pid, style=str(lv + 1))
        paragraph(sec, "본문 문단")

variant("v_headers2.hwpx", headers2)
variant("v_outline0.hwpx", outline0)
