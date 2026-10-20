// mdcast built-in PDF layout library.
// Contract (a custom pdf.typ must provide the same names):
//   conf(cfg, doc)                      -> page/text/element rules for the whole document
//   mdcast-table(cfg, name, head, body) -> per-table styling wrapper
//   horizontalrule                      -> used by pandoc's typst writer for `---`
// Line heights: cfg.elements.<el>.line_height and cfg.tables.<name>.line_height are ratios of the
// font size (1.6 = 160%): every line box is that tall and paragraphs set no extra leading.

#let horizontalrule = line(length: 100%, stroke: 0.5pt)

#let _none-or(v, f) = if v == none { none } else { f(v) }

#let _segments(segs) = {
  for s in segs {
    if s.t == "text" { s.v }
    else if s.t == "page" { context counter(page).display() }
    else if s.t == "pages" { context str(counter(page).final().first()) }
  }
}

#let _slots(spec) = {
  if spec == none { return none }
  let row = grid(
    columns: (1fr, auto, 1fr),
    align(left, _segments(spec.left)),
    align(center, _segments(spec.center)),
    align(right, _segments(spec.right)),
  )
  if spec.line == "below" { stack(spacing: 1.5mm, row, line(length: 100%, stroke: 0.5pt)) }
  else if spec.line == "above" { stack(spacing: 1.5mm, line(length: 100%, stroke: 0.5pt), row) }
  else { row }
}

#let _text-args(e) = {
  let d = (:)
  if e.at("size", default: none) != none { d.insert("size", e.size * 1pt) }
  if e.at("bold", default: none) != none { d.insert("weight", if e.bold { "bold" } else { "regular" }) }
  if e.at("italic", default: none) != none { d.insert("style", if e.italic { "italic" } else { "normal" }) }
  if e.at("color", default: none) != none { d.insert("fill", rgb(e.color)) }
  d
}

// A line box exactly r em tall (half the extra above, half below), so the line pitch and a
// paragraph's height are r × the font size, like Word's "exact" line spacing.
#let _lines(r) = (
  top-edge: (0.8 + (r - 1) / 2) * 1em,
  bottom-edge: -(0.2 + (r - 1) / 2) * 1em,
)

#let mdcast-table(cfg, name, head, body) = {
  let t = cfg.tables.at(name, default: cfg.tables.at("_default"))
  let inner = t.border.width * 1pt + rgb(t.border.color)
  let outer = t.border_outer.width * 1pt + rgb(t.border_outer.color)
  set text(size: t.font_size * 1pt, .._lines(t.line_height))
  set par(spacing: 0pt)  // no gap between paragraphs in a cell, as in the docx cells
  set table.header(repeat: t.header.repeat)
  set table(
    inset: t.cell_padding * 1mm,
    stroke: inner,
    fill: (x, y) => {
      if y < head { _none-or(t.header.background, rgb) }
      else if x == 0 and t.first_column.background != none { rgb(t.first_column.background) }
      else if t.body.zebra != none and calc.odd(y - head) { rgb(t.body.zebra) }
      else { none }
    },
  )
  // breakable so long tables flow onto the next pages (header rows repeat); the measured
  // width keeps the outer border hugging an auto-width table. The inner block keeps the
  // available width as the base of percentage columns, or they would shrink a second time.
  show table: it => layout(size => block(
    breakable: true, stroke: outer, width: measure(it, width: size.width).width,
    block(width: size.width, it)))
  body
}

#let conf(cfg, doc) = {
  let el = cfg.elements
  set document(title: cfg.document.title, keywords: cfg.document.keywords)
  set page(
    width: cfg.page.width * 1mm,
    height: cfg.page.height * 1mm,
    margin: (
      top: cfg.page.margin.top * 1mm,
      bottom: cfg.page.margin.bottom * 1mm,
      left: cfg.page.margin.left * 1mm,
      right: cfg.page.margin.right * 1mm,
    ),
    header: _slots(cfg.header),
    footer: _slots(cfg.footer),
  )
  set text(font: cfg.fonts.body, lang: "ko", .._text-args(el.body), .._lines(el.body.line_height))
  set par(
    leading: 0em,
    spacing: el.body.space_after * 1pt,
    justify: el.body.align == "justify",
  )
  set list(marker: cfg.lists.bullet.map(m => [#m]), indent: cfg.lists.indent * 1mm)
  set enum(
    full: true,
    indent: cfg.lists.indent * 1mm,
    numbering: (..n) => {
      let lv = n.pos().len()
      let pats = cfg.lists.ordered
      numbering(pats.at(calc.min(lv, pats.len()) - 1), n.pos().last())
    },
  )
  set figure(numbering: none)
  show figure.where(kind: table): set block(breakable: true)
  show figure.where(kind: table): set figure.caption(
    position: if cfg.tables.at("_default").caption.position == "below" { bottom } else { top })
  show figure.where(kind: image): set figure.caption(
    position: if cfg.figures.caption.position == "above" { top } else { bottom })
  show figure.caption: set text(.._text-args(el.caption), .._lines(el.caption.line_height))
  show heading: set text(font: cfg.fonts.heading)
  show raw: set text(font: cfg.fonts.code)
  show raw.where(block: true): it => block(
    width: 100%,
    inset: 2mm,
    fill: _none-or(el.code.background, rgb),
    text(.._text-args(el.code), .._lines(el.code.line_height), it),
  )
  show quote.where(block: true): it => block(
    inset: (left: el.quote.indent_left * 1mm),
    text(.._text-args(el.quote), .._lines(el.quote.line_height), it.body),
  )
  show footnote.entry: set text(.._text-args(el.footnote), .._lines(el.footnote.line_height))
  let doc = doc
  for lv in range(1, 7) {
    let e = el.at("heading" + str(lv))
    doc = {
      show heading.where(level: lv): set text(.._text-args(e), .._lines(e.line_height))
      show heading.where(level: lv): set block(above: e.space_before * 1pt, below: e.space_after * 1pt)
      doc
    }
  }
  doc
}
