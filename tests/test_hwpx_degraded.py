from helpers import hwpx_render, hwpx_settings, hwpx_texts


def kinds(notices):
    return [(n.kind, n.element) for n in notices.items]


def test_tables_become_row_paragraphs_with_one_notice():
    md = "Table: 요약\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n| c |\n|---|\n| 3 |\n"
    _, shapes, paragraphs, notices = hwpx_render(md)
    assert hwpx_texts(paragraphs) == ["요약", "a | b", "1 | 2", "c", "3"]
    assert paragraphs[0].get("styleIDRef") == shapes["caption"].style
    assert kinds(notices) == [("degraded", "table")]


def test_table_caption_below_when_configured():
    md = "Table: 요약\n\n| a |\n|---|\n| 1 |\n"
    _, _, paragraphs, _ = hwpx_render(md, hwpx_settings(table_caption_above=False))
    assert hwpx_texts(paragraphs) == ["a", "1", "요약"]


def test_images_become_placeholders_and_figure_captions_stay():
    _, shapes, paragraphs, notices = hwpx_render("앞 ![그림](x.png) 뒤\n\n![설명](y.png)\n")
    assert hwpx_texts(paragraphs) == ["앞 [이미지: 그림] 뒤", "[이미지: 설명]", "설명"]
    assert paragraphs[2].get("styleIDRef") == shapes["caption"].style
    assert kinds(notices) == [("degraded", "image")]


def test_footnotes_are_collected_at_the_end():
    _, shapes, paragraphs, notices = hwpx_render("본문[^1] 둘[^2]\n\n[^1]: 첫 각주\n[^2]: 둘째\n")
    assert hwpx_texts(paragraphs) == ["본문[1] 둘[2]", "[1] 첫 각주", "[2] 둘째"]
    assert paragraphs[1].get("paraPrIDRef") == shapes["footnote"].para
    assert kinds(notices) == [("degraded", "footnote")]


def test_math_keeps_its_latex_in_the_code_look():
    _, _, paragraphs, notices = hwpx_render("식 $x^2$ 끝\n")
    assert hwpx_texts(paragraphs) == ["식 x^2 끝"]
    assert kinds(notices) == [("degraded", "math")]
