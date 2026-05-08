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
    assert expand_dropped_ligatures("a|") == "a|"
    assert expand_dropped_ligatures("|a") == "|a"


# --- \x7f → fi -----------------------------------------------------------

def test_del_marker_becomes_fi():
    assert expand_dropped_ligatures("\x7fnancial") == "financial"
    assert expand_dropped_ligatures("\x7fxed") == "fixed"
    assert expand_dropped_ligatures("\x7frst") == "first"
    assert expand_dropped_ligatures("\x7ffteenth-century") == "fifteenth-century"


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
