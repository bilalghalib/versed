# Changelog

## 1.3.3 (unreleased)

### OpenITI typesetter

- **Verse and title words get boxes.** `draw_verse_pair` drew both
  hemistichs without word coordinates, and `TITLE` blocks were drawn with
  `track_words=False`, though both are voiced. Verse words are now located
  by source byte span like body text, hemistich A (the right-hand column)
  then B, with `word_index` running on across the block (the order versed-app
  ingestion and the Archive gate expect). Archive gate, timed words boxed,
  1.3.2 -> 1.3.3: IbnSinanKhafaji.Diwan 55 -> 1,603 of 1,607 (all placed
  words; the box ink check passes), IbnTaymiyya.CaqidaWasitiyya 4,521 ->
  4,884 of 4,884; Sakhawi 4,191/4,191 and Tahafut 13,057/13,057 unchanged.
- **Cover text can copy as logical text.** A `cover_renderer` that accepts a
  `paint_layout` keyword receives the body's painter: outline glyphs plus
  the invisible logical text layer. Text drawn with
  `PangoCairo.show_layout` copied as visual-order Arabic and letter-spaced
  Latin ("S AK H AW I"). Renderers without the keyword are called as before.
- **Lines no longer merge in PDFKit.** The invisible text layer sized its
  glyphs from the line height (0.75 x logical height), so a fully
  diacritized line's glyph boxes overlapped its neighbours and PDFKit
  spliced them, with the margin page marker, into one line (Sakhawi p.1).
  It now uses the drawn em size; PyMuPDF, Poppler and PDFKit each give one
  line per drawn line, top to bottom (PDFKit lists the margin markers as
  their own column).
- **Empty source pages share one marker.** Consecutive page markers with no
  main text between them print once as a range (`[ص ٦٣–٦٥]`), instead of
  stacking in one margin spot (Sakhawi, Ibn Taymiyya's `[ص ٥]`...`[ص ١٨]`).
- **Shamela placeholder rows are not drawn.** A paragraph of dots only
  (`. . . . .`, Shamela's mark for omitted page text) is skipped; it still
  counts as a block, so `block_index` values are unchanged.
- The first three items leave the visible page unchanged (Sakhawi at 100
  dpi: all 46 body pages identical; the old cover design differs only by
  antialiasing where its text became outlines). Sizes via the gate, 1.3.2 -> 1.3.3 (with the
  versed-app cover redesign): Sakhawi 1.08 -> 1.15 MB, Diwan 1.34 -> 1.43 MB
  (the embedded word map now holds 1,548 more verse rows), Tahafut 3.20 ->
  3.24 MB, Wasitiyya 0.91 -> 0.96 MB.

## 1.3.2 (unreleased)

### OpenITI typesetter

- **Reading editions are small again, with the same text layer.** 1.3.0 and
  1.3.1 filled a full glyph outline (`layout_path`) for every glyph
  occurrence, so 0902Sakhawi.SirrMaktum's 48-page Archive edition was
  20.8 MB. Each distinct (font, glyph id, colour) is now recorded once as a
  Cairo recording surface, which Cairo writes as one Form XObject and
  places per occurrence with `cm` + `Do`. Positions come from the shaped
  layout (`Pango.Layout.serialize` glyph ids, advances and x/y offsets plus
  the line iterator's run origins), and a test checks they reproduce
  `layout_path` contour for contour, kashida, marks and mixed-direction
  runs included. The page still holds no visible text: the only fonts are
  the invisible semantic layer's, so PyMuPDF, Poppler and PDFKit extraction
  is unchanged (byte-identical on the three books below). The semantic save
  also writes object streams.
- Measured with the versed-app Archive gate (cover, front matter, word map),
  1.3.1 -> 1.3.2: Sakhawi.SirrMaktum 20.8 MB -> 1.25 MB (48 pp),
  IbnSinanKhafaji.Diwan 46.6 MB -> 1.74 MB (117 pp), Ghazali.Tahafut
  94.0 MB -> 4.0 MB (230 pp). Word maps identical; 150 dpi renders differ
  only by antialiasing where joined glyphs overlap (max channel diff 69,
  about 0.01% of samples above 32).

## 1.3.1 (unreleased)

### OpenITI typesetter

- **Mixed-direction text layer.** Glyphs follow UAX #9 visual order of the
  isolate-free line text (resolved by Pango/FriBidi) instead of the drawn
  layout's isolate-level runs. PDFKit now round-trips digits, Arabic-Indic
  digits, `(2)` footnote numbers and embedded Latin titles exactly (in 1.3.0
  it mirrored `(2)` and reordered Latin). Poppler is exact for Arabic and
  `902هـ`; next to a number it puts the separating space on the other side
  (`681بدمشق`), and brackets or marks beside LTR runs move. MuPDF is exact
  for Arabic only. A Chrome-printed PDF of the same text extracts the same
  way in Poppler and MuPDF, so these are reader limits (documented as xfail
  tests).
- **Verse numbers sit in the margin opposite the page markers.** They shared
  the outer margin and overprinted `[ص …]` (0466IbnSinanKhafaji.Diwan).
- **No silent font substitution.** `render_book` raises when Pango would draw
  the theme's body or heading face with another font, or fall back per glyph
  for Arabic. On the build Mac, "Amiri" had been resolving to AlNile and
  DecoType Naskh (a broken Amiri download was an HTML file).

### OpenITI parser

- Every Arabic source word now reaches the block model, in order, for all
  740 OpenITI sources on the Archive (the 1.3.0 parser lost words in 3):
  - text after a line-initial page anchor (`PageV01P023 وتسديدهم…`, 47 words
    in 0711IbnIbrahimCimadDinWasiti.Tadhkira) and after glued anchors
    (`PageV01P298PageV01P300…`, 0625AbuMuhammadIbnRushd.HalYattasilBiCaql);
  - `#NewRec#` and other header lines no longer leak into the body
    (0720IbnCumarKurdi.Juz);
  - folio anchors such as `PageV01P003b` are read as page anchors.
- Canonical `%~%` lines are split locally like the `%` form; a pair with no
  words on one side (OCR noise such as `قدهة 1 %~% 11` in
  0671AbuCabdAllahQurtubi.Asna) stays one verse line, not a fake couplet.
- An inline title (` $ `) inside a `%` verse line is a title, not a verse
  line (0833IbnJazari.DurraMudiyya printed "$ & باب البسملة"); an empty one
  (`% $`, 0795IbnRajabHanbali.KalimatIkhsas) is dropped as markup.
- A verse placeholder merged with neighbouring text by the bridge is still
  substituted instead of printing `VRSDVERSE…`.

## 1.3.0

1.2.7 was bumped on `main` but never tagged or published; its changes ship
here. Everything below is relative to the published 1.2.6.

### OpenITI typesetter

- **Text layer on vector pages.** Body pages are no longer replaced by a
  16-colour 200-DPI PNG. The Cairo vector page is kept and an invisible text
  layer is added: one glyph per character in visual order with a ToUnicode
  map to the source character, and a right-to-left mark (inside an empty
  `/ActualText` span) anchoring each RTL line. Arabic copy/search round-trips
  exactly in PyMuPDF, Poppler `pdftotext` and macOS PDFKit (PDFKit returns an
  invisible U+200F at RTL line ends; Poppler moves the space before `،`/`:`).
  The PDFKit-only reversed proxy text is gone.
- **Word stream names source words only.** Entry markers (`◆`), labels,
  Arabic-Indic ordinal rewrites, title-page text and lacunae no longer get
  word boxes; a token broken across lines or a page split (for example
  `(681ه/1282م)،` broken at the slash) keeps a single box with its source
  spelling; synthetic kashida tatweel is excluded while source tatweel
  (`هـ`) is kept.
- **Apparatus notes are never clipped.** Notes too long for a page continue
  on the next page at a word boundary, and notes still pending at the end
  get notes-only pages. `BookTheme.footnote_max_chars` is no longer used.
- **Paragraphs taller than a page** flow across pages instead of being drawn
  past the bottom margin (regression test added; 1.2.6 overflowed). Page-split
  chunks are no longer re-wrapped: Pango re-breaks some lines laid out alone
  (e.g. around ` ، `), which on `main` still pushed a 28-line chunk to 39 lines
  and off the page (0983IbnMuhammadSahgirAkhdari.MukhtasarFiCibadat).
- Balanced pagination without widows/orphans; mixed-direction Arabic layout
  keeps bracketed references like `(2)` inside their LTR isolate.
- Text-layer fonts fall back across Arial Unicode, SF Arabic, Geeza Pro,
  Amiri, Noto and DejaVu; a letter, mark or digit no font covers raises.

### OpenITI parser

- Shamela-style verse lines `# % A % B % % 3` (with `~~` continuations) are
  split locally: hemistichs pair in source order and a numeric segment
  becomes `Block.meta["verse_number"]` (printed in the margin) instead of the
  second hemistich. Previously the upstream parser turned the first
  hemistich into a paragraph and the verse number into hemistich B.
- Conformance with the OpenITI mARkdown scheme
  (https://github.com/OpenITI/mARkdown_scheme): inline tags are removed and
  their words kept (`@QURS…_BEG/_END`, `@TOP02`-style and manual `@T/@S/@B/@P/@SRC`
  entity tags, `@YB45` year tags, text-reuse and passage ids, `REF##########`,
  open-tagging `@TOP@TOP@…@`); ignore elements (`~!~…~!!~`, `NoteV…N…`,
  `PageWrongV…`, `PageStartV…`, `PageBegV…`, `PageEndV…`, `StartingPageV…`)
  and `#COMMENT#` / `#ENTITIES#` / `#@COMMENT` lines are dropped;
  `### |EDITOR|` / `### |SKIP|` become one `EDITORIAL_SECTION` block (was a
  heading printing "EDITOR|" plus a duplicate note); `#~:cat:` lines become
  `MORPHO_TAG`; the `$BIO_REP$` tag no longer prints.
- Arabic guillemets `«…»` are prose quotations; only `﴿…﴾` marks a Qur'an
  citation.

### Alignment

- New `versed.alignment` package and `versed align` /
  `versed verify-alignment` / `versed alignment-doctor` commands for
  hierarchical Arabic-English alignment (see `docs/ALIGNMENT.md`).
