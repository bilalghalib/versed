"""
versed — Arabic-aware PDF text repair.

Fixes QCF Quran fonts, Sabon mojibake, and honorific glyphs.

    from versed import repair_text, detect_mojibake

    clean = repair_text("tafß¬l")          # → "tafṣīl"
    report = detect_mojibake(raw_text)      # → MojibakeReport
"""

__version__ = "1.0.0"

from .repair import repair_text, repair_text_for_font, is_repairable_font, SABON_CHAR_REPAIR
from .qcf import QCFDecoder, is_qcf_text, is_qcf_glyph, detect_qcf_regions
from .honorifics import (
    normalize_text, normalize_words, decode_honorific,
    expand_honorifics, HONORIFIC_SYMBOLS, NormalizedWord,
)
from .detect import detect_mojibake, MojibakeReport
