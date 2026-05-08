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

- `PageV..P..` is structural, not visible prose.
- `ms####` and `Milestone####` are source milestones, not visible prose.
- ` + ` is a source separator. It is hidden by default.
- A ` + ` segment becomes `apparatus_note` only when it matches apparatus grammar
  such as `حديث ...`, `أثر ...`, `تنبيه ...`, `قلت ...`, or `قال المحقق ...`.
- Other ` + ` segments remain authorial prose.

## Typography Policy

- Body text may use native paragraph justification.
- Manual tatweel/kashida is optional polish and must never be required for
  correct layout.
- Apparatus notes are never kashida-justified.
- Mixed LTR/RTL runs should be isolated before layout, but isolates must not
  be stored as user-visible word text.

