"""Repair PDF font CMaps that drop or mojibake-d Latin f-ligature glyphs.

Some PDF fonts (observed in OUP academic typesetting using Merriweather
and Sabon) ship with broken ToUnicode CMaps for the standard `fi`, `fl`,
`ff`, `ffi`, `ffl` ligature glyphs:

  - The `ff` glyph maps to U+007C (`|`):
        differed → di|ered, effectuated → e|ectuated.

  - The `fi` glyph maps to U+007F (DEL):
        financial → \\x7fnancial, fixed → \\x7fxed.

The standard ligature codepoints U+FB01–U+FB04 are useless here — the
broken font never emitted them in the first place. We repair after
extraction by translating the two known marker characters when they
appear inside a word context. Both rules are universal and lossless on
well-formed PDFs (a real `|` outside a word stays put; a real DEL char
inside a word is always extraction noise).

We deliberately do NOT try to recover the silently-dropped `fl`/`ffi`/
`ffl` glyphs (where PyMuPDF simply emits nothing). There is no signal
to anchor on without per-font glyph-table inspection — that's a
separate, font-specific repair pass.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Tuple


# --- Standard Unicode ligature codepoints (well-formed PDFs) ----------
#
# These are the official Unicode ligature characters. A well-formed PDF
# may emit them directly; many TTS engines and downstream consumers
# don't speak them properly, so we normalize at extraction time rather
# than once-per-render. Deterministic, lossless 1:N character map.
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

# --- Broken-CMap marker chars (OUP-style font corruption) -------------
#
# Pipe between letters → ff (broken `ff` glyph mapped to U+007C).
_FF_RE = re.compile(r"(?<=[A-Za-z])\|(?=[A-Za-z])")

# DEL between/adjacent to letters → fi (broken `fi` glyph mapped to
# U+007F). We require at least one alphabetic neighbour so genuine
# control characters in binary blobs or pasteboard junk are left alone.
_FI_RE = re.compile(r"(?<=[A-Za-z])\x7f(?=[A-Za-z])|(?<=[A-Za-z])\x7f|\x7f(?=[A-Za-z])")


def expand_dropped_ligatures(text: str) -> str:
    """Normalize Unicode ligatures and repair known broken-CMap markers.

    Applied in order:

      1. Standard ligature codepoints U+FB00-FB06 + U+0132/0133
         (ﬁ → fi, ﬂ → fl, ﬀ → ff, ﬃ → ffi, ﬄ → ffl, etc.)

      2. `|` between letters  →  ff   (Sabon/Merriweather broken-CMap)
      3. `\\x7f` adjacent to letters  →  fi   (Merriweather broken-CMap)

    Other characters pass through untouched. Returns ``text`` unchanged
    when no rule applies.
    """
    if not text:
        return text
    out = _UNICODE_LIGATURE_RE.sub(lambda m: _UNICODE_LIGATURES[m.group(0)], text)
    out = _FF_RE.sub("ff", out)
    out = _FI_RE.sub("fi", out)
    return out


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
