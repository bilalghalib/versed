# versed

Local PDF-to-Markdown tooling for Arabic and bilingual texts.

It repairs broken extraction, decodes QCF Quran fonts, classifies pages, and renders semantic Markdown from local PDFs.

## Install

```bash
pip install versed-pdf
pip install versed-pdf[pdf]
pip install versed-pdf[pdf,ocr]
```

## Quick start

```python
from versed import extract_document

result = extract_document("book.pdf", title="Book")
print(result.markdown)
```

## CLI

```bash
versed repair-text "tafß¬l"
versed detect book.pdf
versed classify book.pdf
versed extract book.pdf -o book.md
```

## Public modules

- `versed.repair`: Sabon mojibake repair helpers
- `versed.qcf`: QCF Quran font decoding
- `versed.classify`: local page classification and backend selection
- `versed.routing`: cost-aware routing heuristics
- `versed.layout`: aligned words to semantic blocks
- `versed.markdown`: semantic blocks to Markdown/plain text
- `versed.extract`: end-to-end local extraction

## License

MIT
