"""
Tests for lisan.repair — font-aware encoding repair for Sabon fonts.

Tests that:
1. Character repair map is applied correctly for Sabon fonts
2. Non-Sabon fonts are never modified
3. Bbox containment matching works for multi-word spans
4. Full word tuple pipeline preserves non-text fields
5. Edge cases (empty spans, no mojibake chars) are handled cleanly
6. The convenience repair_text() wrapper works
"""

import pytest

from versed.repair import (
    SABON_CHAR_REPAIR,
    SABON_FONT_PREFIXES,
    extract_repairable_font_spans,
    find_font_for_word,
    is_repairable_font,
    repair_text,
    repair_text_for_font,
    repair_words_with_font_info,
)


# ---------------------------------------------------------------------------
# is_repairable_font
# ---------------------------------------------------------------------------
class TestIsRepairableFont:
    def test_sabondiex_plain(self):
        assert is_repairable_font("SabondiexPlain") is True

    def test_sabondiacritic_roman(self):
        assert is_repairable_font("SabondiacriticRoman") is True

    def test_sabondiacritic_bold(self):
        assert is_repairable_font("SabondiacriticBold") is True

    def test_sabondiacritic_italic(self):
        assert is_repairable_font("SabondiacriticItalic") is True

    def test_non_sabon_font(self):
        assert is_repairable_font("TimesNewRoman") is False

    def test_qcf_font_not_repairable(self):
        assert is_repairable_font("QCF_P363") is False

    def test_empty_string(self):
        assert is_repairable_font("") is False


# ---------------------------------------------------------------------------
# repair_text (convenience wrapper)
# ---------------------------------------------------------------------------
class TestRepairText:
    def test_repair_all_three_mojibake_chars(self):
        assert repair_text("taf\u00df\u00acl") == "taf\u1e63\u012bl"

    def test_repair_ha_with_dot(self):
        assert repair_text("ta\u00a4\u00df\u00acl") == "ta\u1e25\u1e63\u012bl"

    def test_no_change_for_clean_text(self):
        assert repair_text("normal text") == "normal text"

    def test_empty_string(self):
        assert repair_text("") == ""


# ---------------------------------------------------------------------------
# repair_text_for_font
# ---------------------------------------------------------------------------
class TestRepairTextForFont:
    def test_repair_all_three_mojibake_chars(self):
        """All three known mojibake chars are repaired for Sabon fonts."""
        text = "taf\u00df\u00acl"  # tafß¬l
        result = repair_text_for_font(text, "SabondiexPlain")
        assert result == "taf\u1e63\u012bl"  # tafṣīl

    def test_repair_ha_with_dot(self):
        """¤ maps to ḥ."""
        text = "ta\u00a4\u00df\u00acl"  # ta¤ß¬l
        result = repair_text_for_font(text, "SabondiexPlain")
        assert result == "ta\u1e25\u1e63\u012bl"  # taḥṣīl

    def test_no_repair_for_non_sabon_font(self):
        """Non-Sabon fonts pass through unchanged even with ß in text."""
        text = "taf\u00df\u00acl"
        result = repair_text_for_font(text, "TimesNewRoman")
        assert result == text  # unchanged

    def test_no_repair_for_clean_text(self):
        """Text without mojibake chars passes through unchanged."""
        text = "normal text"
        result = repair_text_for_font(text, "SabondiexPlain")
        assert result == text

    def test_preserves_non_mojibake_chars(self):
        """Characters not in the repair map pass through unchanged."""
        text = "hello \u00df world"  # hello ß world
        result = repair_text_for_font(text, "SabondiexPlain")
        assert result == "hello \u1e63 world"  # hello ṣ world

    def test_empty_text(self):
        result = repair_text_for_font("", "SabondiexPlain")
        assert result == ""


# ---------------------------------------------------------------------------
# find_font_for_word (bbox containment)
# ---------------------------------------------------------------------------
class TestFindFontForWord:
    def test_word_within_span_bbox(self):
        font_spans = [(40.0, 510.0, 270.0, 524.0, "SabondiexPlain")]
        font = find_font_for_word(51.0, 511.0, 80.0, 522.0, font_spans)
        assert font == "SabondiexPlain"

    def test_second_word_in_same_span(self):
        font_spans = [(40.0, 510.0, 270.0, 524.0, "SabondiexPlain")]
        font = find_font_for_word(170.0, 511.0, 200.0, 522.0, font_spans)
        assert font == "SabondiexPlain"

    def test_word_on_different_line(self):
        font_spans = [(40.0, 510.0, 270.0, 524.0, "SabondiexPlain")]
        font = find_font_for_word(51.0, 45.0, 80.0, 58.0, font_spans)
        assert font is None

    def test_word_outside_x_range(self):
        font_spans = [(40.0, 510.0, 270.0, 524.0, "SabondiexPlain")]
        font = find_font_for_word(300.0, 511.0, 330.0, 522.0, font_spans)
        assert font is None

    def test_empty_font_spans(self):
        font = find_font_for_word(51.0, 511.0, 80.0, 522.0, [])
        assert font is None

    def test_best_overlap_wins(self):
        font_spans = [
            (40.0, 510.0, 100.0, 524.0, "SabondiexPlain"),
            (80.0, 510.0, 270.0, 524.0, "SabondiacriticRoman"),
        ]
        font = find_font_for_word(51.0, 511.0, 200.0, 522.0, font_spans)
        assert font == "SabondiacriticRoman"


# ---------------------------------------------------------------------------
# repair_words_with_font_info (full pipeline)
# ---------------------------------------------------------------------------
class TestRepairWordsWithFontInfo:
    def _make_word(self, x0, y0, x1, y1, text, block=0, line=0, word=0):
        return (x0, y0, x1, y1, text, block, line, word)

    def test_replaces_text_preserves_other_fields(self):
        font_spans = [(40.0, 510.0, 270.0, 524.0, "SabondiexPlain")]
        words = [
            self._make_word(51.0, 511.0, 80.0, 522.0, "taf\u00df\u00acl", 5, 2, 1),
        ]
        result = repair_words_with_font_info(words, font_spans)
        assert len(result) == 1
        w = result[0]
        assert w[4] == "taf\u1e63\u012bl"
        assert w[0] == 51.0
        assert w[5] == 5
        assert w[6] == 2
        assert w[7] == 1

    def test_empty_font_spans_is_noop(self):
        words = [
            self._make_word(51.0, 511.0, 80.0, 522.0, "taf\u00df\u00acl"),
        ]
        result = repair_words_with_font_info(words, [])
        assert result[0][4] == "taf\u00df\u00acl"

    def test_mixed_repairable_and_clean_words(self):
        font_spans = [(40.0, 510.0, 270.0, 524.0, "SabondiexPlain")]
        words = [
            self._make_word(51.0, 45.0, 150.0, 58.0, "normal text"),
            self._make_word(51.0, 511.0, 80.0, 522.0, "taf\u00df\u00acl"),
        ]
        result = repair_words_with_font_info(words, font_spans)
        assert result[0][4] == "normal text"
        assert result[1][4] == "taf\u1e63\u012bl"
