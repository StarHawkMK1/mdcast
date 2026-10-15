from mdcast.fonts import family_chain, latin_name, missing_primary_fonts, unknown_font_name


def test_aliases():
    assert latin_name("맑은 고딕") == "Malgun Gothic"
    assert latin_name("Pretendard") == "Pretendard"


def test_family_chain_appends_bundled_fallback_once():
    assert family_chain({"family": "맑은 고딕", "fallback": ["Noto Sans KR"]}) == [
        "Malgun Gothic",
        "Noto Sans KR",
    ]
    assert family_chain({"family": "Consolas", "fallback": []}) == ["Consolas", "Noto Sans KR"]


def test_unknown_font_name():
    assert unknown_font_name("unknown font family: malgun gothic") == "malgun gothic"
    assert unknown_font_name("something else") is None


def test_missing_primary_fonts_detects_unknown_family():
    cfg = {"body": {"family": "없는글꼴xyz", "fallback": []}, "code": {"family": "Libertinus Serif"}}
    assert missing_primary_fonts(cfg) == ["없는글꼴xyz"]


def test_missing_primary_fonts_family_with_backslash_is_reported_not_raised():
    cfg = {"body": {"family": "a\\", "fallback": []}}
    assert missing_primary_fonts(cfg) == ["a\\"]


def test_missing_primary_fonts_family_with_newline_is_reported_not_raised():
    cfg = {"body": {"family": "a\nb", "fallback": []}}
    assert missing_primary_fonts(cfg) == ["a\nb"]
