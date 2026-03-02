"""
Arabic text utilities — normalization, detection, similarity.

Internal module used by honorifics.py and detect.py.
Not part of the public API.
"""

import re
import unicodedata
from typing import Dict, Optional


class TextUtils:
    """Text processing utilities."""

    # Arabic character ranges
    ARABIC_PATTERN = re.compile(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]')

    # Punctuation and diacritics to strip
    PUNCTUATION_PATTERN = re.compile(
        r"[\'\"`´′″‹›«»\u2018\u2019\u201C\u201D\u02BC\u2032\u2033.,;:!?()[\]{}،؛؟–—-]"
    )
    DIACRITICS_PATTERN = re.compile(r'[\u064B-\u065F\u0670]')

    # Alef variants (أإآٱ) → bare alef (ا)
    ALEF_VARIANTS = re.compile(r'[أإآٱ]')
    # Zero-width and directional markers to drop
    ZERO_WIDTH_TRANSLATION = str.maketrans({
        "\u200B": "",  # zero width space
        "\u200C": "",  # zero width non-joiner
        "\u200D": "",  # zero width joiner
        "\u2060": "",  # word joiner
        "\uFEFF": "",  # zero width no-break space
        "\u200E": "",  # LRM
        "\u200F": "",  # RLM
    })
    # Common Latin ligatures (extra safety; NFKC should also handle these)
    LIGATURE_TRANSLATION = str.maketrans({
        "\uFB00": "ff",
        "\uFB01": "fi",
        "\uFB02": "fl",
        "\uFB03": "ffi",
        "\uFB04": "ffl",
        "\uFB05": "st",
        "\uFB06": "st",
    })

    @classmethod
    def normalize_arabic(cls, text: str) -> str:
        """
        Normalize Arabic text for comparison/matching.

        - Removes diacritics (tashkeel)
        - Normalizes alef variants to bare alef
        - Normalizes teh marbuta to heh
        - Normalizes alef maksura to yeh
        - Removes tatweel (kashida)
        """
        if not text:
            return ""

        # Remove tashkeel (Arabic diacritics)
        text = cls.DIACRITICS_PATTERN.sub('', text)

        # Normalize alef variants to bare alef
        text = cls.ALEF_VARIANTS.sub('ا', text)

        # Normalize teh marbuta to heh
        text = text.replace('ة', 'ه')

        # Normalize alef maksura to yeh
        text = text.replace('ى', 'ي')

        # Remove tatweel (kashida)
        text = text.replace('\u0640', '')

        return text.strip()

    @classmethod
    def normalize(cls, text: str) -> str:
        """
        Normalize text for matching.

        - Lowercases (for non-Arabic)
        - Strips whitespace
        - Removes punctuation
        - Applies full Arabic normalization (diacritics, alef variants, etc.)
        """
        if not text:
            return ""
        text = unicodedata.normalize("NFKC", text).strip()
        text = text.translate(cls.ZERO_WIDTH_TRANSLATION)
        text = text.translate(cls.LIGATURE_TRANSLATION)
        text = cls.PUNCTUATION_PATTERN.sub("", text)

        # Apply full Arabic normalization
        text = cls.normalize_arabic(text)

        # Lowercase for non-Arabic matching (safe after Arabic normalization)
        text = text.lower()

        return text.strip()

    @classmethod
    def is_arabic(cls, text: str) -> bool:
        """Check if text contains Arabic characters."""
        return bool(cls.ARABIC_PATTERN.search(text)) if text else False

    @classmethod
    def levenshtein_similarity(cls, s1: str, s2: str) -> float:
        """
        Calculate similarity score between two strings.

        Returns:
            Similarity score 0.0-1.0 (1.0 = identical)
        """
        s1, s2 = cls.normalize(s1), cls.normalize(s2)
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0

        len1, len2 = len(s1), len(s2)
        if len1 > len2:
            s1, s2 = s2, s1
            len1, len2 = len2, len1

        current_row = list(range(len1 + 1))
        for i in range(1, len2 + 1):
            previous_row, current_row = current_row, [i] + [0] * len1
            for j in range(1, len1 + 1):
                add = previous_row[j] + 1
                delete = current_row[j - 1] + 1
                change = previous_row[j - 1] + (0 if s1[j - 1] == s2[i - 1] else 1)
                current_row[j] = min(add, delete, change)

        distance = current_row[len1]
        return 1.0 - (distance / max(len1, len2))


class HonorificsHandler:
    """
    Handler for Islamic honorific symbols.

    Maps display symbols (ﷺ, ﷻ, etc.) to spoken Arabic phrases.
    """

    # Honorific expansions WITH HARAKAT for proper TTS pronunciation
    HONORIFICS: Dict[str, str] = {
        # Prophet Muhammad ﷺ - صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ
        '\uFDFA': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        '\uFD46': 'صَلَّى اللهُ عَلَيْهِ وَآلِهِ وَسَلَّمَ',
        'ﷺ': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        '\uF067': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        '\uF030': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        '\uF031': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        'PBUH': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        'pbuh': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        '(s)': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        '(S)': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        '(saw)': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        '(SAW)': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        '(PBUH)': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',
        '(pbuh)': 'صَلَّى اللهُ عَلَيْهِ وَسَلَّمَ',

        # Allah ﷻ - عَزَّ وَجَلَّ
        '\uFDFB': 'عَزَّ وَجَلَّ',
        'ﷻ': 'عَزَّ وَجَلَّ',
        '\uFBF2': 'عَزَّ وَجَلَّ',
        '\uFBF1': 'عَزَّ وَجَلَّ',
        '\uF063': 'سُبْحَانَهُ وَتَعَالَى',
        '(swt)': 'سُبْحَانَهُ وَتَعَالَى',
        '(SWT)': 'سُبْحَانَهُ وَتَعَالَى',

        # Other prophets - عَلَيْهِ السَّلَامُ
        '\uF064': 'عَلَيْهِ السَّلَامُ',
        '(as)': 'عَلَيْهِ السَّلَامُ',
        '(AS)': 'عَلَيْهِ السَّلَامُ',

        # Companions - رَضِيَ اللهُ عَنْهُ
        '\uF065': 'رَضِيَ اللهُ عَنْهُ',
        '(ra)': 'رَضِيَ اللهُ عَنْهُ',
        '(RA)': 'رَضِيَ اللهُ عَنْهُ',
    }

    SYMBOLS = set(HONORIFICS.keys())

    @classmethod
    def is_honorific(cls, text: str) -> bool:
        """Check if text is an honorific symbol."""
        return text in cls.SYMBOLS

    @classmethod
    def expand(cls, symbol: str) -> Optional[str]:
        """Expand honorific symbol to spoken Arabic."""
        return cls.HONORIFICS.get(symbol)

    @classmethod
    def process_text(cls, text: str) -> tuple[str, str]:
        """
        Process text that may contain honorifics.

        Returns:
            Tuple of (display_text, spoken_text)
        """
        display = text
        spoken = text

        for symbol, expansion in cls.HONORIFICS.items():
            if symbol in text:
                spoken = spoken.replace(symbol, expansion)

        return display, spoken
