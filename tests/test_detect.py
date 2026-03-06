"""
Tests for versed.detect — mojibake detection heuristics.
"""

from versed.detect import detect_mojibake, MojibakeReport, KNOWN_MOJIBAKE_CHARS


class TestDetectMojibake:
    """Test mojibake detection on strings."""

    def test_clean_text_no_mojibake(self):
        report = detect_mojibake("This is clean text with no issues")
        assert report.has_mojibake is False
        assert report.mojibake_count == 0
        assert report.mojibake_rate == 0.0

    def test_empty_text(self):
        report = detect_mojibake("")
        assert report.has_mojibake is False
        assert report.mojibake_count == 0
        assert report.total_chars == 0

    def test_detects_sabon_mojibake(self):
        """Detects ß ¬ ¤ from Sabon font corruption."""
        text = "taf\u00df\u00acl and ta\u00a4\u00df\u00acl"
        report = detect_mojibake(text)
        assert report.has_mojibake is True
        assert report.mojibake_count == 5  # 2 + 3

    def test_detects_replacement_char(self):
        """Detects U+FFFD replacement character."""
        text = "some \ufffd text"
        report = detect_mojibake(text)
        assert report.has_mojibake is True
        assert report.mojibake_count == 1

    def test_mojibake_rate(self):
        text = "\u00df\u00ac"  # 2 mojibake chars, 2 total
        report = detect_mojibake(text)
        assert report.mojibake_rate == 1.0

    def test_sample_contexts_captured(self):
        text = "before \u00df after"
        report = detect_mojibake(text)
        assert len(report.sample_contexts) == 1
        assert "\\x" in report.sample_contexts[0] or "'" in report.sample_contexts[0]

    def test_max_five_samples(self):
        text = "\u00df " * 10  # 10 mojibake chars
        report = detect_mojibake(text)
        assert len(report.sample_contexts) == 5

    def test_char_counts(self):
        text = "\u00df\u00df\u00ac"
        report = detect_mojibake(text)
        assert report.mojibake_chars["\u00df"] == 2
        assert report.mojibake_chars["\u00ac"] == 1

    def test_repaired_text_clean(self):
        """Text after repair has no mojibake."""
        from versed.repair import repair_text
        original = "taf\u00df\u00acl"
        repaired = repair_text(original)
        report = detect_mojibake(repaired)
        assert report.has_mojibake is False

    def test_known_chars_frozenset(self):
        """KNOWN_MOJIBAKE_CHARS contains expected characters."""
        assert "\u00df" in KNOWN_MOJIBAKE_CHARS  # ß
        assert "\u00ac" in KNOWN_MOJIBAKE_CHARS  # ¬
        assert "\u00a4" in KNOWN_MOJIBAKE_CHARS  # ¤
        assert "\ufffd" in KNOWN_MOJIBAKE_CHARS  # replacement char
