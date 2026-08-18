# Arabic–English alignment

`versed-pdf` can align an Arabic OpenITI mARkdown source with an English
translation supplied as PDF, Markdown, or plain text. It preserves source
structure, paragraphs, and derived sentences as separate objects and emits the
finest correspondence supported by the local evidence.

The aligner records correspondence. It does not decide whether either source
may be published, redistributed, or used commercially.

## What the result means

The recommendation hierarchy is:

1. `sentence`: a variable-size sentence path is locally supported;
2. `paragraph`: the paragraph span is supported but sentence boundaries are not;
3. `region`: a bounded local paragraph span is useful, but exact paragraph
   boundaries are doubtful;
4. `structure`: only the enclosing paired section is justified, or one side is
   an omission/addition.

Every result retains the structural, paragraph, and sentence link tables even
when the recommended display level is coarser. A `score_confidence` is a ranking
score, not a calibrated probability. `uncertainty_radius` tells a consumer how
much neighboring context to show.

## Algorithm

### 1. Prepare both witnesses

- Parse OpenITI mARkdown into headings and paragraphs with stable IDs such as
  `ar:u0003:p0012`.
- Extract an English PDF with the normal `versed-pdf` extraction pipeline, or
  split English text/Markdown into headings and paragraphs.
- Derive sentence IDs beneath their paragraphs; sentence splitting never
  replaces the paragraph source.
- Retain but quarantine known apparatus, explicit footnotes, and Project
  Gutenberg wrappers with `exclude_from_alignment`.

### 2. Pair real structural units when possible

If both witnesses expose a compatible numbered or named spine—chapters,
maqāmas, odes, and similar units—the aligner pairs them monotonically. Equal
counts alone are not treated as proof. When no shared spine exists, the book is
kept as one monotonic search interval; Hayy deliberately exercises this case.

### 3. Discover conservative hard landmarks

Distinctive shared numbers and strong transliterated-name evidence can divide a
large interval into smaller ones. Candidates must be unique enough and must
form an ordered chain. Capitalization alone is never a landmark; that rule
prevents title pages, dedications, and ordinary eighteenth-century capitalized
nouns from pulling the alignment forward.

### 4. Run variable-span monotonic DP

Within every landmark-bounded interval, dynamic programming selects one global
ordered path. It considers:

```text
1:1  1:2  2:1  2:2  1:3  3:1
2:3  3:2  1:4  4:1  1:5  5:1
1:0 omission      0:1 addition
```

Length is a prior, not a boundary rule. Basic mode also uses names and numbers.
The optional semantic scorer adds cross-language similarity. Semantic span
vectors and their similarity matrices are precomputed, so DP lookups are
constant-time instead of rebuilding vectors in every cell.

For semantic runs, strong mutual matches over three-paragraph context windows
become soft waypoints. The aligner interpolates a piecewise-linear expected
position between consecutive waypoints and gently penalizes distance from that
curve. Waypoints guide DP; they never force a `1:1` link, so splits, merges,
omissions, and better local evidence can still win.

### 5. Refine strong paragraph links into sentences

The same monotonic DP runs over the Arabic and English sentences inside a
supported paragraph link. Translators may split, merge, or omit sentences, so
the result can be `1:2`, `2:1`, and so on. Weak sentence evidence causes a
paragraph recommendation; weak paragraph evidence causes a local region
recommendation. The system does not deliberately aim for approximation—it
zooms out only when finer evidence is not justified.

### 6. Surface doubts and permit correction

Every non-trivial doubt is written to `review/queue.jsonl` with a stable review
ID, priority, source IDs, reason, score, and radius. An optional local Ollama
judge can label a doubt `aligned`, `partial`, `wrong`, or `uncertain`. Its
verdict is provenance only: it does not silently rewrite correspondence.

Human corrections are JSONL records keyed by review ID:

```json
{"review_id":"review:…","action":"accept","note":"Checked against scan page 31."}
{"review_id":"review:…","action":"replace","note":"Boundary begins one paragraph later.","resolution":"paragraph","english_ids":["en:u0009:p0031"]}
```

`reject` is also supported. Re-run with `--corrections`. Review IDs incorporate
both source hashes, so stale edits fail. Bundle construction asserts that
paragraph and sentence links—and corrections—remain inside their paired
structural units.

## Compute profiles

The deterministic core has no model dependency.

| Profile | Evidence | Intended use |
| --- | --- | --- |
| Basic | length, numbers, conservative names | quick baseline; expect more region fallbacks |
| Balanced | multilingual embeddings for paragraph DP | recommended first corpus pass |
| Thorough | paragraph and sentence embeddings | slower sentence refinement on capable computers |
| Experimental review | either profile plus an explicitly selected Ollama judge | audits doubtful links without overwriting them |

Run `versed alignment-doctor` to inspect memory, optional runtimes, and already
installed Ollama models. It recommends an embedding profile but does not
recommend an LLM judge merely because one fits in memory. Every model and
profile remains explicitly overridable.

MiniLM is not part of the core algorithm. The current default semantic backend,
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, is a small,
replaceable cross-language retrieval scorer. It earned an optional place because
the names/numbers/length baseline lost all seven Hayy audit regions, while the
semantic run recovered all seven inside the local buffer. A future backend can
implement the same scorer interface without changing bundle semantics.

## Commands

Basic, dependency-free text alignment:

```bash
versed align 0581IbnTufayl.HayyIbnYaqzan ockley.txt \
  --output hayy.alignment.zip
```

English PDF input with OCR when needed:

```bash
versed align 0581IbnTufayl.HayyIbnYaqzan ockley.pdf \
  --allow-ocr --output hayy.alignment.zip
```

Balanced semantic run:

```bash
pip install 'versed-pdf[semantic]'
versed align arabic.mARkdown english.txt \
  --semantic-model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
  --output aligned.zip
```

Add `--semantic-sentences` for the thorough profile. Add
`--semantic-local-only` when a run must refuse uncached model downloads.

Experimentally audit doubts with an already-installed local model:

```bash
versed align arabic.mARkdown english.txt \
  --semantic-model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
  --ollama-judge YOUR_CALIBRATED_MODEL \
  --output reviewed.zip
```

Score against stable-ID sentence gold or passage-text region gold:

```bash
versed align arabic.mARkdown english.txt --gold gold.jsonl --output scored.zip
```

Verify bundle membership, sizes, identities, and checksums without extracting:

```bash
versed verify-alignment scored.zip
```

## Portable bundle

The deterministic ZIP contains:

```text
manifest.json
documents/ar.structures.jsonl
documents/en.structures.jsonl
documents/ar.sentences.jsonl
documents/en.sentences.jsonl
alignments/structural.jsonl
alignments/paragraphs.jsonl
alignments/sentences.jsonl
alignments/recommended.jsonl
review/queue.jsonl
review/README.txt
reports/diagnostics.json
reports/accuracy.json
README.txt
```

All payloads are checksummed. Bundle identity includes both source hashes and
all payload hashes. Coverage is reported as a diagnostic and is never presented
as accuracy; accuracy remains `unscored` unless independent gold is supplied.

## Hayy corpus test

Inputs:

- OpenITI `0581IbnTufayl.HayyIbnYaqzan`;
- Simon Ockley's English text, 120 numbered narrative sections;
- seven existing passage-region judgments.

Balanced mode completed locally on an M2/16 GB Mac in under one minute after
semantic span lookup was optimized.

| Metric | Result |
| --- | ---: |
| Gold regions mapped | 7 / 7 |
| Exact paragraph span | 3 / 7 (42.9%) |
| Within ±1 paragraph | 7 / 7 |
| Within ±2 paragraphs | 7 / 7 |
| Correct local paragraph region | 7 / 7 |
| Catastrophic misses | 0 / 7 |
| Gold-region recall | 1.000 |
| Mean span precision | 0.771 |

The seven regions are not independent sentence gold: they originated as
length-partition proposals and were later content-adjudicated. They are useful
regression regions, not evidence that arbitrary books have 100% accuracy.

Three examples were selected with seed `20260818`:

| Gold region | Arabic opening | Predicted English opening | Outcome |
| --- | --- | --- | --- |
| §§22–23 | `فصار عنده الجسد كله خسيسا…` | “Upon this the whole Body seem'd…” | within ±1; recall 1.0, precision .667 |
| §§25–27 | `وكان من جملة ما القى فيها…` | “Amongst other things which he put in…” | exact; recall 1.0, precision 1.0 |
| §§30–32 | `فان خرج هذا الروح بجملته…` | “Thus far had his Observations brought him…” | deliberately broad region; recall 1.0, precision .429 |

The third example is why both recall and matched-span precision are reported.
A broad span can contain the answer while still being a poor exact boundary.

## Review and limitations

The architecture is sound for the intended product because it is monotonic,
hierarchical, source-addressable, model-optional, and explicit about doubt. The
hard-anchor policy and structural clamps prevent the two most damaging failure
modes: drift caused by false names and links crossing section boundaries.

Known limitations remain:

- scores are not calibrated probabilities;
- sentence splitting is rule-based and historical punctuation is irregular;
- PDF layout/OCR errors can dominate alignment quality;
- prose without shared headings or semantic evidence may only justify regions;
- a local LLM reviewer currently audits links but does not autonomously apply
  boundary changes;
- the tested local 2.6B and 4.3B models did not discriminate Hayy hard
  negatives: each scored 7/14 as pair classifiers and 3/7 as three-way
  candidate choosers, so neither is a recommended default judge;
- Hayy's seven regression regions are small and partly derived from the same
  source partition, so more independent gold across genres is required.

The next corpus-level quality work is therefore evaluation, not a new core
algorithm: run diverse books, stratify by structural spine and source quality,
label random and low-confidence samples, and tune thresholds at matched span
precision.
