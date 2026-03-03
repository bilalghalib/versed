"""Portable Arabic text helpers for the public engine."""

from __future__ import annotations

from typing import Iterable


ARABIC_DIACRITICS = frozenset(
    {
        "\u064B",
        "\u064C",
        "\u064D",
        "\u064E",
        "\u064F",
        "\u0650",
        "\u0651",
        "\u0652",
        "\u0653",
        "\u0654",
        "\u0655",
        "\u0656",
        "\u0657",
        "\u0658",
        "\u0670",
    }
)

ARABIC_BASE_LETTERS = frozenset(chr(codepoint) for codepoint in range(0x0621, 0x064B))


def _iter_arabic_chars(text: str) -> Iterable[str]:
    return (
        char
        for char in text
        if "\u0600" <= char <= "\u06FF" or "\u0750" <= char <= "\u077F"
    )


def is_arabic(text: str) -> bool:
    """Return True when the string contains Arabic characters."""
    return any(True for _ in _iter_arabic_chars(text))


def is_mostly_arabic(text: str, threshold: float = 0.5) -> bool:
    """Return True when at least `threshold` of visible chars are Arabic."""
    if not text:
        return False

    visible_chars = [char for char in text if not char.isspace()]
    if not visible_chars:
        return False

    arabic_chars = [char for char in visible_chars if is_arabic(char)]
    return (len(arabic_chars) / len(visible_chars)) >= threshold


def strip_diacritics(text: str) -> str:
    """Remove Arabic diacritics for fuzzy matching."""
    return "".join(char for char in text if char not in ARABIC_DIACRITICS)


def orphan_diacritic_rate(text: str) -> float:
    """Measure how often diacritics appear without a valid Arabic base letter."""
    if not text:
        return 0.0

    diacritic_count = 0
    orphan_count = 0

    for index, char in enumerate(text):
        if char not in ARABIC_DIACRITICS:
            continue

        diacritic_count += 1

        cursor = index - 1
        while cursor >= 0 and text[cursor] in ARABIC_DIACRITICS:
            cursor -= 1

        if cursor < 0:
            orphan_count += 1
        elif text[cursor] not in ARABIC_BASE_LETTERS and not is_arabic(text[cursor]):
            orphan_count += 1

    return orphan_count / diacritic_count if diacritic_count else 0.0


def detect_batch_reversal(words_raw: list) -> bool:
    """Detect likely RTL reversal in a PyMuPDF-style `get_text(\"words\")` batch."""
    arabic_texts = []
    for word in words_raw:
        text = word[4] if len(word) > 4 else ""
        if is_arabic(text) and any(char in ARABIC_DIACRITICS for char in text):
            arabic_texts.append(text)

    if len(arabic_texts) < 3:
        return False

    orphan_rates = [orphan_diacritic_rate(text) for text in arabic_texts[:30]]

    if max(orphan_rates) >= 0.4:
        return True

    words_with_orphans = sum(1 for rate in orphan_rates if rate > 0.1)
    if words_with_orphans / len(orphan_rates) >= 0.3:
        return True

    average_rate = sum(orphan_rates) / len(orphan_rates)
    return average_rate > 0.15

