"""Tests for public Arabic helpers."""

from versed.arabic import (
    detect_batch_reversal,
    is_arabic,
    is_mostly_arabic,
    orphan_diacritic_rate,
    strip_diacritics,
)


class TestArabicHelpers:
    def test_is_arabic_detects_arabic_chars(self):
        assert is_arabic("hello") is False
        assert is_arabic("السلام") is True

    def test_is_mostly_arabic_uses_ratio(self):
        assert is_mostly_arabic("abc") is False
        assert is_mostly_arabic("سلام test", threshold=0.3) is True

    def test_strip_diacritics(self):
        assert strip_diacritics("السَّلَامُ") == "السلام"

    def test_orphan_diacritic_rate(self):
        assert orphan_diacritic_rate("َسلام") > 0.0
        assert orphan_diacritic_rate("سلام") == 0.0

    def test_detect_batch_reversal(self):
        words_raw = [
            (0, 0, 0, 0, "َسل"),
            (0, 0, 0, 0, "َام"),
            (0, 0, 0, 0, "َكم"),
        ]
        assert detect_batch_reversal(words_raw) is True

