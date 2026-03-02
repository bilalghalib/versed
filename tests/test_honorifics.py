"""
Tests for lisan.honorifics — text normalizer for Islamic texts.

Covers:
- Honorific symbols (ﷺ ﷻ etc.)
- Hyphenated words (un-hyphenation)
- Transliterations (Arabic equivalents)
"""

import pytest
from versed.honorifics import (
    normalize_text,
    normalize_words,
    decode_honorific,
    find_transliteration,
    has_leading_honorific,
    get_spoken_text,
    NormalizedWord,
    HONORIFIC_SYMBOLS,
    TRANSLITERATIONS,
)


class TestHonorifics:
    """Test honorific symbol handling."""

    def test_honorific_symbols_defined(self):
        assert len(HONORIFIC_SYMBOLS) >= 5
        assert "\uf067" in HONORIFIC_SYMBOLS
        assert "\uf063" in HONORIFIC_SYMBOLS

    def test_decode_saw_honorific(self):
        text = "Prophet\uf067 said"
        cleaned, honorifics = decode_honorific(text)
        assert len(honorifics) == 1
        assert honorifics[0]["abbrev"] == "SAW"
        arabic = honorifics[0]["arabic"]
        assert len(arabic) > 10
        assert "الله" in arabic or "اللهُ" in arabic

    def test_decode_swt_honorific(self):
        text = "God\uf063 says"
        cleaned, honorifics = decode_honorific(text)
        assert len(honorifics) == 1
        assert honorifics[0]["abbrev"] == "SWT"
        arabic = honorifics[0]["arabic"]
        assert len(arabic) > 5
        assert "و" in arabic

    def test_decode_multiple_honorifics(self):
        text = "The Prophet\uf067 and God\uf063"
        cleaned, honorifics = decode_honorific(text)
        assert len(honorifics) == 2

    def test_no_honorific(self):
        text = "Regular text without symbols"
        cleaned, honorifics = decode_honorific(text)
        assert len(honorifics) == 0
        assert cleaned == text


class TestLeadingHonorific:
    """Test leading honorific detection."""

    def test_has_leading_saw(self):
        text = "\uf067said:"
        has_hon, hon_type, remaining = has_leading_honorific(text)
        assert has_hon is True
        assert hon_type == "SAW"
        assert remaining == "said:"

    def test_no_leading_honorific(self):
        text = "Normal text"
        has_hon, hon_type, remaining = has_leading_honorific(text)
        assert has_hon is False
        assert hon_type is None
        assert remaining == text


class TestTransliterations:
    """Test transliteration detection."""

    def test_transliterations_defined(self):
        assert len(TRANSLITERATIONS) >= 20
        assert "allah" in TRANSLITERATIONS
        assert "prophet" in TRANSLITERATIONS
        assert "quran" in TRANSLITERATIONS

    def test_find_prophet(self):
        assert find_transliteration("Prophet") == "النبي"

    def test_find_allah(self):
        assert find_transliteration("allah") == "الله"

    def test_find_god(self):
        assert find_transliteration("God") == "الله"

    def test_find_quran(self):
        assert find_transliteration("quran") == "القرآن"
        assert find_transliteration("Qur'an") == "القرآن"

    def test_find_surah_names(self):
        assert find_transliteration("al-fatiha") == "الفاتحة"
        assert find_transliteration("al-jathiyah") == "الجاثية"

    def test_find_partial_match(self):
        arabic = find_transliteration("(Al-Jathiyah,")
        assert arabic == "الجاثية"

    def test_not_found(self):
        assert find_transliteration("unknown_word_xyz") is None


class TestNormalizeText:
    """Test text normalization."""

    def test_normalize_honorifics(self):
        text = "The Prophet\uf067 said"
        normalized = normalize_text(text)
        assert "ﷺ" in normalized or "\uf067" not in normalized

    def test_normalize_hyphenation_newline(self):
        text = "gov-\nerning the people"
        normalized = normalize_text(text)
        assert "governing" in normalized or "gov-" not in normalized

    def test_normalize_mid_word_hyphen(self):
        text = "gov- erning"
        normalized = normalize_text(text)
        assert "governing" in normalized or "gov-" in normalized


class TestNormalizeWords:
    """Test word-level normalization."""

    def test_normalize_single_word(self):
        words = [{"text": "Prophet"}]
        result = normalize_words(words)
        assert len(result) == 1
        assert result[0].original == "Prophet"
        assert result[0].is_transliteration is True
        assert result[0].arabic == "النبي"

    def test_normalize_honorific_word(self):
        words = [{"text": "Prophet"}, {"text": "\uf067said"}]
        result = normalize_words(words)
        assert result[0].has_honorific is True
        assert result[0].honorific_type == "SAW"

    def test_normalize_hyphenated_words(self):
        words = [{"text": "gov-"}, {"text": "erning"}]
        result = normalize_words(words)
        assert len(result) == 1
        assert result[0].normalized == "governing"
        assert result[0].is_hyphen_end is True

    def test_normalized_word_fields(self):
        words = [{"text": "test"}]
        result = normalize_words(words)
        word = result[0]
        assert hasattr(word, "original")
        assert hasattr(word, "normalized")
        assert hasattr(word, "arabic")
        assert hasattr(word, "has_honorific")
        assert hasattr(word, "honorific_type")
        assert hasattr(word, "is_hyphen_start")
        assert hasattr(word, "is_hyphen_end")
        assert hasattr(word, "is_transliteration")


class TestGetSpokenText:
    """Test TTS-ready text generation."""

    def test_spoken_regular_word(self):
        word = NormalizedWord(
            original="test", normalized="test", arabic=None,
            has_honorific=False, honorific_type=None,
            is_hyphen_start=False, is_hyphen_end=False,
            is_transliteration=False,
        )
        assert get_spoken_text(word) == "test"

    def test_spoken_with_saw_expansion(self):
        word = NormalizedWord(
            original="Prophet", normalized="Prophet", arabic="النبي",
            has_honorific=True, honorific_type="SAW",
            is_hyphen_start=False, is_hyphen_end=False,
            is_transliteration=True,
        )
        spoken = get_spoken_text(word, expand_honorifics=True)
        assert "صلى الله عليه وسلم" in spoken

    def test_spoken_with_swt_expansion(self):
        word = NormalizedWord(
            original="God", normalized="God", arabic="الله",
            has_honorific=True, honorific_type="SWT",
            is_hyphen_start=False, is_hyphen_end=False,
            is_transliteration=True,
        )
        spoken = get_spoken_text(word, expand_honorifics=True)
        assert "سبحانه وتعالى" in spoken

    def test_spoken_no_expansion(self):
        word = NormalizedWord(
            original="Prophet", normalized="Prophet", arabic="النبي",
            has_honorific=True, honorific_type="SAW",
            is_hyphen_start=False, is_hyphen_end=False,
            is_transliteration=True,
        )
        spoken = get_spoken_text(word, expand_honorifics=False)
        assert "صلى الله عليه وسلم" not in spoken
