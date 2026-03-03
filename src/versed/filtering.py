"""Portable filtering helpers for spurious PUA/presentation-form tokens."""

from __future__ import annotations

from typing import Any, List

from .honorifics import HONORIFIC_SYMBOLS, decode_honorific
from .qcf import is_qcf_glyph


def is_pua_or_presentation(text: str) -> bool:
    """Return True when all characters are PUA or Arabic presentation forms."""
    if not text:
        return False

    def _in_range(codepoint: int) -> bool:
        return (
            0xE000 <= codepoint <= 0xF8FF
            or 0xFB50 <= codepoint <= 0xFDEF
            or 0xFE70 <= codepoint <= 0xFEFC
        )

    return all(_in_range(ord(char)) for char in text)


def _is_honorific_token(text: str) -> bool:
    if text in HONORIFIC_SYMBOLS:
        return True
    _, honorifics = decode_honorific(text)
    return bool(honorifics)


def filter_spurious_bboxes(bboxes: List[Any]) -> tuple[List[Any], int]:
    """Drop undecoded ghost tokens while preserving valid QCF/honorific content."""
    filtered = []
    removed_ghost_qcf = 0

    for bbox in bboxes:
        text = getattr(bbox, "text", "") or ""
        if not text:
            continue

        is_qcf = getattr(bbox, "is_qcf", False)
        qcf_arabic = getattr(bbox, "qcf_arabic", None)
        qcf_verse_key = getattr(bbox, "qcf_verse_key", None)

        if is_pua_or_presentation(text) and not _is_honorific_token(text):
            if is_qcf and (qcf_arabic or qcf_verse_key):
                filtered.append(bbox)
                continue
            if is_qcf_glyph(text):
                removed_ghost_qcf += 1
                continue
            continue

        filtered.append(bbox)

    return filtered, removed_ghost_qcf


def filter_spurious_tokens(words: List[Any]) -> List[Any]:
    """Drop bogus PUA/presentation-form tokens from a token list."""
    filtered = []
    for word in words:
        if isinstance(word, dict):
            text = (word.get("text", "") or "").strip()
        else:
            text = (getattr(word, "text", "") or "").strip()
        if not text:
            continue
        if is_pua_or_presentation(text) and not _is_honorific_token(text) and not is_qcf_glyph(text):
            continue
        filtered.append(word)
    return filtered
