"""Repair PDF font CMaps that drop or mojibake-d Latin f-ligature glyphs.

Some PDF fonts (observed in OUP academic typesetting using Merriweather
and Sabon) ship with broken ToUnicode CMaps for the standard `fi`, `fl`,
`ff`, `ffi`, `ffl` ligature glyphs:

  - The `ff` glyph maps to U+007C (`|`):
        differed → di|ered, effectuated → e|ectuated, off → o|.

  - The `fi` glyph maps to U+007F (DEL):
        financial → \\x7fnancial, fixed → \\x7fxed,
        Shāfiʿīs → Shā\\x7fʿīs.

The standard ligature codepoints U+FB01–U+FB04 are useless here — the
broken font never emitted them in the first place. We repair after
extraction by translating the two known marker characters when they
appear inside a word context.

The neighbour test is intentionally inclusive: as well as ASCII letters
it accepts accented Latin letters (ā, ī, ḥ, ṣ, …) and the modifier
characters used in Arabic transliteration (ʿ, ʾ, curly apostrophes).
That is why ``Shā\\x7fʿīs`` repairs even though `ā` and `ʿ` are not in
``[A-Za-z]``.

We deliberately do NOT try to recover the silently-dropped fl/ffi/ffl
glyphs (where PyMuPDF emits nothing — no marker char survives). There
is no anchor signal without per-font glyph-table inspection or a
wordlist; that's a separate repair pass.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Tuple


# --- Standard Unicode ligature codepoints (well-formed PDFs) ----------
#
# Official Unicode ligature characters. Well-formed PDFs emit these
# directly; many TTS engines and downstream consumers don't speak them
# properly, so we normalize at extraction time. 1:N character map.
_UNICODE_LIGATURES: dict[str, str] = {
    "ĳ": "ij",   # ĳ Latin Small Ligature IJ
    "Ĳ": "IJ",   # Ĳ Latin Capital Ligature IJ
    "ﬀ": "ff",   # ﬀ
    "ﬁ": "fi",   # ﬁ
    "ﬂ": "fl",   # ﬂ
    "ﬃ": "ffi",  # ﬃ
    "ﬄ": "ffl",  # ﬄ
    "ﬅ": "ft",   # ﬅ Latin Small Ligature Long S T
    "ﬆ": "st",   # ﬆ Latin Small Ligature ST
}

_UNICODE_LIGATURE_RE = re.compile(
    "|".join(re.escape(c) for c in _UNICODE_LIGATURES)
)

# Latin transliteration modifier marks that may sit next to a marker
# character: ʿ (U+02BF), ʾ (U+02BE), curly apostrophes.
_TRANSLIT_MARKS = frozenset({"ʾ", "ʿ", "‘", "’", "'"})

# Marker characters we know about (broken CMap output).
_MARKERS = frozenset({"|", "\x7f"})


def is_latinish_word_char(ch: str) -> bool:
    """True if ``ch`` is a Latin-or-Latin-transliteration word character.

    We treat as "latinish" anything that can plausibly sit inside a word
    that was set in a Latin-script font:

      - ASCII letters
      - Latin-1 Supplement + Latin Extended-A/B (U+00C0–U+024F):
          covers à, é, ñ, ā, ī, ē, ō, etc.
      - Latin Extended Additional (U+1E00–U+1EFF):
          covers ḥ, ṣ, ḍ, ṭ, ẓ, etc.
      - Modifier letters used in Arabic transliteration: ʿ ʾ
      - Curly apostrophes used in transliteration: ' '

    We deliberately do NOT include Arabic-script characters; words
    written in Arabic shouldn't be touched by this repair.
    """
    if not ch:
        return False
    if "a" <= ch <= "z" or "A" <= ch <= "Z":
        return True
    cp = ord(ch)
    if 0x00C0 <= cp <= 0x024F:
        return True
    if 0x1E00 <= cp <= 0x1EFF:
        return True
    if ch in _TRANSLIT_MARKS:
        return True
    return False


def _is_word_char(ch: str) -> bool:
    """Latinish letter, ligature marker, or in-word punctuation (hyphen).
    Used to bracket a "word region" inside a longer string."""
    return is_latinish_word_char(ch) or ch in _MARKERS or ch == "-"


def _repair_word_region(region: str) -> str:
    """Repair markers inside a single tokenized word region.

    A region is a maximal run of word characters (latinish letters,
    markers, hyphens). We refuse to repair regions that *start* with a
    bare `|` — those look like separator pipes, not corrupted glyphs
    (e.g. ``|table|`` from a TOC leader).
    """
    if not region:
        return region
    # Leading-`|` regions are almost always separator pipes.
    if region.startswith("|"):
        return region

    out: List[str] = []
    n = len(region)
    for i, ch in enumerate(region):
        prev = region[i - 1] if i > 0 else ""
        nxt = region[i + 1] if i + 1 < n else ""

        if ch == "|":
            left_ok = is_latinish_word_char(prev)
            right_letter = is_latinish_word_char(nxt)
            right_word_end = (i == n - 1) or (not is_latinish_word_char(nxt) and nxt != "|")
            if left_ok and (right_letter or right_word_end):
                out.append("ff")
                continue
        elif ch == "\x7f":
            # Only need ONE latinish neighbour (handles `\x7fnancial` at
            # the start of a word and `Shā\x7fʿīs` mid-word equally).
            if is_latinish_word_char(prev) or is_latinish_word_char(nxt):
                out.append("fi")
                continue
        out.append(ch)
    return "".join(out)


def expand_dropped_ligatures(text: str) -> str:
    """Normalize Unicode ligatures and repair the known broken-CMap markers.

    Applied in order:

      1. Standard ligature codepoints U+FB00-FB06 + U+0132/0133
         (ﬁ → fi, ﬂ → fl, ﬀ → ff, ﬃ → ffi, ﬄ → ffl, ﬅ → ft, ﬆ → st,
         ĳ → ij, Ĳ → IJ).

      2. Per-word-region scan for the broken-CMap markers `|` and `\\x7f`:
         - `|` adjacent to a latinish letter (with another letter or a
           word boundary on the other side) → ``ff``.
         - `\\x7f` next to any latinish letter → ``fi``.

    "Latinish" here includes accented Latin and the transliteration
    modifier letters ʿ ʾ (so ``Shā\\x7fʿīs`` repairs even though `ā` and
    `ʿ` are outside ``[A-Za-z]``).

    Word regions that *start* with `|` are left alone — those are almost
    always separator pipes (e.g. ``|table|`` from a TOC leader).

    Returns ``text`` unchanged when no rule applies.
    """
    if not text:
        return text

    # 1. Unicode normalization (cheap, char-for-char).
    text = _UNICODE_LIGATURE_RE.sub(lambda m: _UNICODE_LIGATURES[m.group(0)], text)

    # 2. Region-aware marker repair.
    out: List[str] = []
    n = len(text)
    i = 0
    while i < n:
        if _is_word_char(text[i]):
            j = i
            while j < n and _is_word_char(text[j]):
                j += 1
            out.append(_repair_word_region(text[i:j]))
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def repair_words_for_dropped_ligatures(
    words_raw: Iterable[Tuple],
) -> List[Tuple]:
    """Apply :func:`expand_dropped_ligatures` to PyMuPDF word tuples.

    PyMuPDF's ``page.get_text("words")`` returns tuples
    ``(x0, y0, x1, y1, text, block, line, word)``. We rebuild each
    tuple with the repaired text and leave coordinates untouched.
    """
    repaired: List[Tuple] = []
    for w in words_raw:
        if len(w) <= 4:
            repaired.append(w)
            continue
        text = w[4] or ""
        new_text = expand_dropped_ligatures(text)
        if new_text == text:
            repaired.append(w)
            continue
        repaired.append((w[0], w[1], w[2], w[3], new_text) + tuple(w[5:]))
    return repaired
