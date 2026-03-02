# versed

Arabic-aware PDF text repair. Fixes QCF Quran fonts, Sabon mojibake, and honorific glyphs.

## Install

```bash
pip install versed-repair          # pure Python, zero deps
pip install versed-repair[pdf]     # adds pymupdf for PDF extraction
```

## Quick start

```python
from versed import repair_text, detect_mojibake

# Fix Sabon font mojibake
clean = repair_text("tafß¬l")   # → "tafṣīl"

# Detect encoding corruption
report = detect_mojibake(raw_text)
if report.has_mojibake:
    print(f"Found {report.mojibake_count} corrupted characters")
```

## CLI

```bash
versed repair-text "tafß¬l"           # → tafṣīl
versed repair input.pdf               # extract + repair PDF text
versed detect input.pdf               # mojibake detection report
```

## What it fixes

- **Sabon font mojibake**: `ß→ṣ`, `¬→ī`, `¤→ḥ` (broken ToUnicode CMaps)
- **QCF Quran fonts**: PUA glyph → Arabic mapping for 604 mushaf pages
- **Honorific glyphs**: `ﷺ→صلى الله عليه وسلم`, `ﷻ→سبحانه وتعالى`, etc.

## License

MIT
