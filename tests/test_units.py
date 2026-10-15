import pytest

from mdcast.units import normalize_color, page_size_mm, parse_length_mm, parse_pt, parse_ratio


def test_length_units():
    assert parse_length_mm("20mm") == 20
    assert parse_length_mm("2cm") == 20
    assert parse_length_mm("1in") == pytest.approx(25.4)
    assert parse_length_mm("72pt") == pytest.approx(25.4)
    assert parse_length_mm(15) == 15


def test_pt_units():
    assert parse_pt("11pt") == 11
    assert parse_pt(10.5) == 10.5
    assert parse_pt("25.4mm") == pytest.approx(72)


def test_ratio():
    assert parse_ratio("160%") == pytest.approx(1.6)
    assert parse_ratio(1.2) == 1.2
    assert parse_ratio("1.5") == 1.5


@pytest.mark.parametrize("bad", ["abc", "12px", "", True])
def test_bad_lengths_raise(bad):
    with pytest.raises(ValueError):
        parse_length_mm(bad)


def test_colors():
    assert normalize_color("#1f3864") == "1F3864"
    assert normalize_color("abc") == "AABBCC"
    assert normalize_color(None) is None
    with pytest.raises(ValueError):
        normalize_color("#12345")


def test_page_sizes():
    assert page_size_mm("a4", "portrait") == (210.0, 297.0)
    assert page_size_mm("A4", "landscape") == (297.0, 210.0)
