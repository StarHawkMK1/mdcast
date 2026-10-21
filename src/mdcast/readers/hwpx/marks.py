"""Begin/end marks read inside a paragraph: tracked changes and field parameters."""

from __future__ import annotations

import re

from lxml import etree

from mdcast.readers.hwpx.package import HP

_P = f"{{{HP}}}p"
_T = f"{{{HP}}}t"
_DELETE_BEGIN, _DELETE_END = f"{{{HP}}}deleteBegin", f"{{{HP}}}deleteEnd"
_STRING_PARAM = f"{{{HP}}}stringParam"
# Hancom's click-here Command: "Clickhere:set:<n>:Direction:wstring:<length>:<guide text> HelpState:..."
_DIRECTION = re.compile(r"Direction:wstring:(\d+):")


def own(p: etree._Element, *tags: str) -> list[etree._Element]:
    """Elements under ``p`` (document order) that belong to it, not to a paragraph nested in it."""
    return [e for e in p.iter(*tags) if e is not p and next(e.iterancestors(_P), None) is p]


def accept_deletions(ps: list[etree._Element]) -> None:
    """Remove the text of sibling paragraphs that a tracked deletion marks, as if it were accepted.

    ``ps`` is one paragraph list (a section's paragraphs, or one ``hp:subList``'s). A deletion is
    the text between a ``deleteBegin`` and the next ``deleteEnd`` with the same ``Id`` later in the
    list, across paragraphs; a paragraph left without text is then dropped like any empty one. A
    begin without such an end and an end without a begin delete nothing, so no text outside a
    marked span is lost. Marks inside the span (tabs, line breaks) go with it; tables, notes and
    the paragraphs in them stay.
    """
    matched: set[etree._Element] = set()  # begins with an end of the same Id after them
    later_ends: set[str | None] = set()
    for mark in reversed([m for p in ps for m in own(p, _DELETE_BEGIN, _DELETE_END)]):
        if mark.tag == _DELETE_END:
            later_ends.add(mark.get("Id"))
        elif mark.get("Id") in later_ends:
            matched.add(mark)
    if not matched:
        return
    deleting, closing = False, None  # closing: the Id of the open deletion's end
    doomed: list[etree._Element] = []
    for e in (e for p in ps for e in own(p)):
        if not deleting:
            if e in matched:
                deleting, closing = True, e.get("Id")
                e.tail = None
        elif e.tag == _DELETE_END and e.get("Id") == closing:
            deleting = False
        elif e.tag in (_DELETE_BEGIN, _DELETE_END):
            e.tail = None
        elif e.tag == _T:
            e.text = None
        elif e.getparent().tag == _T:  # a tab or other mark inside the deleted text, with its tail
            doomed.append(e)
    for e in doomed:
        e.getparent().remove(e)


def _params(begin: etree._Element) -> dict[str, str]:
    return {e.get("name") or "": "".join(e.itertext()) for e in begin.iter(_STRING_PARAM)}


def hyperlink_url(begin: etree._Element) -> str:
    """The URL of a HYPERLINK field: its ``Command`` up to the first unescaped ``;``.

    Hancom escapes ``\\``, ``:`` and ``;`` in the Command with a backslash.
    """
    command = _params(begin).get("Command", "")
    out: list[str] = []
    chars = iter(command)
    for ch in chars:
        if ch == "\\":
            out.append(next(chars, ""))
        elif ch == ";":
            break
        else:
            out.append(ch)
    return "".join(out).strip()


def click_here_guide(begin: etree._Element) -> str:
    """The guide text of a CLICK_HERE field: its ``Direction`` parameter, else the one in ``Command``."""
    params = _params(begin)
    guide = params.get("Direction", "")
    if not guide.strip():
        command = params.get("Command", "")
        m = _DIRECTION.search(command)
        guide = command[m.end() : m.end() + int(m.group(1))] if m else ""
    return guide.strip()
