# versed-pdf

**Turn Arabic, English and bilingual PDFs into inspectable text and document structure for reading applications.** Extract Markdown, plain text and structured JSON; repair supported PDF font/character problems; retain native word coordinates when building your own reading pipeline.

Useful for:

- Preparing a PDF for a reader, search index or narration workflow.
- Recovering Arabic/Quran text from supported QCF fonts and repairing known broken Sabon encodings.
- Preserving transliteration marks such as **ā, ī, ū, ḥ and ṣ** where supported font or glyph evidence establishes the intended text.
- Converting parsed OpenITI content to the same document/Markdown formats, or aligning Arabic OpenITI text with an English translation.

This package supplies extraction and preparation tools. Audio synthesis, provider word timings, billing, playback highlighting and automatic page turns are implemented by the separate [Versed application](https://github.com/bilalghalib/versed-app). The example below shows how to preserve the information those systems need.

## Install and extract

Use Python 3.9 or newer. In your Python project:

```sh
uv add 'versed-pdf[pdf]'
uv run versed extract book.pdf -o book.md
uv run versed extract book.pdf --format json -o book.json
```

Or use the Python API:

```python
import json
from pathlib import Path
from versed import extract_document

result = extract_document('book.pdf', title='My book')
Path('book.md').write_text(result.markdown, encoding='utf-8')
Path('book.json').write_text(
    json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8'
)
print(result.pages)  # per-page extraction route and warnings
print(result.stats)
```

`ExtractResult` contains `markdown`, `plain_text`, `document`, `pages`, `stats` and an extraction-engine `version`. The engine version is separate from the installed package version, available through `importlib.metadata.version('versed-pdf')`.

`document` contains text blocks and metadata. Its serialization is **not a complete word-coordinate/timing manifest**. For source word boxes, use `extract_repaired_words(page)` as in the example below.

### Scanned pages

Scans need OCR. Install the OCR extra and the **system Tesseract executable and appropriate language data**:

```sh
uv add 'versed-pdf[pdf,ocr]'
uv run versed extract scan.pdf --allow-ocr -o scan.md
```

The public convenience OCR path calls Tesseract with its default language (English); it currently exposes no language-selection argument. It produces text, not reliable original-PDF word coordinates. Review its language coverage, reading order and page warnings before narration; use a separately configured OCR/word-location pipeline for Arabic scans and precise PDF highlighting. It does not invoke Versed's hosted vision OCR or paid providers automatically.

## What the macron fix changes

Some PDFs draw a macron as a separate glyph. A printed **Majnūn** can therefore extract as `Majn¯un`. Since **1.3.4**, the native repair helper composes the vowel and mark when the raw characters agree with the source word and their geometry identifies one adjacent vowel under the macron.

The repair preserves the word's bounding box and source block/line/word identifiers. Ambiguous marks remain unchanged. It does not guess underdots from periods, turn ordinary German `ß` into `ṣ`, or rewrite unaccented Turkish `ı`. Known Sabon encoding repairs remain font-specific in the extraction path.

The **1.3.5** release adds this guide and the tested reading-chunk example; its extraction behavior is unchanged from 1.3.4. Package version metadata is synchronized in this release.

## PDF → reviewable reading chunks → audio

A narration chunk should follow spoken content, while each word still points back to its page. **A page break alone is not a sentence boundary.** For example:

```text
page 1: The sentence continues
page 2: on the next page.

one chunk: The sentence continues on the next page.
word records: page 1, page 1, page 1, page 2, page 2, page 2, page 2
```

The repository includes a runnable, provider-independent example:

```sh
git clone https://github.com/bilalghalib/versed.git
cd versed
uv run --with 'versed-pdf[pdf]==1.3.5' --no-project \
  python examples/prepare_reading_chunks.py book.pdf reading-chunks.json
```

[Read the example](https://github.com/bilalghalib/versed/blob/main/examples/prepare_reading_chunks.py). It uses the public `extract_repaired_words` helper and writes:

| Field | Purpose |
|---|---|
| `source_sha256`, `package_version` | Bind the manifest to its source PDF and extraction version. |
| `words[].id`, `page`, `bbox`, `source_position` | Identify each extracted word and its original page/rectangle. Page numbers are one-based; rectangles use PyMuPDF page coordinates. |
| `chunks[].text` | Text proposed for a single synthesis request. |
| `chunks[].word_links` | Source-word IDs and character offsets within that exact text. Offsets are Python Unicode character indices, not UTF-8 byte or JavaScript UTF-16 offsets. |
| `boundary`, `needs_review` | Explain punctuation/length/end-of-document splits and require review. |

The example handles **native-text PDFs with reviewed reading order**. It joins across page breaks, recognizes simple English/Arabic end punctuation, and limits chunks to 120 words by default (`--max-words`). It labels forced length splits. It refuses empty/native-unreadable pages and detected QCF or unresolved private-use text rather than silently omitting them.

This is an example, not an automatic semantic narrator. Abbreviations, headings, columns, footnotes, page headers, language changes, verse/poetry boundaries, blank pages and long sentences need a reviewed policy. It does not decode QCF words into a coordinate manifest or perform OCR. Use the higher-level extraction/QCF tools and a reviewed source mapping for those cases. IDs are deterministic for this source and extraction order; preserve the manifest rather than assuming IDs survive arbitrary re-extraction.

### Connect reviewed chunks to a speech engine

1. **Review extraction and routing.** Confirm text, reading order, language and what should be spoken. Keep headings/footnotes/verses distinct where appropriate. Never flatten an entire Markdown export and discard its source mapping.
2. **Send a reviewed chunk to TTS.** Select its voice/language, account for the provider's byte/token limits, and retain the exact submitted text. A multi-page sentence can be one request.
3. **Obtain word timings.** Use provider timestamps or a separate forced aligner. Validate the spoken token sequence against `word_links`; if pronunciation expands a token or changes text, keep an explicit spoken-to-source mapping. Do not assign timestamps to different words by position alone.
4. **Drive the reader from source IDs.** Each timed word resolves to a page and box. Highlight that word and turn the page when playback reaches the first word belonging to the next page. For page-specific audio files, cut the shared recording at mapped word boundaries and rebase timings to each file's start.
5. **Validate before publishing.** Check that all intended source words occur once, timings are monotonic and within the audio, and page boundaries neither omit nor repeat speech. Listen to English and Arabic transitions. The JSON example contains no audio or timestamps and is not proof of alignment quality.

For the production implementation, see the application's [cross-page speech design and verification](https://github.com/bilalghalib/versed-app/blob/main/versed-app/docs/agentic/CROSS_PAGE_SPEECH_2026-10-26.md). That bounded speech-planning/TTS system is separate from this public package.

## OpenITI and bilingual alignment

```python
from versed import build_openiti_markdown

result = build_openiti_markdown({
    'metadata': {'title': 'رسالة'},
    'content': [
        {'type': 'title', 'content': 'رسالة'},
        {'type': 'paragraph', 'content': 'قال المصنف ...'},
    ],
})
print(result.markdown)
```

For Arabic-source/English-translation correspondence:

```sh
uv run versed alignment-doctor
uv run versed align arabic.mARkdown english.pdf -o aligned.zip
uv run versed verify-alignment aligned.zip
```

The [alignment guide](https://github.com/bilalghalib/versed/blob/main/docs/ALIGNMENT.md) explains structural, paragraph and sentence links, uncertainty and review. These are **text-to-text links**, not audio timestamps. Optional semantic models are available with `uv add 'versed-pdf[semantic]'`; deterministic extraction does not download them.

## Limits and quality checks

PDFs may contain broken encodings, incorrect text order, missing text layers or ambiguous glyph positions. OCR can produce fluent but incorrect text, including Arabic citations and diacritics. Inspect warnings and compare representative output with the rendered pages. Word-box coverage is not a measurement of transcription or geometric accuracy. Semantic blocks are heuristics, not verified scholarly annotations.

Useful public modules: `versed.extract`, `versed.repair`, `versed.qcf`, `versed.classify`, `versed.layout`, `versed.markdown`, `versed.openiti` and `versed.alignment`. `versed repair-text` applies explicit repair mappings without PDF font evidence; prefer the font-aware extraction path for documents containing ordinary German/Turkish text.

## License

MIT. Source-document rights remain separate from the software license.
