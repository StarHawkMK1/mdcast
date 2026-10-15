"""THROWAWAY spike S1: append generated paragraphs to section0.xml of a seed hwpx.

Also edits one value in Contents/header.xml (the first charPr height, x1.5) so that
the spike covers both body-XML and header-XML rewriting (spec S1 / M2 writer needs both).
"""

import copy
import sys
import zipfile
from pathlib import Path

from lxml import etree

TEXTS = ["mdcast 스파이크 문단 1", "둘째 문단: 한글 English 123", "셋째 문단 — 특수문자 <>&"]
STRIP = {"secPr", "ctrl", "linesegarray"}
HEIGHT_SCALE = 1.5


def localname(el) -> str:
    return etree.QName(el).localname


def patch_section(root) -> None:
    paragraphs = [el for el in root if localname(el) == "p"]
    template = paragraphs[0]
    next_id = 1_000_000
    for text in TEXTS:
        p = copy.deepcopy(template)
        for el in [e for e in p.iter() if localname(e) in STRIP]:
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
        if "id" in p.attrib:
            p.set("id", str(next_id))
            next_id += 1
        runs = [el for el in p.iter() if localname(el) == "run"]
        for extra in runs[1:]:
            extra.getparent().remove(extra)
        run = runs[0]
        ts = [el for el in run if localname(el) == "t"]
        ns = etree.QName(run).namespace
        t = ts[0] if ts else etree.SubElement(run, f"{{{ns}}}t" if ns else "t")
        for extra in ts[1:]:
            run.remove(extra)
        t.text = text
        root.append(p)


def patch_header(root) -> None:
    char_pr = next(el for el in root.iter() if localname(el) == "charPr")
    old = int(char_pr.get("height"))
    new = round(old * HEIGHT_SCALE)
    char_pr.set("height", str(new))
    print(f"header charPr id={char_pr.get('id')} height {old} -> {new}")


def patch(seed: Path, out: Path) -> None:
    with zipfile.ZipFile(seed) as zin:
        names = zin.namelist()
        section_name = next(n for n in names if n.lower().endswith("section0.xml"))
        header_name = next(n for n in names if n.lower().endswith("contents/header.xml"))

        section_root = etree.fromstring(zin.read(section_name))
        patch_section(section_root)
        new_section = etree.tostring(
            section_root, xml_declaration=True, encoding="UTF-8", standalone=True
        )

        header_root = etree.fromstring(zin.read(header_name))
        patch_header(header_root)
        new_header = etree.tostring(
            header_root, xml_declaration=True, encoding="UTF-8", standalone=True
        )

        replaced = {section_name: new_section, header_name: new_header}
        with zipfile.ZipFile(out, "w") as zout:
            for info in zin.infolist():
                if info.filename in replaced:
                    data = replaced[info.filename]
                else:
                    data = zin.read(info.filename)
                mode = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
                zout.writestr(info.filename, data, compress_type=mode)
    print("wrote", out)


if __name__ == "__main__":
    patch(Path(sys.argv[1]), Path(sys.argv[2]))
