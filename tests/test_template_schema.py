from pathlib import Path

from mdcast.report import Codes, Report
from mdcast.templates.schema import (
    deep_merge,
    load_builtin_default,
    load_yaml,
    sanitize,
    validate_against,
)
from mdcast.types import Format


def new_report() -> Report:
    return Report("t", Format.MD)


def codes(report: Report) -> list[str]:
    return [e.code for e in report.events]


def test_default_validates_against_itself_cleanly():
    default = load_builtin_default()
    r = new_report()
    assert validate_against(default, default, r) == default
    assert sanitize(default, default, r) == default
    assert r.events == []


def test_unknown_key_dropped_with_warning():
    r = new_report()
    clean = validate_against({"pagee": {}, "page": {"size": "A3"}}, load_builtin_default(), r)
    assert "pagee" not in clean and clean["page"]["size"] == "A3"
    assert codes(r) == [Codes.TEMPLATE_INVALID]


def test_wrong_type_dropped_with_warning():
    r = new_report()
    clean = validate_against({"page": "A4", "lists": {"bullet": "□"}}, load_builtin_default(), r)
    assert "page" not in clean
    assert "bullet" not in clean["lists"]
    assert codes(r) == [Codes.TEMPLATE_INVALID, Codes.TEMPLATE_INVALID]


def test_free_form_sections_accept_anything():
    r = new_report()
    user = {"tables": {"variants": {"plain": {"header": {"background": None}}}}, "fields": {"defaults": {"dept": "기획"}}}
    assert validate_against(user, load_builtin_default(), r) == user
    assert r.events == []


def test_deep_merge_replaces_lists_and_merges_dicts():
    base = {"a": {"x": 1, "y": [1, 2]}, "b": 1}
    out = deep_merge(base, {"a": {"y": [3]}, "c": 2})
    assert out == {"a": {"x": 1, "y": [3]}, "b": 1, "c": 2}
    assert base["a"]["y"] == [1, 2]


def test_sanitize_replaces_bad_values_with_defaults():
    default = load_builtin_default()
    config = deep_merge(default, {
        "page": {"size": "A9", "margin": {"top": "2px"}},
        "elements": {"heading1": {"color": "navy", "size": "big"}},
        "tables": {"header": {"align": "middle"}},
        "lists": {"ordered": ["1.", "※"]},
    })
    r = new_report()
    clean = sanitize(config, default, r)
    assert clean["page"]["size"] == "A4"
    assert clean["page"]["margin"]["top"] == "20mm"
    assert clean["elements"]["heading1"]["color"] == "#1F3864"
    assert clean["elements"]["heading1"]["size"] == "16pt"
    assert clean["tables"]["header"]["align"] == "center"
    assert clean["lists"]["ordered"] == default["lists"]["ordered"]
    assert codes(r).count(Codes.TEMPLATE_INVALID) == 6


def test_sanitize_deletes_bad_value_without_default():
    default = load_builtin_default()
    config = deep_merge(default, {"tables": {"variants": {"plain": {"header": {"background": "zzz"}}}}})
    r = new_report()
    clean = sanitize(config, default, r)
    assert "background" not in clean["tables"]["variants"]["plain"]["header"]


def test_load_yaml_reports_broken_file(tmp_path: Path):
    p = tmp_path / "template.yaml"
    p.write_text("page: [unclosed", encoding="utf-8")
    r = new_report()
    assert load_yaml(p, r) == {}
    assert codes(r) == [Codes.TEMPLATE_INVALID]


# --- Controller ruling I1: no-reject hardening ---


def _validate(user: dict) -> tuple[dict, Report]:
    r = new_report()
    return validate_against(user, load_builtin_default(), r), r


def test_null_dropped_where_not_nullable():
    cases = [
        ({"page": {"margin": {"top": None}}}, lambda c: c["page"]["margin"]),
        ({"fonts": {"body": None}}, lambda c: c["fonts"]),
        ({"elements": {"body": None}}, lambda c: c["elements"]),
        ({"header": {"center": None}}, lambda c: c["header"]),
    ]
    for user, getter in cases:
        clean, r = _validate(user)
        assert codes(r) == [Codes.TEMPLATE_INVALID]
        assert getter(clean) == {}


def test_null_kept_where_nullable():
    user = {
        "tables": {"body": {"zebra": None}, "first_column": {"background": None}},
        "elements": {"heading1": {"color": None}, "body": {"bold": None}},
        "header": {"logo": None},
        "extends": None,
    }
    clean, r = _validate(user)
    assert r.events == []
    assert clean["tables"]["body"] == {"zebra": None}
    assert clean["elements"]["heading1"] == {"color": None}
    assert clean["header"]["logo"] is None


def test_number_becomes_string_where_default_is_string():
    clean, r = _validate({"header": {"center": 2026}, "tables": {"caption": {"format": 1}}})
    assert r.events == []
    assert clean["header"]["center"] == "2026"
    assert clean["tables"]["caption"]["format"] == "1"


def test_non_bool_dropped_for_boolean_keys():
    clean, r = _validate({
        "elements": {"body": {"italic": 1}, "heading1": {"keep_with_next": "yes"}},
        "tables": {"header": {"repeat": 0}, "variants": {"v": {"header": {"bold": "x"}}}},
        "layout": {"page_break": {"skip_first": 1}},
    })
    assert codes(r) == [Codes.TEMPLATE_INVALID] * 5
    assert clean["elements"]["body"] == {}
    assert clean["tables"]["variants"]["v"]["header"] == {}


def test_open_mapping_values_checked_like_non_variant_keys():
    default = load_builtin_default()
    r = new_report()
    clean = validate_against(
        {"tables": {"variants": {"v": {"header": {"background": "#FFF", "align": {"x": 1}}, "bogus": 1}}}}, default, r
    )
    assert clean["tables"]["variants"]["v"] == {"header": {"background": "#FFF"}}
    assert codes(r) == [Codes.TEMPLATE_INVALID] * 2
    config = deep_merge(default, {"tables": {"variants": {"v": {"header": {"align": "bad", "background": "zzz"}}}}})
    r2 = new_report()
    out = sanitize(config, default, r2)
    assert out["tables"]["variants"]["v"]["header"] == {}
    assert codes(r2) == [Codes.TEMPLATE_INVALID] * 2


def test_structured_value_in_scalar_slot_dropped():
    clean, r = _validate({"elements": {"body": {"indent_left": {"a": 1}, "size": ["x"]}}})
    assert clean["elements"]["body"] == {}
    assert codes(r) == [Codes.TEMPLATE_INVALID] * 2


def test_sanitize_rejects_non_finite_bad_format_and_bad_margins():
    default = load_builtin_default()
    config = deep_merge(default, {
        "elements": {"body": {"line_height": float("nan")}},
        "tables": {"caption": {"format": "<표 {n} {oops}>"}},
        "fonts": {"body": {"family": ""}},
        "page": {"margin": {"left": "150mm", "right": "150mm"}},
        "layout": {"page_break": {"before": ["h1", "h9"]}},
    })
    r = new_report()
    clean = sanitize(config, default, r)
    assert clean["elements"]["body"]["line_height"] == "180%"
    assert clean["tables"]["caption"]["format"] == "<표 {n}> {text}"
    assert clean["fonts"]["body"]["family"] == "맑은 고딕"
    assert clean["page"]["margin"] == default["page"]["margin"]
    assert clean["layout"]["page_break"]["before"] == []
    assert codes(r).count(Codes.TEMPLATE_INVALID) == 5


def test_logo_mapping_validated():
    default = load_builtin_default()
    r = new_report()
    ok = validate_against({"header": {"logo": {"file": "a.png", "position": "left", "height": "8mm"}}}, default, r)
    assert ok["header"]["logo"]["file"] == "a.png" and r.events == []
    r2 = new_report()
    bad = validate_against({"header": {"logo": {"position": "left"}}}, default, r2)
    assert "logo" not in bad["header"] and codes(r2) == [Codes.TEMPLATE_INVALID]
    r3 = new_report()
    cfg = sanitize(deep_merge(default, ok), default, r3)
    assert cfg["header"]["logo"]["height"] == "8mm" and r3.events == []


def test_builtin_line_heights_are_all_set():
    default = load_builtin_default()
    expected = {f"heading{i}": "130%" for i in range(1, 7)} | {
        "body": "180%", "quote": "180%", "code": "160%", "caption": "130%", "footnote": "130%",
    }
    assert {k: v["line_height"] for k, v in default["elements"].items()} == expected
    assert default["tables"]["line_height"] == "130%"


def test_table_line_height_validates_and_variants_may_override():
    default = load_builtin_default()
    r = new_report()
    clean = validate_against(
        {"tables": {"line_height": "150%", "variants": {"dense": {"line_height": "100%"}}}}, default, r
    )
    assert clean["tables"]["line_height"] == "150%"
    assert clean["tables"]["variants"]["dense"]["line_height"] == "100%"
    assert codes(r) == []
    config = deep_merge(default, {"tables": {"line_height": "-5%"}})
    r = new_report()
    assert sanitize(config, default, r)["tables"]["line_height"] == "130%"
    assert codes(r) == [Codes.TEMPLATE_INVALID]
