import panflute as pf
from helpers import HWPX_NS as NS
from helpers import hwpx_render, hwpx_texts

from mdcast.ast import md_to_doc


def notes(paragraphs):
    return [n for p in paragraphs for n in p.iter(f"{{{NS['hp']}}}footNote")]


def test_footnotes_are_hangul_footnotes():
    _, shapes, paragraphs, notices = hwpx_render("본문[^1] 둘[^2]\n\n[^1]: 첫 각주\n[^2]: 둘째\n\n    둘째 문단\n")
    first, second = notes(paragraphs)
    assert [n.get("number") for n in (first, second)] == ["1", "2"]
    p = first.find("hp:subList/hp:p", NS)
    assert p.get("styleIDRef") == shapes["footnote"].style
    auto = p.find("hp:run/hp:ctrl/hp:autoNum", NS)
    assert (auto.get("num"), auto.get("numType")) == ("1", "FOOTNOTE")
    assert auto.find("hp:autoNumFormat", NS).get("suffixChar") == ")"
    assert "".join(p.itertext()).strip() == "첫 각주"
    assert len(second.findall("hp:subList/hp:p", NS)) == 2
    assert hwpx_texts(paragraphs) == ["본문 둘"]
    assert notices.items == []


def test_footnote_in_a_cell_is_a_footnote():
    _, _, paragraphs, notices = hwpx_render("| a |\n|---|\n| 칸[^1] |\n\n[^1]: 칸 각주\n")
    assert len(notes(paragraphs)) == 1 and notices.items == []


def test_footnote_starting_with_a_list_gets_a_number_paragraph_first():
    _, _, paragraphs, _ = hwpx_render("가[^1]\n\n[^1]:\n    - 하나\n    - 둘\n")
    [note] = notes(paragraphs)
    first = note.find("hp:subList/hp:p", NS)
    assert first.find("hp:run/hp:ctrl/hp:autoNum", NS) is not None
    assert len(note.findall("hp:subList/hp:p", NS)) == 3


def test_note_in_note_falls_back_with_its_own_numbers():
    doc = md_to_doc("가[^1] 나[^2]\n\n[^1]: 바깥\n[^2]: 둘째\n")
    outer = []
    doc.walk(lambda e, _d: outer.append(e) if isinstance(e, pf.Note) else None)
    outer[0].content[0].content.append(pf.Note(pf.Para(pf.Str("안쪽"))))
    _, _, paragraphs, notices = hwpx_render("", doc=doc)
    assert [n.get("number") for n in notes(paragraphs)] == ["1", "2"]
    assert "[주 1]" in "".join(notes(paragraphs)[0].itertext())
    assert hwpx_texts(paragraphs)[-1] == "[주 1] 안쪽"
    assert [(n.kind, n.element) for n in notices.items] == [("degraded", "footnote")]
