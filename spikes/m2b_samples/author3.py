"""THROWAWAY: cell padding through the table's inMargin (reuses author.py; same arguments)."""

import runpy
from pathlib import Path

g = runpy.run_path(str(Path(__file__).with_name("author.py")), run_name="author")
d = g["Doc"]()
fid = g["border_fill"](d.header, ("SOLID", "0.12 mm"), ("SOLID", "0.12 mm"), ("SOLID", "0.12 mm"), ("SOLID", "0.12 mm"))
for pad in (141, 425, 850):
    row = g["cell"](0, 0, 48189, g["para"](f"inMargin/cellMargin {pad}"), fid, margin=(pad, pad, pad, pad))
    xml = g["table"](f"<hp:tr>{row}</hp:tr>", 1, 1, 48189, fid).replace(
        '<hp:inMargin left="510" right="510" top="141" bottom="141"/>',
        f'<hp:inMargin left="{pad}" right="{pad}" top="{pad}" bottom="{pad}"/>').replace('hasMargin="1"', 'hasMargin="0"')
    d.body.append(g["para"]("", xml + "<hp:t/>"))
d.save("a_inmargin.hwpx")
