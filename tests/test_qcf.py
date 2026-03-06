"""
Tests for versed.qcf — QCF (Quran Complex Font) decoder.

The QCF decoder maps Private Use Area glyphs to Arabic text
with verse references based on the mushaf page.
"""

import pytest
from versed.qcf import (
    QCFDecoder,
    is_qcf_glyph,
    is_qcf_text,
    extract_qcf_page_number,
    QCFWord,
)


class TestQCFGlyphDetection:
    """Test glyph detection functions."""

    def test_is_qcf_glyph_pua_basic(self):
        assert is_qcf_glyph("\uE000") is True
        assert is_qcf_glyph("\uF000") is True
        assert is_qcf_glyph("\uF8FF") is True

    def test_is_qcf_glyph_arabic_forms_a(self):
        assert is_qcf_glyph("\uFB50") is True
        assert is_qcf_glyph("\uFC00") is True
        assert is_qcf_glyph("\uFDFF") is True

    def test_is_qcf_glyph_arabic_forms_b(self):
        assert is_qcf_glyph("\uFE70") is True
        assert is_qcf_glyph("\uFEFF") is True

    def test_is_qcf_glyph_regular_text(self):
        assert is_qcf_glyph("A") is False
        assert is_qcf_glyph(" ") is False
        assert is_qcf_glyph("ا") is False
        assert is_qcf_glyph("ب") is False

    def test_is_qcf_text_with_glyphs(self):
        text_with_qcf = "Hello \uE000\uE001 world"
        assert is_qcf_text(text_with_qcf) is True

    def test_is_qcf_text_without_glyphs(self):
        assert is_qcf_text("Hello world") is False

    def test_is_qcf_text_empty(self):
        assert is_qcf_text("") is False


class TestFontPageExtraction:
    """Test mushaf page extraction from font names."""

    def test_extract_page_standard_format(self):
        assert extract_qcf_page_number("QCF_P001") == 1
        assert extract_qcf_page_number("QCF_P100") == 100
        assert extract_qcf_page_number("QCF_P604") == 604

    def test_extract_page_alternate_format(self):
        assert extract_qcf_page_number("QCF2_P123") == 123
        assert extract_qcf_page_number("KFGQPC_P050") is None or extract_qcf_page_number("KFGQPC_P050") == 50

    def test_extract_page_invalid(self):
        assert extract_qcf_page_number("Arial") is None
        assert extract_qcf_page_number("Times New Roman") is None
        assert extract_qcf_page_number("") is None

    def test_extract_page_returns_number(self):
        assert extract_qcf_page_number("QCF_P000") == 0
        assert extract_qcf_page_number("QCF_P605") == 605
        assert extract_qcf_page_number("QCF_P999") == 999


class TestQCFDecoder:
    """Test the QCF decoder class."""

    def test_singleton_pattern(self):
        # Reset singleton for test isolation
        QCFDecoder._instance = None
        decoder1 = QCFDecoder.get_instance()
        decoder2 = QCFDecoder.get_instance()
        assert decoder1 is decoder2

    def test_decoder_loads_mapping(self):
        QCFDecoder._instance = None
        decoder = QCFDecoder.get_instance()
        assert decoder.is_loaded is True

    def test_mapping_has_604_pages(self, qcf_mapping):
        pages = qcf_mapping.get("pages", {})
        assert len(pages) == 604

    def test_page_1_contains_bismillah(self, qcf_mapping):
        pages = qcf_mapping.get("pages", {})
        page_1 = pages.get("1", {})
        assert len(page_1) > 0
        first_glyph = list(page_1.keys())[0]
        first_word = page_1[first_glyph]
        assert first_word.get("verse_key") == "1:1"

    def test_word_has_required_fields(self, qcf_mapping):
        pages = qcf_mapping.get("pages", {})
        page_1 = pages.get("1", {})
        first_glyph = list(page_1.keys())[0]
        word = page_1[first_glyph]
        assert "arabic" in word
        assert "verse_key" in word
        assert "word_position" in word


class TestQCFWordDataclass:
    """Test QCFWord dataclass."""

    def test_qcf_word_creation(self):
        word = QCFWord(
            glyph="\uFB51",
            arabic="بِسْمِ",
            page=1,
            position=0,
        )
        assert word.glyph == "\uFB51"
        assert word.arabic == "بِسْمِ"
        assert word.page == 1
        assert word.position == 0

    def test_qcf_word_optional_fields(self):
        word = QCFWord(
            glyph="\uFB51",
            arabic="بِسْمِ",
            page=1,
            position=0,
            verse_key="1:1",
            word_position=1,
            transliteration="bis'mi",
        )
        assert word.verse_key == "1:1"
        assert word.word_position == 1
        assert word.transliteration == "bis'mi"


class TestSQLiteBackend:
    """Test SQLite-specific functionality."""

    def test_sqlite_loads(self):
        from versed.qcf import _DB_PATH
        if not _DB_PATH.exists():
            pytest.skip("SQLite DB not found")
        QCFDecoder._instance = None
        decoder = QCFDecoder()
        assert decoder.is_loaded is True
        stats = decoder.get_stats()
        assert stats["backend"] == "sqlite"
        assert stats["pages"] == 604
        assert stats["glyphs"] > 70000

    def test_sqlite_lazy_loading(self):
        from versed.qcf import _DB_PATH
        if not _DB_PATH.exists():
            pytest.skip("SQLite DB not found")
        QCFDecoder._instance = None
        decoder = QCFDecoder()
        stats = decoder.get_stats()
        assert stats["pages_cached"] == 0  # Nothing loaded yet

        # Decode a glyph — triggers page 1 load
        info = decoder.decode_glyph("\uFB51", 1)
        assert info is not None
        assert info["arabic"] == "بِسْمِ"
        stats = decoder.get_stats()
        assert stats["pages_cached"] == 1  # Only page 1 loaded

    def test_sqlite_verse_lookup(self):
        from versed.qcf import _DB_PATH
        if not _DB_PATH.exists():
            pytest.skip("SQLite DB not found")
        QCFDecoder._instance = None
        decoder = QCFDecoder()
        text = decoder.get_verse_text("1:1")
        assert text is not None
        assert "بِسْمِ" in text

    def test_sqlite_decode_page1_bismillah(self):
        from versed.qcf import _DB_PATH
        if not _DB_PATH.exists():
            pytest.skip("SQLite DB not found")
        QCFDecoder._instance = None
        decoder = QCFDecoder()
        arabic, words = decoder.decode_text("\uFB51\uFB52\uFB53\uFB54", "QCF_P001")
        assert len(words) == 4
        assert words[0].arabic == "بِسْمِ"
        assert words[0].verse_key == "1:1"


class TestDecodeText:
    """Test text decoding functionality."""

    def test_decode_empty_text(self):
        QCFDecoder._instance = None
        decoder = QCFDecoder.get_instance()
        arabic, words = decoder.decode_text("", "QCF_P001")
        assert arabic == ""
        assert len(words) == 0

    def test_decode_non_qcf_text(self):
        QCFDecoder._instance = None
        decoder = QCFDecoder.get_instance()
        arabic, words = decoder.decode_text("Hello world", "Arial")
        assert "H" in arabic
        assert "e" in arabic
        assert len(words) == 0

    def test_decode_with_invalid_font(self):
        QCFDecoder._instance = None
        decoder = QCFDecoder.get_instance()
        arabic, words = decoder.decode_text("test", "TimesNewRoman")
        assert "t" in arabic
        assert "e" in arabic
        assert len(words) == 0
