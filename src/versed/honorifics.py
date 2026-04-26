"""
Text normalizer for Islamic texts.

Handles:
- Honorific symbols (ﷺ ﷻ etc.)
- Hyphenated words (un-hyphenation)
- Transliterations (Arabic equivalents)
- Arabic presentation forms
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import re

from versed._arabic import TextUtils


# Honorific symbol mappings (PUA glyphs from KFGQPCArabicSymbols fonts + standard Unicode)
# Arabic text includes harakat (diacritics) for proper TTS pronunciation
HONORIFIC_SYMBOLS = {
    # === PUA Symbols (Private Use Area - used by KFGQPCArabicSymbols fonts) ===

    # Sallallahu alayhi wasallam (ﷺ) - for Prophet Muhammad
    '\uf067': {
        'unicode': 'ﷺ',
        'arabic': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',  # With harakat
        'transliteration': 'sallallahu alayhi wasallam',
        'abbrev': 'SAW',
        'context': 'prophet',
    },
    # Subhanahu wa ta'ala (ﷻ) - for Allah
    '\uf063': {
        'unicode': 'ﷻ',
        'arabic': 'سُبْحَانَهُ وَتَعَالَى',  # With harakat
        'transliteration': 'subhanahu wa ta\'ala',
        'abbrev': 'SWT',
        'context': 'god',
    },
    # Alayhi/Alayha assalam - for prophets/angels
    '\uf064': {
        'unicode': 'عليه السلام',
        'arabic': 'عَلَيْهِ السَّلَامُ',  # With harakat
        'transliteration': 'alayhi assalam',
        'abbrev': 'AS',
        'context': 'prophet',
    },
    # Radi Allahu anhu - for companions
    '\uf065': {
        'unicode': 'رضي الله عنه',
        'arabic': 'رَضِيَ اللهُ عَنْهُ',  # With harakat
        'transliteration': 'radi allahu anhu',
        'abbrev': 'RA',
        'context': 'companion',
    },
    # Other PUA variants for SAW
    '\uf030': {
        'unicode': 'ﷺ',
        'arabic': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        'transliteration': 'sallallahu alayhi wasallam',
        'abbrev': 'SAW',
        'context': 'prophet',
    },
    '\uf031': {
        'unicode': 'ﷺ',
        'arabic': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        'transliteration': 'sallallahu alayhi wasallam',
        'abbrev': 'SAW',
        'context': 'prophet',
    },
    # Space character in symbol font
    '\uf020': {
        'unicode': ' ',
        'arabic': '',
        'transliteration': '',
        'abbrev': '',
        'context': 'space',
    },

    # === Standard Unicode Honorifics (Arabic Presentation Forms-A block) ===

    # U+FDFA - Arabic Ligature Sallallahou Alayhe Wasallam (ﷺ)
    '\ufdfa': {
        'unicode': 'ﷺ',
        'arabic': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        'transliteration': 'sallallahu alayhi wasallam',
        'abbrev': 'SAW',
        'context': 'prophet',
    },
    # U+FD46 - Arabic Ligature Sallallaahu Alayhi Wa-aalih (variant with آله)
    '\ufd46': {
        'unicode': 'ﷺ',
        'arabic': 'صَلَّى اللهُ عَلَيْهِ وَآلِهِ وَسَلَّمَ',  # With "wa aalihi"
        'transliteration': 'sallallahu alayhi wa aalihi wasallam',
        'abbrev': 'SAW',
        'context': 'prophet',
    },
    # U+FDFB - Arabic Ligature Jallajalalouhou (ﷻ for Allah)
    # Canonical spoken form: "Subhanahu wa Ta'ala" (سُبْحَانَهُ وَتَعَالَى)
    '\ufdfb': {
        'unicode': 'ﷻ',
        'arabic': 'سُبْحَانَهُ وَتَعَالَى',
        'transliteration': 'subhanahu wa ta\'ala',
        'abbrev': 'SWT',
        'context': 'god',
    },
    # Direct ﷻ character (same as U+FDFB)
    'ﷻ': {
        'unicode': 'ﷻ',
        'arabic': 'سُبْحَانَهُ وَتَعَالَى',
        'transliteration': 'subhanahu wa ta\'ala',
        'abbrev': 'SWT',
        'context': 'god',
    },
    # Direct ﷺ character (same as U+FDFA)
    'ﷺ': {
        'unicode': 'ﷺ',
        'arabic': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        'transliteration': 'sallallahu alayhi wasallam',
        'abbrev': 'SAW',
        'context': 'prophet',
    },
}


def _normalize_translit_key(text: str) -> str:
    """Normalize transliteration keys for consistent lookup."""
    return TextUtils.normalize(text)


def _load_transliterations() -> Tuple[Dict[str, str], Dict[str, str]]:
    """Load transliterations from the bundled data file."""
    data_path = Path(__file__).parent / "_data" / "transliterations.json"
    if not data_path.exists():
        return {}, {}

    try:
        data = json.loads(data_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}, {}

    words = data.get("words", {})
    prefixes = data.get("prefixes", {})

    normalized_words = {}
    for key, value in words.items():
        norm_key = _normalize_translit_key(key)
        if norm_key:
            normalized_words[norm_key] = value

    normalized_prefixes = {}
    for key, value in prefixes.items():
        norm_key = _normalize_translit_key(key)
        if norm_key:
            normalized_prefixes[norm_key] = value

    return normalized_words, normalized_prefixes


# Minimal fallback transliterations (only used if Claude enrichment unavailable)
TRANSLITERATIONS, TRANSLITERATION_PREFIXES = _load_transliterations()


@dataclass
class NormalizedWord:
    """A normalized word with metadata."""
    original: str           # Original text
    normalized: str         # Cleaned text (unhyphenated, symbols decoded)
    arabic: Optional[str]   # Arabic equivalent if transliteration
    has_honorific: bool     # Contains honorific symbol
    honorific_type: Optional[str]  # 'SAW', 'SWT', 'AS', 'RA'
    is_hyphen_start: bool   # Ends with hyphen (word continues)
    is_hyphen_end: bool     # Continues from previous hyphenated word
    is_transliteration: bool


def decode_honorific(text: str) -> Tuple[str, List[Dict]]:
    """
    Decode honorific symbols in text.

    Returns:
        Tuple of (cleaned_text, list of honorific info dicts)
    """
    honorifics = []
    cleaned = text

    for symbol, info in HONORIFIC_SYMBOLS.items():
        if symbol in cleaned:
            honorifics.append(info)
            # Replace symbol with space (will be handled separately for TTS)
            cleaned = cleaned.replace(symbol, ' ')

    # Clean up multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned, honorifics


# Public alias for decode_honorific — more intuitive name for library users
expand_honorifics = decode_honorific


def find_transliteration(word: str) -> Optional[str]:
    """
    Find Arabic equivalent for a transliterated word.

    Returns Arabic text or None.
    """
    if not word:
        return None

    # Normalize for lookup (robust to punctuation/curly quotes)
    normalized = _normalize_translit_key(word)

    # Direct match
    if normalized in TRANSLITERATIONS:
        return TRANSLITERATIONS[normalized]

    # Check if word contains a transliteration (e.g., "(Al-Jathiyah," )
    for translit, arabic in TRANSLITERATIONS.items():
        if translit and translit in normalized:
            return arabic

    return None


def has_leading_honorific(text: str) -> Tuple[bool, Optional[str], str]:
    """
    Check if text starts with an honorific symbol.

    Returns: (has_honorific, honorific_type, remaining_text)
    """
    for symbol, info in HONORIFIC_SYMBOLS.items():
        if text.startswith(symbol):
            remaining = text[len(symbol):]
            # Check for additional symbols/spaces
            while remaining and remaining[0] in HONORIFIC_SYMBOLS:
                remaining = remaining[1:]
            return True, info.get('abbrev'), remaining.strip()
    return False, None, text


def normalize_words(words: List[Dict]) -> List[NormalizedWord]:
    """
    Normalize a list of word dicts from PDF extraction.

    Handles:
    - Honorific symbols (which may be attached to the NEXT word in PDF extraction)
    - Hyphenation
    - Transliterations
    """
    result = []
    skip_indices = set()

    for i, word in enumerate(words):
        if i in skip_indices:
            continue

        text = word.get('text', '')

        # Check if this word STARTS with an honorific (belongs to previous word)
        has_leading, honorific_type, remaining = has_leading_honorific(text)

        if has_leading:
            # This honorific belongs to the PREVIOUS result
            if result:
                prev = result[-1]
                result[-1] = NormalizedWord(
                    original=prev.original,
                    normalized=prev.normalized,
                    arabic=prev.arabic,
                    has_honorific=True,
                    honorific_type=honorific_type or prev.honorific_type,
                    is_hyphen_start=prev.is_hyphen_start,
                    is_hyphen_end=prev.is_hyphen_end,
                    is_transliteration=prev.is_transliteration,
                )

            # If there's remaining text, process it as a new word
            if remaining:
                text = remaining
            else:
                continue  # Skip this word entirely (just a symbol)

        # Decode any remaining honorifics in the text
        cleaned, honorifics = decode_honorific(text)

        # Check for hyphenation at end of word
        is_hyphen_start = cleaned.endswith('-')
        is_hyphen_end = False

        if is_hyphen_start and i + 1 < len(words):
            # Merge with next word
            next_text = words[i + 1].get('text', '')
            # Check if next word starts with honorific
            next_has_leading, _, next_remaining = has_leading_honorific(next_text)
            if next_has_leading:
                next_text = next_remaining

            next_cleaned, next_honorifics = decode_honorific(next_text)
            cleaned = cleaned.rstrip('-') + next_cleaned
            honorifics.extend(next_honorifics)
            skip_indices.add(i + 1)
            is_hyphen_end = True

        # Check for transliteration
        arabic = find_transliteration(cleaned)

        # Determine honorific type from inline honorifics
        inline_honorific_type = None
        if honorifics:
            for h in honorifics:
                if h.get('abbrev'):
                    inline_honorific_type = h['abbrev']
                    break

        result.append(NormalizedWord(
            original=text,
            normalized=cleaned,
            arabic=arabic,
            has_honorific=bool(honorifics),
            honorific_type=inline_honorific_type,
            is_hyphen_start=is_hyphen_start,
            is_hyphen_end=is_hyphen_end,
            is_transliteration=arabic is not None,
        ))

    return result


def normalize_text(text: str) -> str:
    """
    Quick normalization of text string.

    Decodes honorifics and fixes common issues.
    """
    result = text

    # Decode honorific symbols
    for symbol, info in HONORIFIC_SYMBOLS.items():
        if symbol in result:
            result = result.replace(symbol, info.get('unicode', ' '))

    # Fix hyphenation (simple approach)
    result = re.sub(r'-\s*\n\s*', '', result)  # Line-break hyphens
    result = re.sub(r'(\w)-\s+(\w)', r'\1\2', result)  # Mid-word hyphens

    return result


def annotate_transliterations(text: str) -> str:
    """
    Annotate transliterations inside parentheses with Arabic equivalents.

    Example:
        (hammazan) -> (hammazan هَمَّاز)
        ('ayyaban) -> ('ayyaban عَيَّاب)
    """
    if not text:
        return ""

    def _replace(match: re.Match) -> str:
        inner = match.group(1)
        arabic = find_transliteration(inner)
        if not arabic or arabic in inner:
            return match.group(0)
        return f"({inner} {arabic})"

    return re.sub(r"\(([^)]+)\)", _replace, text)


def get_spoken_text(word: NormalizedWord, expand_honorifics: bool = True) -> str:
    """
    Get the text that should be spoken for TTS.

    Args:
        word: Normalized word
        expand_honorifics: If True, expand SAW/SWT to full Arabic

    Returns:
        Text to speak
    """
    base = word.normalized

    if expand_honorifics and word.has_honorific:
        # Add honorific expansion
        if word.honorific_type == 'SAW':
            base += ' صلى الله عليه وسلم'
        elif word.honorific_type == 'SWT':
            base += ' سبحانه وتعالى'
        elif word.honorific_type == 'AS':
            base += ' عليه السلام'
        elif word.honorific_type == 'RA':
            base += ' رضي الله عنه'

    return base
