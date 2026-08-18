"""Bounded variable-span monotonic dynamic programming."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from .scoring import (
    arabic_skeleton,
    english_name_skeletons,
    estimate_length_ratio,
    normalized_numbers,
    skeleton_variants,
)

PARAGRAPH_MOVES: tuple[tuple[int, int], ...] = (
    (1, 1), (1, 2), (2, 1), (2, 2), (1, 3), (3, 1),
    (2, 3), (3, 2), (1, 4), (4, 1), (1, 5), (5, 1),
    (1, 0), (0, 1),
)
SENTENCE_MOVES: tuple[tuple[int, int], ...] = (
    (1, 1), (1, 2), (2, 1), (2, 2), (1, 3), (3, 1),
    (1, 4), (4, 1), (1, 5), (5, 1), (1, 0), (0, 1),
)
SpanScorer = Callable[[list[str], int, int, list[str], int, int], float]


@dataclass(frozen=True)
class DPLink:
    arabic_start: int
    arabic_end: int
    english_start: int
    english_end: int
    operation: str
    score: float
    score_confidence: float
    uncertainty_radius: int
    flags: tuple[str, ...] = ()


def _join(values: list[str], start: int, end: int) -> str:
    return " ".join(values[start:end])


def default_span_scorer(arabic: list[str], english: list[str], length_ratio: float) -> SpanScorer:
    """Precompute item features so DP moves do not repeatedly parse text."""
    ar_h = [arabic_skeleton(value, ta_marbuta="h") for value in arabic]
    ar_t = [arabic_skeleton(value, ta_marbuta="t") for value in arabic]
    ar_numbers = [normalized_numbers(value) for value in arabic]
    en_names = [english_name_skeletons(value) for value in english]
    en_numbers = [normalized_numbers(value) for value in english]
    ar_words = [len(value.split()) for value in arabic]
    en_words = [len(value.split()) for value in english]

    def score(
        _arabic: list[str],
        ar_start: int,
        ar_end: int,
        _english: list[str],
        en_start: int,
        en_end: int,
    ) -> float:
        blobs = ("".join(ar_h[ar_start:ar_end]), "".join(ar_t[ar_start:ar_end]))
        names = {
            name
            for values in en_names[en_start:en_end]
            for name in values
        }
        matched = {
            name
            for name in names
            if any(
                variant and variant in blob
                for variant in skeleton_variants(name)
                for blob in blobs
            )
        }
        names_score = min(1.0, sum(len(value) for value in matched) / 10.0)
        source_numbers = set().union(*ar_numbers[ar_start:ar_end])
        target_numbers = set().union(*en_numbers[en_start:en_end])
        number_score = 1.0 if source_numbers & target_numbers else 0.0
        source_words = sum(ar_words[ar_start:ar_end])
        target_words = sum(en_words[en_start:en_end])
        expected = max(1.0, source_words * length_ratio)
        observed = max(1.0, float(target_words))
        length_score = math.exp(-abs(math.log(observed / expected)))
        return 0.55 * names_score + 0.25 * number_score + 0.65 * length_score - 0.45

    return score


def align_spans(
    arabic: list[str],
    english: list[str],
    *,
    span_scorer: SpanScorer | None = None,
    moves: tuple[tuple[int, int], ...] = SENTENCE_MOVES,
    skip_cost: float = 1.1,
    max_cells: int = 2_000_000,
) -> list[DPLink]:
    """Return a globally monotonic path inside one evidence-bounded interval."""
    n, m = len(arabic), len(english)
    if n == 0:
        return [DPLink(0, 0, j, j + 1, "0-1", -skip_cost, 0.12, 3, ("english_addition",)) for j in range(m)]
    if m == 0:
        return [DPLink(i, i + 1, 0, 0, "1-0", -skip_cost, 0.12, 3, ("arabic_omission",)) for i in range(n)]
    cells = (n + 1) * (m + 1)
    if cells > max_cells:
        raise ValueError(
            f"alignment interval is too large ({n}x{m}={cells} cells); "
            "add landmarks or increase max_cells deliberately"
        )

    ratio = estimate_length_ratio(arabic, english)
    score_span = span_scorer or default_span_scorer(arabic, english, ratio)
    negative = float("-inf")
    best = [[negative] * (m + 1) for _ in range(n + 1)]
    previous: list[list[tuple[int, int, str, float] | None]] = [
        [None] * (m + 1) for _ in range(n + 1)
    ]
    best[0][0] = 0.0

    for i in range(n + 1):
        for j in range(m + 1):
            if best[i][j] == negative:
                continue
            for da, de in moves:
                ni, nj = i + da, j + de
                if ni > n or nj > m or (da == 0 and de == 0):
                    continue
                if da and de:
                    score = score_span(arabic, i, ni, english, j, nj)
                    score -= 0.05 * (da + de - 2)
                else:
                    score = -skip_cost
                candidate = best[i][j] + score
                if candidate > best[ni][nj]:
                    best[ni][nj] = candidate
                    previous[ni][nj] = (i, j, f"{da}-{de}", score)

    links: list[DPLink] = []
    i, j = n, m
    while (i, j) != (0, 0):
        step = previous[i][j]
        if step is None:
            raise ValueError(f"alignment moves cannot reach terminal cell ({n}, {m})")
        pi, pj, operation, score = step
        # Length alone tops out below sentence-detail confidence. Distinctive
        # bilingual evidence or a semantic scorer must earn a tight link.
        confidence = max(0.12, min(0.97, 0.35 + score / 1.6))
        radius = 0 if confidence >= 0.88 else (1 if confidence >= 0.70 else 2)
        flags: tuple[str, ...] = ()
        if operation in {"1-0", "0-1"}:
            flags = ("skip",)
            radius = max(radius, 2)
        elif confidence < 0.55:
            flags = ("low_signal",)
        links.append(DPLink(pi, i, pj, j, operation, score, confidence, radius, flags))
        i, j = pi, pj
    links.reverse()
    return links
