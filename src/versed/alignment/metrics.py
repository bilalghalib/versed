"""Independent-gold scoring; coverage is never substituted for accuracy."""

from __future__ import annotations

import re
from collections.abc import Iterable
from statistics import mean
from typing import Any

from .models import AlignmentResult, AlignmentSentence

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def _sentence_index(values: Iterable[AlignmentSentence]) -> dict[str, AlignmentSentence]:
    return {value.id: value for value in values}


def _fraction(value: int, total: int) -> float:
    return round(value / total, 6) if total else 0.0


def score_sentence_gold(result: AlignmentResult, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    gold_rows = list(rows)
    if not gold_rows:
        return {
            "status": "unscored",
            "reason": "gold contained no sentence links",
            "coverage_diagnostics_are_not_accuracy": True,
        }
    ar_index = _sentence_index(result.arabic_sentences)
    en_index = _sentence_index(result.english_sentences)
    predicted_by_ar: dict[str, set[str]] = {}
    for link in result.sentence_links:
        for source_id in link.arabic_sentence_ids:
            predicted_by_ar.setdefault(source_id, set()).update(link.english_sentence_ids)

    exact = buffer_1 = buffer_2 = paragraph = catastrophic = 0
    ordered: list[tuple[int, bool]] = []
    details: list[dict[str, Any]] = []
    for position, row in enumerate(gold_rows, start=1):
        row_id = str(row.get("id") or f"gold-{position}")
        gold_ar = tuple(str(value) for value in row.get("arabic_sentence_ids") or ())
        gold_en = tuple(str(value) for value in row.get("english_sentence_ids") or ())
        if not gold_ar or not gold_en:
            raise ValueError(f"gold row {row_id!r} must name Arabic and English sentences")
        missing = [value for value in gold_ar if value not in ar_index] + [
            value for value in gold_en if value not in en_index
        ]
        if missing:
            raise ValueError(f"gold row {row_id!r} references unknown sentence ids: {missing[:3]}")
        predicted = set().union(*(predicted_by_ar.get(value, set()) for value in gold_ar))
        gold_set = set(gold_en)
        is_exact = predicted == gold_set
        predicted_positions = sorted(en_index[value].global_sequence for value in predicted)
        gold_positions = sorted(en_index[value].global_sequence for value in gold_set)
        within_1 = bool(predicted_positions) and (
            gold_positions[0] >= predicted_positions[0] - 1
            and gold_positions[-1] <= predicted_positions[-1] + 1
        )
        within_2 = bool(predicted_positions) and (
            gold_positions[0] >= predicted_positions[0] - 2
            and gold_positions[-1] <= predicted_positions[-1] + 2
        )
        paragraph_hit = bool(
            {en_index[value].paragraph_id for value in predicted}
            & {en_index[value].paragraph_id for value in gold_set}
        )
        exact += int(is_exact)
        buffer_1 += int(is_exact or within_1)
        buffer_2 += int(is_exact or within_2)
        paragraph += int(paragraph_hit)
        catastrophic += int(not paragraph_hit)
        ordered.append((min(ar_index[value].global_sequence for value in gold_ar), is_exact or within_2))
        details.append(
            {
                "id": row_id,
                "exact": is_exact,
                "buffer_1": is_exact or within_1,
                "buffer_2": is_exact or within_2,
                "paragraph_correct": paragraph_hit,
                "catastrophic": not paragraph_hit,
                "predicted_english_sentence_ids": sorted(predicted),
            }
        )

    ordered.sort()
    reanchor: list[int] = []
    for index, (start, good) in enumerate(ordered):
        if good:
            continue
        next_good = next((position for position, ok in ordered[index + 1:] if ok), None)
        if next_good is not None:
            reanchor.append(next_good - start)
    total = len(gold_rows)
    return {
        "status": "scored",
        "gold_links": total,
        "exact": _fraction(exact, total),
        "buffer_1": _fraction(buffer_1, total),
        "buffer_2": _fraction(buffer_2, total),
        "paragraph_correct": _fraction(paragraph, total),
        "catastrophic": _fraction(catastrophic, total),
        "reanchor_distance_mean": round(mean(reanchor), 3) if reanchor else None,
        "reanchor_distance_max": max(reanchor, default=None),
        "details": details,
    }


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(value.lower()))


def _ngram_set(tokens: tuple[str, ...], width: int = 4) -> set[tuple[str, ...]]:
    actual = min(width, len(tokens))
    if actual == 0:
        return set()
    return {tokens[index:index + actual] for index in range(len(tokens) - actual + 1)}


def _match_region_paragraphs(paragraphs, text: str) -> tuple[str, ...]:
    gold = _ngram_set(_tokens(text))
    if not gold:
        return ()
    scored: list[tuple[int, str, float]] = []
    for position, paragraph in enumerate(paragraphs):
        grams = _ngram_set(_tokens(paragraph.text))
        if not grams:
            continue
        score = len(grams & gold) / len(grams)
        if score >= 0.45:
            scored.append((position, paragraph.id, score))
    if not scored:
        return ()

    runs: list[list[tuple[int, str, float]]] = []
    for value in scored:
        if not runs or value[0] > runs[-1][-1][0] + 1:
            runs.append([value])
        else:
            runs[-1].append(value)
    best = max(runs, key=lambda run: (sum(value[2] for value in run), len(run)))
    return tuple(value[1] for value in best)


def score_region_gold(result: AlignmentResult, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Score passage-text gold when stable sentence ids are not available."""
    gold_rows = list(rows)
    if not gold_rows:
        return {
            "status": "unscored",
            "reason": "gold contained no passage regions",
            "coverage_diagnostics_are_not_accuracy": True,
        }
    ar_paragraphs = [
        paragraph
        for structure in result.arabic.structures
        for paragraph in structure.paragraphs
        if "exclude_from_alignment" not in paragraph.flags
    ]
    en_paragraphs = [
        paragraph
        for structure in result.english.structures
        for paragraph in structure.paragraphs
        if "exclude_from_alignment" not in paragraph.flags
    ]
    en_positions = {value.id: index for index, value in enumerate(en_paragraphs)}
    predicted_by_ar: dict[str, set[str]] = {}
    for link in result.paragraph_links:
        for source_id in link.arabic_paragraph_ids:
            predicted_by_ar.setdefault(source_id, set()).update(link.english_paragraph_ids)

    exact = buffer_1 = buffer_2 = paragraph = catastrophic = contains = 0
    span_precisions: list[float] = []
    span_recalls: list[float] = []
    mapping_failures = 0
    details: list[dict[str, Any]] = []
    for position, row in enumerate(gold_rows, start=1):
        row_id = str(row.get("id") or f"gold-{position}")
        arabic_text = str(row.get("arabic") or "")
        english_text = str(row.get("english") or row.get("reference_english") or "")
        if not arabic_text or not english_text:
            raise ValueError(f"region gold row {row_id!r} must contain Arabic and English text")
        gold_ar = _match_region_paragraphs(ar_paragraphs, arabic_text)
        gold_en = _match_region_paragraphs(en_paragraphs, english_text)
        if not gold_ar or not gold_en:
            mapping_failures += 1
            details.append(
                {
                    "id": row_id,
                    "mapped": False,
                    "arabic_paragraph_ids": list(gold_ar),
                    "english_paragraph_ids": list(gold_en),
                }
            )
            continue
        predicted = set().union(*(predicted_by_ar.get(value, set()) for value in gold_ar))
        gold_set = set(gold_en)
        overlap = predicted & gold_set
        is_exact = predicted == gold_set
        contains_gold = gold_set <= predicted
        predicted_positions = sorted(en_positions[value] for value in predicted)
        gold_positions = sorted(en_positions[value] for value in gold_set)
        within_1 = bool(predicted_positions) and (
            gold_positions[0] >= predicted_positions[0] - 1
            and gold_positions[-1] <= predicted_positions[-1] + 1
        )
        within_2 = bool(predicted_positions) and (
            gold_positions[0] >= predicted_positions[0] - 2
            and gold_positions[-1] <= predicted_positions[-1] + 2
        )
        precision = len(overlap) / len(predicted) if predicted else 0.0
        recall = len(overlap) / len(gold_set)
        exact += int(is_exact)
        contains += int(contains_gold)
        buffer_1 += int(is_exact or within_1)
        buffer_2 += int(is_exact or within_2)
        paragraph += int(bool(overlap))
        catastrophic += int(not overlap)
        span_precisions.append(precision)
        span_recalls.append(recall)
        details.append(
            {
                "id": row_id,
                "mapped": True,
                "exact": is_exact,
                "contains_gold_region": contains_gold,
                "buffer_1": is_exact or within_1,
                "buffer_2": is_exact or within_2,
                "paragraph_correct": bool(overlap),
                "catastrophic": not overlap,
                "span_precision": round(precision, 6),
                "span_recall": round(recall, 6),
                "predicted_english_paragraph_ids": sorted(predicted, key=en_positions.get),
                "gold_english_paragraph_ids": sorted(gold_set, key=en_positions.get),
            }
        )

    scored = len(gold_rows) - mapping_failures
    if not scored:
        return {
            "status": "unscored",
            "reason": "no region gold rows could be mapped to source paragraphs",
            "gold_regions": len(gold_rows),
            "mapping_failures": mapping_failures,
            "details": details,
        }
    return {
        "status": "scored",
        "gold_kind": "passage_region_text",
        "gold_regions": len(gold_rows),
        "scored_regions": scored,
        "mapping_failures": mapping_failures,
        "exact": _fraction(exact, scored),
        "contains_gold_region": _fraction(contains, scored),
        "buffer_1": _fraction(buffer_1, scored),
        "buffer_2": _fraction(buffer_2, scored),
        "paragraph_correct": _fraction(paragraph, scored),
        "catastrophic": _fraction(catastrophic, scored),
        "span_precision_mean": round(mean(span_precisions), 6),
        "span_recall_mean": round(mean(span_recalls), 6),
        "details": details,
    }
