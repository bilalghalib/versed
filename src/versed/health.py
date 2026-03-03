"""Dependency-light text health diagnostics for extracted PDF text."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class WordBBoxLike(Protocol):
    """Any object with `.text` and `.bbox`-style geometry."""

    text: str
    bbox: Tuple[float, float, float, float]


try:
    import ftfy

    HAS_FTFY = True
except ImportError:
    HAS_FTFY = False


def detect_mojibake(text: str) -> bool:
    """Return True when the string appears to contain mojibake."""
    if not text or len(text) < 3:
        return False

    if HAS_FTFY:
        fixed = ftfy.fix_text(text)
        if fixed != text:
            return True
        try:
            from ftfy.badness import text_cost

            if text_cost(text) > 10:
                return True
        except ImportError:
            pass

    return _detect_mojibake_heuristic(text)


def _detect_mojibake_heuristic(text: str) -> bool:
    if len(text) < 10:
        return False

    for char in ("\ufffd", "□", "■", "\x00"):
        if text.count(char) > len(text) * 0.05:
            return True

    arabic_count = len(re.findall(r"[\u0600-\u06FF]", text))
    english_count = len(re.findall(r"[a-zA-Z]", text))
    extended_latin_count = len(re.findall(r"[\u00C0-\u00FF\u0100-\u017F]", text))
    total = len(text)

    valid_ratio = (arabic_count + english_count) / total
    garbage_ratio = extended_latin_count / total
    if valid_ratio < 0.2 and garbage_ratio > 0.1:
        return True

    alphanum_count = len(re.findall(r"[\w\s]", text))
    return (alphanum_count / total) < 0.3


def fix_mojibake(text: str) -> Tuple[str, bool]:
    """Attempt to repair mojibake with ftfy when available."""
    if not text:
        return text, False

    if HAS_FTFY:
        fixed = ftfy.fix_text(text)
        return fixed, fixed != text

    return text, False


def _get_bbox_y(bbox: Any) -> float:
    if hasattr(bbox, "y"):
        return bbox.y
    if hasattr(bbox, "bbox"):
        return bbox.bbox[1]
    return 0.0


def _get_bbox_height(bbox: Any) -> float:
    if hasattr(bbox, "height"):
        return bbox.height
    if hasattr(bbox, "bbox"):
        return bbox.bbox[3] - bbox.bbox[1] if len(bbox.bbox) >= 4 else 0.0
    return 0.0


def detect_qcf_issues(bboxes: List[Any]) -> bool:
    """Detect undecoded QCF text or collapsed invisible-text geometry."""
    if not bboxes:
        return False

    text = " ".join(item.text for item in bboxes if hasattr(item, "text") and item.text)
    pua_count = len(re.findall(r"[\uE000-\uF8FF]", text))
    if text and pua_count > len(text) * 0.2:
        return True

    zero_height = sum(1 for item in bboxes if _get_bbox_height(item) <= 0.1)
    return zero_height > len(bboxes) * 0.5


def detect_double_honorifics(text: str) -> bool:
    """Detect redundant honorific encodings such as `ﷺ ﷺ`."""
    honorific_symbols = ["ﷺ", "ﷻ", "﷽", "\uFDF0", "\uFDF1", "\uFDF2"]
    latin_abbrevs = ["(pbuh)", "(saw)", "(s.a.w)", "(swt)", "(a.s)", "(r.a)", "PBUH", "SAW", "SWT"]
    arabic_expansions = ["صلى الله عليه وسلم", "عليه السلام", "رضي الله عنه", "جل جلاله"]

    for symbol in honorific_symbols:
        if f"{symbol} {symbol}" in text or f"{symbol}{symbol}" in text:
            return True

        for abbrev in latin_abbrevs:
            if abbrev in text and symbol in text and abs(text.find(symbol) - text.find(abbrev)) < 30:
                return True

        for expansion in arabic_expansions:
            if symbol in text and expansion in text:
                return True

    return False


def fix_double_honorifics(text: str) -> Tuple[str, bool]:
    """Collapse duplicate honorifics while keeping the symbol."""
    original = text
    patterns = [
        (r"\(pbuh\)\s*ﷺ", "ﷺ"),
        (r"ﷺ\s*\(pbuh\)", "ﷺ"),
        (r"\(saw\)\s*ﷺ", "ﷺ"),
        (r"ﷺ\s*\(saw\)", "ﷺ"),
        (r"\(swt\)\s*ﷻ", "ﷻ"),
        (r"ﷻ\s*\(swt\)", "ﷻ"),
        (r"ﷺ\s*ﷺ", "ﷺ"),
        (r"ﷻ\s*ﷻ", "ﷻ"),
        (r"ﷺ\s*صلى الله عليه وسلم", "ﷺ"),
        (r"صلى الله عليه وسلم\s*ﷺ", "ﷺ"),
    ]

    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text, text != original


def detect_pua_characters(text: str) -> Dict[str, int]:
    """Count private-use-area characters in the string."""
    counts: Dict[str, int] = {}
    for char in text:
        if "\uE000" <= char <= "\uF8FF":
            counts[char] = counts.get(char, 0) + 1
    return counts


def summarize_text_health(text: str, bboxes: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Return a compact diagnostic summary for UI or CLI display."""
    fixed_text, ftfy_changed = fix_mojibake(text)
    summary = {
        "has_mojibake": detect_mojibake(text),
        "ftfy_changed": ftfy_changed,
        "has_double_honorifics": detect_double_honorifics(text),
        "pua_characters": detect_pua_characters(text),
        "suggested_text": fixed_text,
    }
    if bboxes is not None:
        summary["has_qcf_issues"] = detect_qcf_issues(bboxes)
    return summary

