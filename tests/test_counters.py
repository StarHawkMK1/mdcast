import pytest

from mdcast.counters import format_counter, parse_pattern, typst_pattern, word_level


@pytest.mark.parametrize(
    ("pattern", "n", "expected"),
    [
        ("1.", 3, "3."),
        ("Ⅰ.", 4, "Ⅳ."),
        ("가.", 2, "나."),
        ("(가)", 14, "(하)"),
        ("(가)", 15, "(15)"),
        ("1)", 10, "10)"),
        ("(ㄱ)", 3, "(ㄷ)"),
        ("①", 2, "②"),
        ("i.", 4, "iv."),
        ("A.", 28, "AB."),
    ],
)
def test_format_counter(pattern, n, expected):
    assert format_counter(pattern, n) == expected


def test_parse_pattern_splits_prefix_and_suffix():
    p = parse_pattern("(가)")
    assert (p.prefix, p.token, p.suffix) == ("(", "가", ")")


def test_parse_pattern_rejects_patterns_without_token():
    with pytest.raises(ValueError):
        parse_pattern("※")


def test_word_level():
    assert word_level("가.", 1) == ("ganada", "%2.")
    assert word_level("(1)", 4) == ("decimal", "(%5)")
    assert word_level("Ⅰ.", 0) == ("upperRoman", "%1.")


def test_typst_pattern():
    assert typst_pattern("Ⅰ.") == "I."
    assert typst_pattern("(가)") == "(가)"
