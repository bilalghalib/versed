"""Tests for the broken-CMap ligature repair (two-rule version).

Fixtures from the OUP edited-volume PDF (Sheibani / Marriage chapter)
where the Merriweather font's ToUnicode CMap drops `fi` to U+007F and
maps `ff` to U+007C (`|`).
"""
from __future__ import annotations

from versed.ligatures import (
    expand_dropped_ligatures,
    repair_words_for_dropped_ligatures,
)


# --- pipe → ff ----------------------------------------------------------

def test_pipe_inside_word_becomes_ff():
    assert expand_dropped_ligatures("di|ered") == "differed"
    assert expand_dropped_ligatures("e|ectuated") == "effectuated"
    assert expand_dropped_ligatures("o|er") == "offer"
    assert expand_dropped_ligatures("di|erent") == "different"
    assert expand_dropped_ligatures("gender-di|erentiated") == "gender-differentiated"


def test_pipe_outside_word_left_alone():
    """Genuine pipes in math/code/leaders must not be touched."""
    assert expand_dropped_ligatures("a | b") == "a | b"
    assert expand_dropped_ligatures("p. 159 | OUP") == "p. 159 | OUP"
    assert expand_dropped_ligatures("|table|") == "|table|"
    assert expand_dropped_ligatures("|a") == "|a"


def test_pipe_at_word_end_repaired():
    """The `ff` glyph drops to `|` and may sit at the end of a word
    when the trailing letters were dropped (`off` -> `o|`).

    Observed in the OUP/Sheibani PDF, page 3:
      'fathers can marry o| their minor children'
      'agnatic kin to whom guardianship would devolve from marrying o|'
    """
    assert expand_dropped_ligatures("o|") == "off"
    assert expand_dropped_ligatures("o|,") == "off,"
    assert expand_dropped_ligatures("o|.") == "off."
    assert expand_dropped_ligatures("o| their") == "off their"


def test_pipe_in_paragraph_with_separators_handles_both():
    """A paragraph that mixes a real ligature corruption AND a
    separator pipe must repair the corruption and leave the separator
    alone. The separator looks like ``|table|`` (region starts with
    `|`)."""
    src = "Jurists di|ered. See |table| below. He had no o|."
    expected = "Jurists differed. See |table| below. He had no off."
    assert expand_dropped_ligatures(src) == expected


# --- \x7f → fi -----------------------------------------------------------

def test_del_marker_becomes_fi():
    assert expand_dropped_ligatures("\x7fnancial") == "financial"
    assert expand_dropped_ligatures("\x7fxed") == "fixed"
    assert expand_dropped_ligatures("\x7frst") == "first"
    assert expand_dropped_ligatures("\x7ffteenth-century") == "fifteenth-century"


def test_del_marker_between_accented_latin_and_translit_marks():
    """The `fi` glyph drops to `\\x7f` even inside transliterated tokens
    that use accented Latin and modifier marks. Without this, words
    like ``Shāfiʿīs`` come back as ``Shā\\x7fʿīs`` and stay broken.

    Observed in the OUP/Sheibani PDF, page 3:
      'According to Shā\\x7fʿīs, ...'
    """
    assert expand_dropped_ligatures("Shā\x7fʿīs") == "Shāfiʿīs"
    assert expand_dropped_ligatures("Shā\x7fʿīs,") == "Shāfiʿīs,"


def test_is_latinish_word_char_recognizes_full_alphabet():
    from versed.ligatures import is_latinish_word_char
    # ASCII
    assert is_latinish_word_char("a")
    assert is_latinish_word_char("Z")
    # Latin-1 / Extended-A
    assert is_latinish_word_char("ā")
    assert is_latinish_word_char("é")
    assert is_latinish_word_char("ñ")
    # Latin Extended Additional
    assert is_latinish_word_char("ḥ")
    assert is_latinish_word_char("ṣ")
    assert is_latinish_word_char("ṭ")
    # Modifier marks
    assert is_latinish_word_char("ʿ")
    assert is_latinish_word_char("ʾ")
    # Curly apostrophes
    assert is_latinish_word_char("'")
    assert is_latinish_word_char("'")
    # Negative cases
    assert not is_latinish_word_char("|")
    assert not is_latinish_word_char(" ")
    assert not is_latinish_word_char("ا")  # Arabic alef
    assert not is_latinish_word_char("")


def test_del_marker_at_word_end_also_repaired():
    """If `fi` somehow lands at end of a token, still recover it."""
    assert expand_dropped_ligatures("toe\x7f") == "toefi"


def test_del_marker_outside_word_left_alone():
    """Bare control chars in non-word contexts shouldn't be touched."""
    assert expand_dropped_ligatures("\x7f") == "\x7f"
    assert expand_dropped_ligatures("a \x7f b") == "a \x7f b"


# --- combined and pass-through ------------------------------------------

def test_combined_pipe_and_del_in_one_pass():
    assert expand_dropped_ligatures("\x7fnancial di|ered") == "financial differed"


def test_unrelated_text_passes_through():
    assert expand_dropped_ligatures("the quick brown fox") == "the quick brown fox"
    assert expand_dropped_ligatures("") == ""


def test_arabic_unaffected():
    assert expand_dropped_ligatures("الْمَالِكِيّ") == "الْمَالِكِيّ"


# --- standard Unicode ligature codepoints --------------------------------

def test_unicode_ligature_codepoints_normalized():
    """Well-formed PDFs may emit U+FB01–FB06 + U+0132/0133 directly.
    Normalize them at extraction time so downstream stages (LLM, TTS,
    search) see plain ASCII."""
    assert expand_dropped_ligatures("ﬁnancial") == "financial"
    assert expand_dropped_ligatures("ﬂoating") == "floating"
    assert expand_dropped_ligatures("diﬀered") == "differed"
    assert expand_dropped_ligatures("eﬃcient") == "efficient"
    assert expand_dropped_ligatures("waﬄe") == "waffle"
    assert expand_dropped_ligatures("ﬅinger") == "ftinger"  # U+FB05
    assert expand_dropped_ligatures("ﬆone") == "stone"
    assert expand_dropped_ligatures("ĳsselmeer") == "ijsselmeer"
    assert expand_dropped_ligatures("Ĳsselmeer") == "IJsselmeer"


def test_unicode_and_broken_markers_in_one_pass():
    """A page can contain both well-formed ligatures and broken markers
    (e.g. the running header uses the right font, body text uses the
    broken one). The repair pass handles both."""
    assert (
        expand_dropped_ligatures("ﬁnancial \x7fxed and di|ered")
        == "financial fixed and differed"
    )


# --- PyMuPDF word-tuple wrapper ----------------------------------------

def test_repair_words_for_dropped_ligatures_only_touches_text():
    """Coordinates and trailing fields stay byte-identical; only the text
    field changes when a repair applies."""
    words_in = [
        (10.0, 20.0, 50.0, 30.0, "\x7fnancial", 0, 0, 0),
        (60.0, 20.0, 100.0, 30.0, "support", 0, 0, 1),  # untouched
        (10.0, 35.0, 80.0, 45.0, "di|ered", 0, 1, 0),
    ]
    out = repair_words_for_dropped_ligatures(words_in)
    assert out[0] == (10.0, 20.0, 50.0, 30.0, "financial", 0, 0, 0)
    assert out[1] == words_in[1]
    assert out[2] == (10.0, 35.0, 80.0, 45.0, "differed", 0, 1, 0)
