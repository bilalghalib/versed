"""Conservative structural and paragraph landmark discovery."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .models import AlignmentDocument, AlignmentParagraph, StructuralLink
from .scoring import (
    english_anchor_skeletons,
    landmark_evidence,
    normalized_numbers,
)


@dataclass(frozen=True)
class ParagraphAnchor:
    arabic_index: int
    english_index: int
    score: int
    evidence: tuple[str, ...]


def discover_structural_links(
    arabic: AlignmentDocument,
    english: AlignmentDocument,
) -> tuple[StructuralLink, ...]:
    """Use a bilateral ordered spine only when headings confirm it."""
    ar_units = arabic.structures
    en_units = english.structures
    if len(ar_units) == len(en_units) and len(ar_units) >= 2:
        confirmations: list[tuple[str, ...]] = []
        for ar_unit, en_unit in zip(ar_units, en_units):
            evidence = landmark_evidence(ar_unit.heading, en_unit.heading)
            markers = (
                *(f"name:{value}" for value in evidence.name_skeletons),
                *(f"number:{value}" for value in evidence.numbers),
            )
            confirmations.append(markers if evidence.mass >= 4 else ())
        required = max(2, (len(ar_units) + 3) // 4)
        if sum(bool(value) for value in confirmations) >= required:
            return tuple(
                StructuralLink(
                    arabic_structure_ids=(ar_unit.id,),
                    english_structure_ids=(en_unit.id,),
                    method="bilateral_structure_sequence",
                    score_confidence=0.92,
                    evidence=confirmations[index],
                )
                for index, (ar_unit, en_unit) in enumerate(zip(ar_units, en_units))
            )
    return (
        StructuralLink(
            arabic_structure_ids=tuple(unit.id for unit in ar_units),
            english_structure_ids=tuple(unit.id for unit in en_units),
            method="whole_book_unanchored",
            score_confidence=0.2,
            flags=("unanchored_structure", "review_required"),
        ),
    )


def _number_counts(paragraphs: list[AlignmentParagraph]) -> Counter[str]:
    return Counter(number for paragraph in paragraphs for number in normalized_numbers(paragraph.text))


def _weighted_monotone(candidates: list[ParagraphAnchor]) -> list[ParagraphAnchor]:
    """Maximum-weight increasing subsequence; crossing landmarks are discarded."""
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda item: (item.arabic_index, item.english_index, -item.score))
    best = [float(item.score) for item in ordered]
    previous: list[int | None] = [None] * len(ordered)
    for index, item in enumerate(ordered):
        for earlier in range(index):
            candidate = ordered[earlier]
            if candidate.arabic_index >= item.arabic_index or candidate.english_index >= item.english_index:
                continue
            score = best[earlier] + item.score
            if score > best[index]:
                best[index] = score
                previous[index] = earlier
    cursor = max(range(len(ordered)), key=best.__getitem__)
    path: list[ParagraphAnchor] = []
    while cursor is not None:
        path.append(ordered[cursor])
        cursor = previous[cursor]
    path.reverse()
    return path


def discover_paragraph_anchors(
    arabic: list[AlignmentParagraph],
    english: list[AlignmentParagraph],
) -> list[ParagraphAnchor]:
    """Find rare numbers or strong transliterated names that agree in order.

    A single ordinary capitalized English token is never sufficient. Name-only
    landmarks require either two matches or one long, unique skeleton.
    """
    ar_number_counts = _number_counts(arabic)
    en_number_counts = _number_counts(english)
    english_name_counts = Counter(
        skeleton
        for paragraph in english
        for skeleton in set(english_anchor_skeletons(paragraph.text))
    )
    candidates: list[ParagraphAnchor] = []
    for en_index, en_paragraph in enumerate(english):
        scored: list[tuple[int, int, tuple[str, ...]]] = []
        for ar_index, ar_paragraph in enumerate(arabic):
            evidence = landmark_evidence(ar_paragraph.text, en_paragraph.text)
            unique_numbers = tuple(
                value
                for value in evidence.numbers
                if ar_number_counts[value] == 1 and en_number_counts[value] == 1
            )
            rare_names = tuple(
                value
                for value in evidence.name_skeletons
                if value in english_name_counts and english_name_counts[value] <= 2
            )
            name_mass = sum(len(value) for value in rare_names)
            strong_names = (
                len(rare_names) >= 2
            )
            if unique_numbers:
                score = 20 + 6 * len(unique_numbers) + name_mass
            elif strong_names and name_mass >= 7:
                score = name_mass
            else:
                continue
            markers = (
                *(f"number:{value}" for value in unique_numbers),
                *(f"name:{value}" for value in rare_names),
            )
            scored.append((score, ar_index, markers))
        if not scored:
            continue
        scored.sort(reverse=True)
        best_score, best_ar, markers = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0
        if best_score - second_score < 3 and not any(value.startswith("number:") for value in markers):
            continue
        candidates.append(ParagraphAnchor(best_ar, en_index, best_score, markers))

    # One Arabic paragraph cannot hard-anchor two English paragraphs.
    by_ar: dict[int, ParagraphAnchor] = {}
    for candidate in candidates:
        current = by_ar.get(candidate.arabic_index)
        if current is None or candidate.score > current.score:
            by_ar[candidate.arabic_index] = candidate
    return _weighted_monotone(list(by_ar.values()))
