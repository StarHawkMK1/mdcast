from helpers import hwpx_render, hwpx_texts


def kinds(notices):
    return [(n.kind, n.element) for n in notices.items]


def test_footnotes_are_collected_at_the_end():
    _, shapes, paragraphs, notices = hwpx_render("본문[^1] 둘[^2]\n\n[^1]: 첫 각주\n[^2]: 둘째\n")
    assert hwpx_texts(paragraphs) == ["본문[1] 둘[2]", "[1] 첫 각주", "[2] 둘째"]
    assert paragraphs[1].get("paraPrIDRef") == shapes["footnote"].para
    assert kinds(notices) == [("degraded", "footnote")]


def test_math_keeps_its_latex_in_the_code_look():
    _, _, paragraphs, notices = hwpx_render("식 $x^2$ 끝\n")
    assert hwpx_texts(paragraphs) == ["식 x^2 끝"]
    assert kinds(notices) == [("degraded", "math")]
