"""Cheap cross-script evidence for alignment and landmark discovery.

This is intentionally a matching skeleton, not display transliteration. It
throws vowels and ambiguous Arabic letters away so proper names can provide
ordered landmarks across Arabic script and scholarly English transliteration.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

_ARABIC_MAP = {
    "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh",
    "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "", "غ": "gh",
    "ف": "f", "ق": "k", "ك": "k", "ل": "l", "م": "m", "ن": "n",
    "ه": "h", "ة": "h", "و": "", "ي": "", "ى": "", "ئ": "",
    "ؤ": "", "ء": "", "ا": "", "أ": "", "إ": "", "آ": "", "ٱ": "",
    "پ": "b", "چ": "j", "ژ": "z", "گ": "k",
}
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z'’ʿʻ-]*")
_LATIN_DROP = re.compile(r"[aeiouwy'’ʿʻâîûāīū-]", re.IGNORECASE)
_DEDUPE = re.compile(r"(.)\1+")
_NUMBER = re.compile(r"\d+")
_STOPWORDS = frozenset(
    ["a", "an", "the", "and", "or", "of", "on", "in", "to", "us", "by", "from", "with", "for", "said", "says", "related", "reported", "ibn", "bin", "ben", "abu", "abi", "abd", "umm", "bint", "banu", "bani", "al", "el", "god", "allah", "prophet", "messenger", "chapter", "book", "section", "part", "page", "volume", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "his", "her", "their", "this", "that", "which", "who", "was", "were", "is", "are"]
)


@lru_cache(maxsize=16_384)
def arabic_skeleton(text: str, *, ta_marbuta: str = "h") -> str:
    text = _DIACRITICS.sub("", text)
    output: list[str] = []
    for character in text:
        if character == "ة":
            output.append(ta_marbuta)
        else:
            output.append(_ARABIC_MAP.get(character, ""))
    return _DEDUPE.sub(r"\1", "".join(output))


@lru_cache(maxsize=16_384)
def latin_skeleton(token: str) -> str:
    value = _LATIN_DROP.sub("", token.lower())
    value = re.sub(r"[^a-z]", "", value)
    return _DEDUPE.sub(r"\1", value)


@lru_cache(maxsize=16_384)
def english_name_skeletons(text: str, *, minimum_length: int = 3) -> tuple[str, ...]:
    output: list[str] = []
    for match in _LATIN_TOKEN.finditer(text):
        raw = match.group(0)
        for part in raw.split("-"):
            token = part.strip("'’ʿʻ")
            if not token or token.lower() in _STOPWORDS or not token[0].isupper():
                continue
            previous = text[:match.start()].rstrip()
            sentence_initial = not previous or previous[-1] in ".!?"
            transliterated = bool(
                re.search(r"(?:kh|gh|dh|th|sh|q|['’ʿʻ])", token, re.IGNORECASE)
            )
            mostly_upper = sum(character.isupper() for character in token) >= max(2, len(token) // 2)
            if sentence_initial and not transliterated and not mostly_upper:
                continue
            skeleton = latin_skeleton(token)
            if len(skeleton) >= minimum_length:
                output.append(skeleton)
    return tuple(dict.fromkeys(output))


@lru_cache(maxsize=16_384)
def english_anchor_skeletons(text: str, *, minimum_length: int = 3) -> tuple[str, ...]:
    """High-precision subset suitable for hard paragraph landmarks.

    Capitalization alone is intentionally insufficient. Hard name landmarks
    must carry a strong transliteration cue that ordinary English rarely has.
    """
    output: list[str] = []
    for match in _LATIN_TOKEN.finditer(text):
        raw = match.group(0)
        for part in raw.split("-"):
            token = part.strip()
            if not token or not token[0].isupper() or token.lower() in _STOPWORDS:
                continue
            if not re.search(r"(?:kh|gh|dh|q|['’ʿʻāīū])", token, re.IGNORECASE):
                continue
            skeleton = latin_skeleton(token)
            if len(skeleton) >= minimum_length:
                output.append(skeleton)
    return tuple(dict.fromkeys(output))


def skeleton_variants(skeleton: str) -> frozenset[str]:
    return frozenset(
        {
            skeleton,
            skeleton.replace("dh", "z"),
            skeleton.replace("dh", "d"),
            skeleton.replace("th", "t"),
            skeleton.replace("q", "k"),
        }
    )


def normalized_numbers(text: str) -> frozenset[str]:
    values: set[str] = set()
    for raw in _NUMBER.findall(text):
        try:
            values.add("".join(str(unicodedata.digit(character)) for character in raw))
        except (TypeError, ValueError):
            continue
    return frozenset(values)


@dataclass(frozen=True)
class LandmarkEvidence:
    name_skeletons: tuple[str, ...] = ()
    numbers: tuple[str, ...] = ()

    @property
    def mass(self) -> int:
        return sum(len(value) for value in self.name_skeletons) + 6 * len(self.numbers)


def landmark_evidence(arabic: str, english: str) -> LandmarkEvidence:
    arabic_blobs = (
        arabic_skeleton(arabic, ta_marbuta="h"),
        arabic_skeleton(arabic, ta_marbuta="t"),
    )
    matched: list[str] = []
    for skeleton in english_name_skeletons(english):
        variants = skeleton_variants(skeleton)
        if any(variant and variant in blob for variant in variants for blob in arabic_blobs):
            matched.append(skeleton)
    matched_names = tuple(dict.fromkeys(matched))
    numbers = tuple(sorted(normalized_numbers(arabic) & normalized_numbers(english)))
    return LandmarkEvidence(matched_names, numbers)


def estimate_length_ratio(arabic: list[str], english: list[str]) -> float:
    arabic_words = sum(len(value.split()) for value in arabic)
    english_words = sum(len(value.split()) for value in english)
    if not arabic_words or not english_words:
        return 1.5
    return min(4.0, max(0.4, english_words / arabic_words))


def pair_score(arabic: str, english: str, *, length_ratio: float) -> float:
    if not arabic.strip() or not english.strip():
        return -2.4
    evidence = landmark_evidence(arabic, english)
    names = min(1.0, sum(len(value) for value in evidence.name_skeletons) / 10.0)
    numbers = 1.0 if evidence.numbers else 0.0
    expected = max(1.0, len(arabic.split()) * length_ratio)
    observed = max(1.0, float(len(english.split())))
    length = math.exp(-abs(math.log(observed / expected)))
    return 0.55 * names + 0.25 * numbers + 0.65 * length - 0.45


def distinctive_counts(values: list[str]) -> Counter[str]:
    return Counter(value for text in values for value in normalized_numbers(text))
