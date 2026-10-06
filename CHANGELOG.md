# Changelog

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
