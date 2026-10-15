from datetime import date

from mdcast.fields import PageField, Text, keys_in, resolve_fields
from mdcast.report import Codes, Report
from mdcast.templates.schema import deep_merge, load_builtin_default
from mdcast.types import Format


def make(frontmatter, overrides=None):
    report = Report("a.md", Format.MD)
    config = deep_merge(load_builtin_default(), overrides or {})
    return resolve_fields(frontmatter, config, report, today=date(2026, 10, 15)), report


def test_render_mixes_text_and_page_fields():
    f, _ = make({"dept": "전략기획팀"})
    assert f.render("{{dept}} | {{page}} / {{pages}}") == [
        Text("전략기획팀 | "),
        PageField("page"),
        Text(" / "),
        PageField("pages"),
    ]


def test_missing_value_is_blank_with_single_info():
    f, r = make({})
    assert f.render("[{{dept}}]") == [Text("[]")]
    f.render("{{dept}}")
    assert [e.code for e in r.events] == [Codes.FIELD_EMPTY]


def test_defaults_and_today_expansion():
    f, _ = make({}, {"fields": {"defaults": {"security": "대외비", "date": "{{today}}"}, "date_format": "YYYY.MM.DD"}})
    assert f.text("{{security}} {{date}} {{today}}") == "대외비 2026.10.15 2026.10.15"


def test_frontmatter_wins_over_defaults_and_reserved_is_ignored():
    f, r = make({"security": "공개", "page": "99"}, {"fields": {"defaults": {"security": "대외비"}}})
    assert f.text("{{security}}") == "공개"
    assert f.render("{{page}}") == [PageField("page")]
    assert [e.code for e in r.events] == [Codes.FIELD_RESERVED]


def test_list_values_are_joined():
    f, _ = make({"authors": ["김", "이"]})
    assert f.text("{{authors}}") == "김, 이"


def test_blank_frontmatter_falls_through_to_default():
    overrides = {"fields": {"defaults": {"security": "대외비"}}}
    for blank in (None, "", "   "):
        f, r = make({"security": blank}, overrides)
        assert f.text("{{security}}") == "대외비"
        assert r.events == []


def test_blank_frontmatter_without_default_is_empty_with_info():
    f, r = make({"security": None})
    assert f.text("{{security}}") == ""
    assert [e.code for e in r.events] == [Codes.FIELD_EMPTY]


def test_odd_frontmatter_value_types_do_not_raise():
    fm = {
        "count": 3,
        "flag": True,
        "when": date(2026, 10, 15),
        "tags": ["김", None],
        "meta": {"a": 1},
        "nothing": None,
    }
    f, _ = make(fm)
    assert f.text("{{count}}|{{flag}}|{{when}}|{{tags}}|{{meta}}|{{nothing}}") == "3|True|2026-10-15|김, ||"


def test_keys_in():
    assert keys_in("{{dept}} - {{ title }} {{page}}") == ["dept", "title", "page"]
