import sys
src = open(sys.argv[0].replace("author4.py", "author3.py"), encoding="utf-8").read()
src = src[: src.index('variant("w_units.hwpx"')]
sys.argv[0] = sys.argv[0].replace("author4.py", "author3.py")
exec(compile(src, "author3", "exec"))

def list_with(tab_id_fn):
    def edit(head, sec, hpf):
        tab_id = tab_id_fn(head)
        pid = add_parapr(head)
        set_margin(head, pid, left=2 * 2834, intent=-2 * 1417)
        head.find(f".//hh:paraPr[@id='{pid}']", NS).set("tabPrIDRef", tab_id)
        first = None
        for marker in ("□", "1.", "(가)"):
            p = paragraph(sec, "", para=pid)
            t = p.find(".//hp:t", NS)
            t.text = marker
            etree.SubElement(t, HP + "tab", width="0", leader="0", type="1").tail = "탭" + LONGER
            first = first or p
        into_first(sec, first)
    return edit

def auto(head):
    return "1"  # container tabPr id=1: autoTabLeft="1"

def explicit(head):
    tabs = head.find(".//hh:tabProperties", NS)
    tab = etree.SubElement(tabs, HH + "tabPr", id=str(len(tabs)), autoTabLeft="0", autoTabRight="0")
    etree.SubElement(tab, HH + "tabItem", pos=str(2 * (2834 + 1417)), type="LEFT", leader="NONE")
    bump(tabs)
    return tab.get("id")

variant("x_list_auto.hwpx", list_with(auto))
variant("x_list_explicit.hwpx", list_with(explicit))
