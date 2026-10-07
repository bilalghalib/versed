# OpenITI Typesetter Design

The typesetter should render OpenITI mARkdown through a semantic layout model,
not directly from raw source lines.

## Pipeline

1. Normalize source lines without losing structural markers.
2. Parse with the upstream OpenITI parser where possible.
3. Convert parser output into ordered layout blocks.
4. Render each block type with its own typography.

## Layout Blocks

- `page_reference`: source page marker, rendered marginally.
- `paragraph`: authorial prose.
- `apparatus_note`: editorial/takhrij/source apparatus, rendered smaller and muted.
- `invocation`, `praise`, `quran_citation`, `verse_pair`, `verse_line`: semantic text.
- headings and special OpenITI context tags: rendered according to hierarchy.

## Marker Policy

The reference is the OpenITI mARkdown scheme
(https://github.com/OpenITI/mARkdown_scheme; prose at
https://maximromanov.github.io/mARkdown/). `tests/test_openiti_parser.py`
cites the scheme category for each conformance case.

- `PageV..P..` is structural, not visible prose.
- `ms####` and `Milestone####` are source milestones, not visible prose.
- ` + ` is a source separator. It is hidden by default.
- A ` + ` segment becomes `apparatus_note` only when it matches apparatus grammar
  such as `حديث ...`, `أثر ...`, `تنبيه ...`, `قلت ...`, or `قال المحقق ...`.
- Other ` + ` segments remain authorial prose.
- Shamela-style verse lines (`# % A % B % % 3`, with `~~` continuations) are
  split before the upstream parser sees them: `%`-delimited segments become
  hemistichs paired in source order, and a purely numeric segment becomes the
  verse's `meta["verse_number"]`, printed in the margin, never a hemistich.

## Typography Policy

- Body text may use native paragraph justification.
- Manual tatweel/kashida is optional polish and must never be required for
  correct layout.
- Apparatus notes are never kashida-justified.
- Mixed LTR/RTL runs should be isolated before layout, but isolates must not
  be stored as user-visible word text.

## Invariants

- No source text is dropped. An apparatus note longer than the space left on
  a page is cut at a word boundary and continues on the next page; notes still
  pending after the last body line get notes-only pages.
- The word stream (`word_coordinates`) names source words only, in source
  order. Entry markers, labels, ordinal digit forms and other decoration get
  no box; a word broken across lines or pages keeps one box under its source
  spelling; synthetic kashida tatweel never appears in it.
- Body pages stay Cairo vector outlines, stored once per distinct glyph
  (font, glyph id, colour) as a Form XObject and placed with `cm` + `Do` at
  the positions Pango/HarfBuzz shaped. An invisible text layer (one glyph
  per character, visual order, ToUnicode to the source character) makes them
  copyable and searchable; synthetic tatweel and bidi isolates are excluded.
