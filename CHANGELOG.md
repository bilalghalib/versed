# Changelog

## 1.3.0 (unreleased)

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
  past the bottom margin (regression test added; 1.2.6 overflowed).
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
- Arabic guillemets `«…»` are prose quotations; only `﴿…﴾` marks a Qur'an
  citation.

### Alignment

- New `versed.alignment` package and `versed align` /
  `versed verify-alignment` / `versed alignment-doctor` commands for
  hierarchical Arabic-English alignment (see `docs/ALIGNMENT.md`).
