from helpers import hwpx_render, hwpx_texts


def kinds(notices):
    return [(n.kind, n.element) for n in notices.items]


def test_math_keeps_its_latex_in_the_code_look():
    _, _, paragraphs, notices = hwpx_render("식 $x^2$ 끝\n")
    assert hwpx_texts(paragraphs) == ["식 x^2 끝"]
    assert kinds(notices) == [("degraded", "math")]
