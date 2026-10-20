"""THROWAWAY: print section0.xml (without line segments), manifest items and BinData entries."""

import re
import sys
import zipfile

for path in sys.argv[1:]:
    archive = zipfile.ZipFile(path)
    print(f"##### {path}")
    print("entries:", [(i.filename, i.compress_type) for i in archive.infolist() if i.filename.startswith("BinData")])
    hpf = archive.read("Contents/content.hpf").decode("utf-8")
    print("manifest:", re.findall(r"<opf:item [^>]*BinData[^>]*>", hpf))
    header = archive.read("Contents/header.xml").decode("utf-8")
    print("binDataList:", re.findall(r"<hh:binDataList.*?</hh:binDataList>", header, re.S))
    section = archive.read("Contents/section0.xml").decode("utf-8")
    section = re.sub(r"<hp:linesegarray>.*?</hp:linesegarray>", "", section)
    start = section.find("</hp:secPr>")
    print(section[start:] if start >= 0 else section)
