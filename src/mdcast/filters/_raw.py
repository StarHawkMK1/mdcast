from __future__ import annotations

import panflute as pf


def raw_block(text: str, fmt: str) -> pf.RawBlock:
    # panflute 2.3.1 rejects "typst" in the constructor, so the format is set after construction.
    block = pf.RawBlock(text, format="html")
    block.format = fmt
    return block
