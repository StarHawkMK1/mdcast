import io
import zipfile

from docx.oxml.ns import qn
from helpers import build, write_template
from lxml import etree

from mdcast.types import Format
from mdcast.writers.docx import write_docx
from mdcast.writers.docx.xml import mm_to_twips


def body_abstracts(data: bytes):
    """The abstractNums behind the numIds the document body uses, in numbering.xml order."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    body = etree.fromstring(archive.read("word/document.xml"))
    root = etree.fromstring(archive.read("word/numbering.xml"))
    used = {n.get(qn("w:val")) for n in body.iter(qn("w:numId"))}
    ids = {
        num.find(qn("w:abstractNumId")).get(qn("w:val"))
        for num in root.findall(qn("w:num"))
        if num.get(qn("w:numId")) in used
    }
    return [a for a in root.findall(qn("w:abstractNum")) if a.get(qn("w:abstractNumId")) in ids]


def abstract_levels(data: bytes):
    result = []
    for abstract in body_abstracts(data):
        levels = []
        for lvl in abstract.findall(qn("w:lvl")):
            fmt = lvl.find(qn("w:numFmt")).get(qn("w:val"))
            text = lvl.find(qn("w:lvlText")).get(qn("w:val"))
            ind = lvl.find(qn("w:pPr")).find(qn("w:ind"))
            fonts = lvl.find(qn("w:rPr"))
            east = fonts.find(qn("w:rFonts")).get(qn("w:eastAsia")) if fonts is not None and fonts.find(qn("w:rFonts")) is not None else None
            levels.append((fmt, text, int(ind.get(qn("w:left"))), east))
        result.append(levels)
    return result


def hangings(data: bytes) -> list[list[tuple[str, int, int]]]:
    """Per body abstractNum: (lvlText, left, hanging) of every level."""
    result = []
    for abstract in body_abstracts(data):
        levels = []
        for lvl in abstract.findall(qn("w:lvl")):
            ind = lvl.find(qn("w:pPr")).find(qn("w:ind"))
            levels.append((lvl.find(qn("w:lvlText")).get(qn("w:val")), int(ind.get(qn("w:left"))), int(ind.get(qn("w:hanging")))))
        result.append(levels)
    return result


def render(tmp_path, md, template=None):
    doc, ctx = build(tmp_path, md, Format.DOCX, template=template)
    return write_docx(doc, ctx)


def test_bullet_levels_use_template_symbols_and_body_font(tmp_path):
    data = render(tmp_path, "- 하나\n    - 둘\n        - 셋\n")
    bullets = [lv for lv in abstract_levels(data) if lv[0][0] == "bullet"]
    assert bullets, "pandoc should create a bullet abstractNum"
    first = bullets[0]
    assert [t for _, t, _, _ in first[:5]] == ["□", "○", "-", "·", "·"]
    assert first[0][3] == "맑은 고딕"
    assert_nesting(hangings(data)[abstract_levels(data).index(first)])


def assert_nesting(levels, indent_mm: float = 5):
    """Each marker starts at least one indent_per_level further and never left of its parent's text."""
    starts = [left - hanging for _, left, hanging in levels]
    assert starts[0] == 0
    for n in range(1, len(levels)):
        assert starts[n] >= mm_to_twips(indent_mm * n) - 1, (n, levels)
        assert starts[n] >= levels[n - 1][1], (n, levels)


def test_nested_markers_start_under_the_parent_text(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nlists: {ordered: ['가.', '(가)', '(1)']}\n")
    data = render(tmp_path, "1. a\n    1. b\n        1. c\n\n<!-- -->\n\n- x\n    - y\n        - z\n", str(tpl))
    found = hangings(data)
    assert len(found) == 2
    for levels in found:
        assert_nesting(levels)


def test_ordered_levels_use_korean_formats(tmp_path):
    data = render(tmp_path, "1. 첫째\n    1. 둘째\n        1. 셋째\n")
    ordered = [lv for lv in abstract_levels(data) if lv[0][0] != "bullet"]
    first = ordered[0]
    assert [(f, t) for f, t, _, _ in first[:3]] == [("decimal", "%1."), ("ganada", "%2."), ("decimal", "%3)")]


def test_custom_patterns(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nlists: {ordered: ['(1)', '①']}\n")
    data = render(tmp_path, "1. a\n    1. b\n        1. c\n", str(tpl))
    ordered = next(lv for lv in abstract_levels(data) if lv[0][0] != "bullet")
    assert [(f, t) for f, t, _, _ in ordered[:3]] == [
        ("decimal", "(%1)"),
        ("decimalEnclosedCircle", "%2"),
        ("decimalEnclosedCircle", "%3"),
    ]


def body_hangings(data: bytes) -> dict[str, int]:
    """lvlText -> hanging (twips), first occurrence over the body abstractNums."""
    out = {}
    for levels in hangings(data):
        for text, _, hanging in levels:
            out.setdefault(text, hanging)
    return out


def test_hanging_fits_the_marker_width(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nlists: {ordered: ['가.', '(가)', '(1)']}\n")
    data = render(tmp_path, "1. a\n    1. b\n        1. c\n", str(tpl))
    ordered = next(lv for lv in hangings(data) if lv[0][0] == "%1.")
    hanging = {text: h for text, _, h in ordered[:3]}
    body_pt = 11
    ga_width = (1 + 0.55) * body_pt * 20  # "가." : one Hangul syllable + an ASCII period, in twips
    assert hanging["%1."] > ga_width + 0.3 * body_pt * 20  # room for a visible gap before the tab
    assert hanging["(%2)"] > hanging["%1."]  # "(가)" is wider than "가."
    assert hanging["(%3)"] > hanging["%1."]  # "(10)" is wider too


def test_bullet_hanging_differs_from_wide_ordered_marker(tmp_path):
    tpl = write_template(tmp_path, "t", "name: t\nlists: {ordered: ['(가)']}\n")
    data = render(tmp_path, "- a\n\n<!-- -->\n\n1. b\n", str(tpl))
    found = body_hangings(data)
    assert found["□"] < found["(%1)"]


def style_linked_reference(path):
    """A reference.docx whose own multi-level list is linked to a paragraph style."""
    import docx
    from docx.enum.style import WD_STYLE_TYPE
    from docx.oxml import parse_xml
    from helpers import make_reference_docx

    make_reference_docx(path)
    document = docx.Document(str(path))
    numbering = document.part.numbering_part.element
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    abstract = parse_xml(
        f'<w:abstractNum {w} w:abstractNumId="900"><w:multiLevelType w:val="multilevel"/>'
        '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="upperRoman"/><w:pStyle w:val="MyOutline"/>'
        '<w:lvlText w:val="제%1장"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="0" w:hanging="0"/></w:pPr></w:lvl>'
        '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="◆"/>'
        '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>'
    )
    nums = numbering.findall(qn("w:num"))
    if nums:
        nums[0].addprevious(abstract)
    else:
        numbering.append(abstract)
    numbering.append(parse_xml(f'<w:num {w} w:numId="900"><w:abstractNumId w:val="900"/></w:num>'))
    style = document.styles.add_style("MyOutline", WD_STYLE_TYPE.PARAGRAPH)
    style.element.get_or_add_pPr().append(
        parse_xml(f'<w:numPr {w}><w:ilvl w:val="0"/><w:numId w:val="900"/></w:numPr>')
    )
    document.save(str(path))
    return path


def test_container_own_style_linked_numbering_is_untouched(tmp_path):
    tpl = tmp_path / "t"
    tpl.mkdir()
    (tpl / "template.yaml").write_text("name: t\n", encoding="utf-8")
    style_linked_reference(tpl / "reference.docx")
    data = render(tmp_path, "- 하나\n    - 둘\n", str(tpl))
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/numbering.xml"))
    own = next(a for a in root.findall(qn("w:abstractNum")) if a.get(qn("w:abstractNumId")) == "900")
    levels = own.findall(qn("w:lvl"))
    assert [lv.find(qn("w:lvlText")).get(qn("w:val")) for lv in levels] == ["제%1장", "◆"]
    assert [lv.find(qn("w:numFmt")).get(qn("w:val")) for lv in levels] == ["upperRoman", "bullet"]
    ind = levels[1].find(qn("w:pPr")).find(qn("w:ind"))
    assert (ind.get(qn("w:left")), ind.get(qn("w:hanging"))) == ("720", "360")
    bullets = [lv for lv in abstract_levels(data) if lv[0][1] == "□"]
    assert bullets, "the body list still gets the template's 개조식 symbols"


def note_abstract_texts(data: bytes, part_name: str = "word/footnotes.xml") -> list[list[str]]:
    """lvlTexts of the abstractNums behind the numIds that ``part_name``'s paragraphs use."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    notes = etree.fromstring(archive.read(part_name))
    root = etree.fromstring(archive.read("word/numbering.xml"))
    used = {n.get(qn("w:val")) for n in notes.iter(qn("w:numId"))}
    ids = {
        num.find(qn("w:abstractNumId")).get(qn("w:val"))
        for num in root.findall(qn("w:num"))
        if num.get(qn("w:numId")) in used
    }
    return [
        [lvl.find(qn("w:lvlText")).get(qn("w:val")) for lvl in a.findall(qn("w:lvl"))]
        for a in root.findall(qn("w:abstractNum"))
        if a.get(qn("w:abstractNumId")) in ids
    ]


def test_list_inside_a_footnote_uses_template_symbols(tmp_path):
    data = render(tmp_path, "본문[^1]\n\n[^1]: 각주\n\n    - 하나\n        - 둘\n")
    assert body_abstracts(data) == [], "the body has no list of its own"
    found = note_abstract_texts(data)
    assert found and found[0][:2] == ["□", "○"]


def test_footnote_list_keeps_container_style_linked_numbering(tmp_path):
    tpl = tmp_path / "t"
    tpl.mkdir()
    (tpl / "template.yaml").write_text("name: t\nlists: {ordered: ['(가)']}\n", encoding="utf-8")
    style_linked_reference(tpl / "reference.docx")
    data = render(tmp_path, "본문[^1]\n\n[^1]: 각주\n\n    1. 하나\n", str(tpl))
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/numbering.xml"))
    own = next(a for a in root.findall(qn("w:abstractNum")) if a.get(qn("w:abstractNumId")) == "900")
    assert [lv.find(qn("w:lvlText")).get(qn("w:val")) for lv in own.findall(qn("w:lvl"))] == ["제%1장", "◆"]
    assert note_abstract_texts(data)[0][0] == "(%1)"
