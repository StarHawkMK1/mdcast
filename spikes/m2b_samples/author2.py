"""THROWAWAY: which border widths Hangul keeps (reuses author.py; same arguments)."""

import runpy
from pathlib import Path

g = runpy.run_path(str(Path(__file__).with_name("author.py")), run_name="author")
WIDTHS = ["0.1 mm", "0.12 mm", "0.15 mm", "0.2 mm", "0.25 mm", "0.3 mm", "0.4 mm", "0.5 mm", "0.6 mm",
          "0.7 mm", "1.0 mm", "1.5 mm", "2.0 mm", "3.0 mm", "4.0 mm", "5.0 mm", "0.18 mm", "0.35 mm", "1 mm"]
d = g["Doc"]()
for w in WIDTHS:
    d.body.append(g["para"](f"굵기 {w}"))
    d.body.append(g["bordered_table"](d, 1, 1, ("SOLID", w), ("SOLID", w)))
d.save("a_widths.hwpx")
