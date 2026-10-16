import panflute as pf
from helpers import HWPX_NS as NS
from helpers import hwpx_render, hwpx_texts

from mdcast.ast import md_to_doc
from mdcast.filters._raw import raw_block


def runs(paragraph):
    return [(r.get("charPrIDRef"), "".join("".join(t.itertext()) for t in r.findall("hp:t", NS)))
            for r in paragraph.findall("hp:run", NS)]


def test_heading_and_body_paragraphs():
    header, shapes, paragraphs, _ = hwpx_render("# 제목\n\n본문 *기울임* **굵게**\n")
    assert hwpx_texts(paragraphs) == ["제목", "본문 기울임 굵게"]
    heading, body = paragraphs
    assert heading.get("styleIDRef") == "2" and heading.get("paraPrIDRef") == shapes["heading1"].para
    assert body.get("paraPrIDRef") == shapes["body"].para
    chars = [char for char, _ in runs(body)]
    assert chars[0] == shapes["body"].char and len(set(chars)) == 3
    assert header.item("charProperties", chars[1]).find("hh:italic", NS) is not None
    assert header.item("charProperties", chars[-1]).find("hh:bold", NS) is not None  # after a space run


def test_inline_code_uses_the_code_font_and_size():
    header, shapes, paragraphs, _ = hwpx_render("앞 `x = 1` 뒤\n")
    char = runs(paragraphs[0])[1][0]
    element = header.item("charProperties", char)
    assert element.get("height") == "950"
    code_ref = header.item("charProperties", shapes["code"].char).find("hh:fontRef", NS).get("latin")
    assert element.find("hh:fontRef", NS).get("latin") == code_ref


def test_code_block_is_one_paragraph_with_line_breaks():
    _, shapes, paragraphs, _ = hwpx_render("```\n가\n나\n```\n")
    assert len(paragraphs) == 1 and paragraphs[0].get("paraPrIDRef") == shapes["code"].para
    assert len(paragraphs[0].findall(".//hp:lineBreak", NS)) == 1
    assert hwpx_texts(paragraphs) == ["가나"]


def test_link_field():
    url = "https://x.kr/a?b=1;c:d\\e"
    doc = pf.Doc(pf.Para(pf.Link(pf.Str("링크"), url=url), pf.Space(), pf.Str("뒤")))
    header, _, paragraphs, _ = hwpx_render("", doc=doc)
    p = paragraphs[0]
    begin = p.find(".//hp:fieldBegin", NS)
    params = {e.get("name"): e.text for e in begin.find("hp:parameters", NS)}
    assert begin.get("type") == "HYPERLINK" and begin.get("fieldid") == "627600491"
    assert params["Command"] == "https\\://x.kr/a?b=1\\;c\\:d\\\\e;1;0;0;"
    assert params["Path"] == "https://x.kr/a?b=1;c:d\\e"
    assert p.find(".//hp:fieldEnd", NS).get("beginIDRef") == begin.get("id")
    link_char = next(char for char, text in runs(p) if text == "링크")
    element = header.item("charProperties", link_char)
    assert element.get("textColor") == "#0000FF" and element.find("hh:underline", NS) is not None


def test_internal_link_is_plain_text():
    _, _, paragraphs, _ = hwpx_render("[절](#sec)\n")
    assert paragraphs[0].find(".//hp:fieldBegin", NS) is None
    assert hwpx_texts(paragraphs) == ["절"]


def test_pagebreak_marker_breaks_before_the_next_paragraph():
    doc = md_to_doc("가\n\n나\n")
    doc.content.insert(1, raw_block("pagebreak", "mdcast-hwpx"))
    _, _, paragraphs, _ = hwpx_render("", doc=doc)
    assert [p.get("pageBreak") for p in paragraphs] == ["0", "1"]


def test_raw_blocks_of_other_formats_are_dropped():
    doc = md_to_doc("가\n")
    doc.content.append(raw_block("#pagebreak()", "typst"))
    _, _, paragraphs, _ = hwpx_render("", doc=doc)
    assert hwpx_texts(paragraphs) == ["가"]


def test_control_characters_are_dropped():
    doc = pf.Doc(pf.Para(pf.Str("가\x0b나\x01다")))
    _, _, paragraphs, _ = hwpx_render("", doc=doc)
    assert hwpx_texts(paragraphs) == ["가나다"]


def test_quotes_indent_per_level():
    header, shapes, paragraphs, _ = hwpx_render("> 바깥\n>\n> > 안쪽\n")
    lefts = [header.para_left(p.get("paraPrIDRef")) for p in paragraphs]
    assert abs(lefts[0] - 5.0) < 0.01 and abs(lefts[1] - 10.0) < 0.01
    assert all(p.get("styleIDRef") == shapes["quote"].style for p in paragraphs)


def test_horizontal_rule_draws_a_bottom_border():
    header, _, paragraphs, _ = hwpx_render("가\n\n---\n\n나\n")
    rule = paragraphs[1]
    fill_id = header.item("paraProperties", rule.get("paraPrIDRef")).find("hh:border", NS).get("borderFillIDRef")
    assert header.item("borderFills", fill_id).find("hh:bottomBorder", NS).get("type") == "SOLID"
    assert hwpx_texts(paragraphs) == ["가", "", "나"]


def test_line_block_and_definition_list():
    header, _, paragraphs, _ = hwpx_render("| 하나\n| 둘\n\n용어\n:   정의\n")
    assert hwpx_texts(paragraphs) == ["하나둘", "용어", "정의"]
    assert len(paragraphs[0].findall(".//hp:lineBreak", NS)) == 1
    term_char = paragraphs[1].find("hp:run", NS).get("charPrIDRef")
    assert header.item("charProperties", term_char).find("hh:bold", NS) is not None
    assert abs(header.para_left(paragraphs[2].get("paraPrIDRef")) - 5.0) < 0.01


def test_empty_document_has_one_paragraph():
    _, _, paragraphs, _ = hwpx_render("")
    assert len(paragraphs) == 1 and paragraphs[0].find("hp:run/hp:t", NS) is not None
