"""
Font-aware encoding repair for Type1 fonts with broken ToUnicode CMaps.

Currently handles:
- SabondiexPlain / SabondiacriticRoman (MacRomanEncoding transliteration diacriticals)

Character map verified from original.pdf p1 footer:
  tafß¬l  → tafṣīl   (detail/classification)
  ta¤ß¬l  → taḥṣīl   (acquisition/attainment)
"""

# Font prefixes that trigger repair.
# SabondiexPlain carries the mojibake in the actual PDF we've tested.
# SabondiacriticRoman/Bold/Italic are in the same family but haven't
# shown mojibake in our corpus — include them defensively.
SABON_FONT_PREFIXES = ("Sabondiex", "Sabondiacritic")

# Character repair map — verified from original.pdf p1 (Step 0).
# All three mojibake chars appear only in SabondiexPlain spans.
SABON_CHAR_REPAIR = {
    "\u00df": "\u1e63",  # ß → ṣ  (s with dot below)
    "\u00ac": "\u012b",  # ¬ → ī  (i with macron)
    "\u00a4": "\u1e25",  # ¤ → ḥ  (h with dot below)
}


def is_repairable_font(font_name: str) -> bool:
    """Check if a font name matches a known-broken encoding."""
    return any(font_name.startswith(p) for p in SABON_FONT_PREFIXES)


def repair_text(text: str) -> str:
    """Apply all known encoding repairs to a raw text string.

    Unlike repair_text_for_font(), this doesn't require font knowledge —
    it applies all repair maps unconditionally. Useful for quick fixes
    when you know the text came from a broken font but don't have the
    font name.
    """
    for bad, good in SABON_CHAR_REPAIR.items():
        text = text.replace(bad, good)
    return text


def repair_text_for_font(text: str, font_name: str) -> str:
    """Apply character-level encoding repair for a known-broken font.

    Returns original text if font is not repairable or no changes needed.
    """
    if not is_repairable_font(font_name):
        return text
    result = text
    for bad, good in SABON_CHAR_REPAIR.items():
        result = result.replace(bad, good)
    return result


def extract_repairable_font_spans(page) -> list:
    """Extract span bboxes for fonts with known broken encodings.

    Uses page.get_text("dict") to find spans rendered with Sabon fonts.
    Returns a list of (x0, y0, x1, y1, font_name) tuples for repairable
    fonts only.
    """
    font_spans = []
    try:
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font = span.get("font", "")
                    if is_repairable_font(font):
                        bbox = span.get("bbox", (0, 0, 0, 0))
                        font_spans.append(
                            (bbox[0], bbox[1], bbox[2], bbox[3], font)
                        )
    except Exception:
        pass
    return font_spans


def find_font_for_word(word_x0, word_y0, word_x1, word_y1, font_spans, tolerance=2.0):
    """Find the Sabon font for a word using bbox containment/overlap.

    A word belongs to a span if:
    - word's y-center is within span's y-range (same line)
    - word's x-range overlaps with span's x-range

    When multiple spans match, returns the one with highest horizontal overlap.
    """
    if not font_spans:
        return None
    word_y_center = (word_y0 + word_y1) / 2
    best_font = None
    best_overlap = -1
    for sx0, sy0, sx1, sy1, font in font_spans:
        if word_y_center < sy0 - tolerance or word_y_center > sy1 + tolerance:
            continue
        if word_x1 < sx0 - tolerance or word_x0 > sx1 + tolerance:
            continue
        overlap = min(word_x1, sx1) - max(word_x0, sx0)
        if overlap > best_overlap:
            best_overlap = overlap
            best_font = font
    return best_font


def repair_words_with_font_info(words_raw, font_spans):
    """Apply encoding repair to word tuples based on font spans.

    Args:
        words_raw: list of PyMuPDF word tuples (x0, y0, x1, y1, text, block, line, word)
        font_spans: from extract_repairable_font_spans()

    Returns:
        list of word tuples with text repaired where applicable.
        Tuples are replaced (not mutated) — only text field changes.
    """
    if not font_spans:
        return words_raw

    repaired = []
    for w in words_raw:
        x0, y0, x1, y1 = w[0], w[1], w[2], w[3]
        text = w[4] if len(w) > 4 else ""
        font = find_font_for_word(x0, y0, x1, y1, font_spans)
        if font:
            new_text = repair_text_for_font(text, font)
            if new_text != text:
                w = (x0, y0, x1, y1, new_text) + w[5:]
        repaired.append(w)
    return repaired
