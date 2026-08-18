"""Sentence and clause splitting that never replaces source paragraphs."""

from __future__ import annotations

import re
from dataclasses import dataclass

_AR_SPLIT = re.compile(r"(?<=[.!?؟۔])\s+")
_AR_CLAUSE_SPLIT = re.compile(r"(?<=[،؛])\s+")
_AR_MAX_WORDS = 55
_EN_ABBREVIATION = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|St|No|vol|pp|cf|viz|i\.e|e\.g)\.$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SplitSentence:
    index: int
    text: str


def split_arabic(text: str) -> list[SplitSentence]:
    terminal_parts = [part.strip() for part in _AR_SPLIT.split(text) if part.strip()]
    parts: list[str] = []
    for part in terminal_parts:
        if len(part.split()) <= _AR_MAX_WORDS:
            parts.append(part)
            continue
        clauses = [value.strip() for value in _AR_CLAUSE_SPLIT.split(part) if value.strip()]
        current: list[str] = []
        current_words = 0
        for clause in clauses:
            clause_words = len(clause.split())
            if current and current_words + clause_words > _AR_MAX_WORDS:
                parts.append(" ".join(current))
                current = []
                current_words = 0
            current.append(clause)
            current_words += clause_words
        if current:
            tail = " ".join(current)
            if parts and len(tail.split()) < 8:
                parts[-1] = f"{parts[-1]} {tail}"
            else:
                parts.append(tail)
    if not parts and text.strip():
        parts = [text.strip()]
    return [SplitSentence(index, part) for index, part in enumerate(parts)]


def split_english(text: str) -> list[SplitSentence]:
    stripped = text.strip()
    if not stripped:
        return []
    pieces: list[str] = []
    start = 0
    for match in re.finditer(r'[.!?]+["\u201d\u2019]*', stripped):
        end = match.end()
        chunk = stripped[start:end].strip()
        if not chunk:
            continue
        if _EN_ABBREVIATION.search(chunk.split()[-1]):
            continue
        following = stripped[end:].lstrip()
        if following and following[0] not in '"\u201c\u2018' and not following[0].isupper():
            continue
        pieces.append(chunk)
        start = end
    tail = stripped[start:].strip()
    if tail:
        pieces.append(tail)
    return [SplitSentence(index, part) for index, part in enumerate(pieces or [stripped])]
