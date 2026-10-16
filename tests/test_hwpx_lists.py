from helpers import HWPX_NS as NS
from helpers import hwpx_render, hwpx_settings, hwpx_texts

from mdcast.hwpx.section import hanging_mm
from mdcast.hwpx.units import para_unit


def margin(header, paragraph, name):
    para = header.item("paraProperties", paragraph.get("paraPrIDRef"))
    return int(para.find(f"hh:margin/hc:{name}", NS).get("value"))


def test_bullet_marker_tab_and_hanging_indent():
    header, _, paragraphs, _ = hwpx_render("- 하나\n- 둘\n")
    assert hwpx_texts(paragraphs) == ["□하나", "□둘"]
    first = paragraphs[0]
    assert first.find("hp:run/hp:t/hp:tab", NS) is not None
    assert margin(header, first, "left") == 0
    assert margin(header, first, "intent") == -para_unit(hanging_mm(["□"], 11))
    assert header.item("paraProperties", first.get("paraPrIDRef")).get("tabPrIDRef") == "1"


def test_ordered_markers_count_from_the_list_start():
    _, _, paragraphs, _ = hwpx_render("3. 셋\n4. 넷\n")
    assert hwpx_texts(paragraphs) == ["3.셋", "4.넷"]


def test_hanging_holds_the_widest_marker():
    settings = hwpx_settings(list_marker=lambda ordered, level, n: f"({n})" if ordered else "-")
    header, _, paragraphs, _ = hwpx_render("1. 가\n", settings)
    widest = hanging_mm([f"({n})" for n in range(1, 11)], 11)
    assert margin(header, paragraphs[0], "intent") == -para_unit(widest)


def test_nested_marker_never_left_of_the_parent_text():
    header, _, paragraphs, _ = hwpx_render("- 하나\n    - 둘\n")
    parent_text = hanging_mm(["□"], 11)
    expected = max(5.0, parent_text)
    assert margin(header, paragraphs[1], "left") == para_unit(expected)
    assert hwpx_texts(paragraphs)[1] == "○둘"


def test_tight_items_have_no_gaps_loose_items_keep_the_body_gaps():
    header, _, tight, _ = hwpx_render("- 하나\n- 둘\n")
    assert margin(header, tight[0], "next") == 0
    header, _, loose, _ = hwpx_render("- 하나\n\n- 둘\n")
    assert margin(header, loose[0], "next") == para_unit(4 * 25.4 / 72)


def test_second_paragraph_of_an_item_aligns_with_its_text():
    header, _, paragraphs, _ = hwpx_render("- 하나\n\n    이어지는 문단\n")
    assert margin(header, paragraphs[1], "left") == para_unit(hanging_mm(["□"], 11))
    assert margin(header, paragraphs[1], "intent") == 0


def test_item_starting_with_code_block():
    header, shapes, paragraphs, _ = hwpx_render("-   ```\n    코드\n    ```\n")
    assert hwpx_texts(paragraphs) == ["□", "코드"]
    code_left = header.para_left(paragraphs[1].get("paraPrIDRef"))
    assert abs(code_left - (hanging_mm(["□"], 11) + 2.0)) < 0.01  # item text + code padding


def test_list_inside_quote():
    header, _, paragraphs, _ = hwpx_render("> - 하나\n>     - 둘\n")
    first, second = paragraphs
    assert margin(header, first, "left") == para_unit(5.0)  # quote indent
    assert margin(header, second, "left") == para_unit(max(10.0, 5.0 + hanging_mm(["□"], 11)))
