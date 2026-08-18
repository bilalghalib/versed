"""Hierarchical alignment with explicit sentence-to-structure fallback."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from statistics import mean

from .anchors import (
    ParagraphAnchor,
    discover_paragraph_anchors,
    discover_structural_links,
)
from .dp import PARAGRAPH_MOVES, SENTENCE_MOVES, DPLink, SpanScorer, align_spans
from .models import (
    AlignmentDocument,
    AlignmentParagraph,
    AlignmentResult,
    AlignmentSentence,
    ParagraphLink,
    RecommendedLink,
    ReviewItem,
    SentenceLink,
    StructuralLink,
    sha256_text,
)
from .sentences import split_arabic, split_english
from .validation import validate_alignment_result


def _structure_index(document: AlignmentDocument):
    return {structure.id: structure for structure in document.structures}


def _selected_paragraphs(
    structure_ids: Iterable[str],
    structures: dict,
) -> list[AlignmentParagraph]:
    output: list[AlignmentParagraph] = []
    for structure_id in structure_ids:
        if structure_id not in structures:
            raise ValueError(f"structural link references unknown unit {structure_id!r}")
        output.extend(
            paragraph
            for paragraph in structures[structure_id].paragraphs
            if "exclude_from_alignment" not in paragraph.flags
        )
    return output


def _sentences(
    paragraphs: Iterable[AlignmentParagraph],
    *,
    language: str,
    global_start: int,
) -> tuple[list[AlignmentSentence], int]:
    output: list[AlignmentSentence] = []
    global_sequence = global_start
    for paragraph in paragraphs:
        split = split_arabic(paragraph.text) if language == "ar" else split_english(paragraph.text)
        for value in split:
            sentence_id = f"{paragraph.id}:s{value.index:04d}"
            output.append(
                AlignmentSentence(
                    id=sentence_id,
                    paragraph_id=paragraph.id,
                    sequence=value.index,
                    global_sequence=global_sequence,
                    text=value.text,
                    source_hash=sha256_text(value.text),
                )
            )
            global_sequence += 1
    return output, global_sequence


def _offset_link(link: DPLink, ar_offset: int, en_offset: int) -> DPLink:
    return DPLink(
        link.arabic_start + ar_offset,
        link.arabic_end + ar_offset,
        link.english_start + en_offset,
        link.english_end + en_offset,
        link.operation,
        link.score,
        link.score_confidence,
        link.uncertainty_radius,
        link.flags,
    )


def _align_with_landmarks(
    arabic: list[AlignmentParagraph],
    english: list[AlignmentParagraph],
    *,
    scorer: SpanScorer | None,
    paragraph_embedder=None,
    max_cells: int,
) -> tuple[list[DPLink], list[ParagraphAnchor], bool]:
    anchors = discover_paragraph_anchors(arabic, english)
    output: list[DPLink] = []
    ar_cursor = en_cursor = 0
    coarse = False

    def align_interval(ar_end: int, en_end: int) -> None:
        nonlocal ar_cursor, en_cursor, coarse
        ar_values = [value.text for value in arabic[ar_cursor:ar_end]]
        en_values = [value.text for value in english[en_cursor:en_end]]
        try:
            links = align_spans(
                ar_values,
                en_values,
                span_scorer=(
                    paragraph_embedder.scorer(ar_values, en_values)
                    if paragraph_embedder and ar_values and en_values else scorer
                ),
                moves=PARAGRAPH_MOVES,
                skip_cost=0.55 if paragraph_embedder else 1.1,
                max_cells=max_cells,
            )
        except ValueError as exc:
            if "too large" not in str(exc):
                raise
            coarse = True
            if ar_values or en_values:
                links = [
                    DPLink(
                        0, len(ar_values), 0, len(en_values),
                        f"{len(ar_values)}-{len(en_values)}", 0.0, 0.2, 3,
                        ("coarse_interval", "dp_window_too_large"),
                    )
                ]
            else:
                links = []
        output.extend(_offset_link(link, ar_cursor, en_cursor) for link in links)

    for anchor in anchors:
        align_interval(anchor.arabic_index, anchor.english_index)
        output.append(
            DPLink(
                anchor.arabic_index,
                anchor.arabic_index + 1,
                anchor.english_index,
                anchor.english_index + 1,
                "1-1",
                1.0,
                0.94,
                0,
                ("hard_landmark", *anchor.evidence),
            )
        )
        ar_cursor = anchor.arabic_index + 1
        en_cursor = anchor.english_index + 1
    align_interval(len(arabic), len(english))
    return output, anchors, coarse


def _coverage(all_ids: set[str], covered: set[str]) -> float:
    return round(len(all_ids & covered) / len(all_ids), 6) if all_ids else 1.0


def _review_items(
    links: list[RecommendedLink],
    *,
    arabic_source_hash: str,
    english_source_hash: str,
) -> tuple[ReviewItem, ...]:
    """Expose every non-trivial doubt instead of hiding it in a score."""
    output: list[ReviewItem] = []
    for index, link in enumerate(links):
        reasons = set(link.flags)
        if link.resolution != "sentence":
            reasons.add(f"zoomed_out_to_{link.resolution}")
        if link.uncertainty_radius:
            reasons.add("nonzero_uncertainty_radius")
        if link.score_confidence < 0.70:
            reasons.add("low_score_confidence")
        if not reasons:
            continue
        if link.resolution in {"region", "structure"} or "coarse_interval" in link.flags:
            priority = "high"
        elif link.resolution == "paragraph" or link.score_confidence < 0.55:
            priority = "medium"
        else:
            priority = "low"
        identity = "\0".join(
            (
                str(index),
                arabic_source_hash,
                english_source_hash,
                link.resolution,
                *link.arabic_ids,
                "=>",
                *link.english_ids,
            )
        )
        output.append(
            ReviewItem(
                id=f"review:{sha256_text(identity)[:20]}",
                recommended_link_index=index,
                priority=priority,
                arabic_ids=link.arabic_ids,
                english_ids=link.english_ids,
                resolution=link.resolution,
                score_confidence=link.score_confidence,
                uncertainty_radius=link.uncertainty_radius,
                reasons=tuple(sorted(reasons)),
                evidence={"recommendation_reason": link.reason},
            )
        )
    return tuple(output)


def _prewarm_paragraph_semantic_cache(
    embedder,
    arabic: AlignmentDocument,
    english: AlignmentDocument,
) -> None:
    """Encode book features in full batches before per-link scorer creation."""
    encode = getattr(embedder, "encode", None)
    if not callable(encode):
        return
    ar_paragraphs = [
        paragraph
        for structure in arabic.structures
        for paragraph in structure.paragraphs
        if "exclude_from_alignment" not in paragraph.flags
    ]
    en_paragraphs = [
        paragraph
        for structure in english.structures
        for paragraph in structure.paragraphs
        if "exclude_from_alignment" not in paragraph.flags
    ]
    paragraph_texts = [value.text for value in (*ar_paragraphs, *en_paragraphs)]
    encode(paragraph_texts)


def align_documents(
    arabic: AlignmentDocument,
    english: AlignmentDocument,
    *,
    structural_links: Iterable[StructuralLink] | None = None,
    paragraph_scorer: SpanScorer | None = None,
    sentence_scorer: SpanScorer | None = None,
    paragraph_embedder=None,
    sentence_embedder=None,
    max_cells: int = 2_000_000,
    sentence_detail_threshold: float = 0.60,
    paragraph_detail_threshold: float = 0.45,
) -> AlignmentResult:
    """Align documents and recommend only the finest locally justified level."""
    arabic.validate()
    english.validate()
    if arabic.language != "ar" or english.language != "en":
        raise ValueError("align_documents expects Arabic then English")
    if arabic.work_id != english.work_id:
        raise ValueError(f"work ids differ: {arabic.work_id!r} != {english.work_id!r}")
    if max_cells <= 0:
        raise ValueError("max_cells must be positive")
    links = tuple(structural_links or discover_structural_links(arabic, english))

    if paragraph_embedder is not None:
        _prewarm_paragraph_semantic_cache(paragraph_embedder, arabic, english)

    ar_structures = _structure_index(arabic)
    en_structures = _structure_index(english)
    paragraph_links: list[ParagraphLink] = []
    sentence_links: list[SentenceLink] = []
    recommended: list[RecommendedLink] = []
    ar_sentences_all: list[AlignmentSentence] = []
    en_sentences_all: list[AlignmentSentence] = []
    next_ar_sentence = next_en_sentence = 0
    landmark_rows: list[dict] = []
    coarse_intervals = 0

    for structural_index, structural in enumerate(links):
        ar_paragraphs = _selected_paragraphs(structural.arabic_structure_ids, ar_structures)
        en_paragraphs = _selected_paragraphs(structural.english_structure_ids, en_structures)
        path, anchors, was_coarse = _align_with_landmarks(
            ar_paragraphs,
            en_paragraphs,
            scorer=paragraph_scorer,
            paragraph_embedder=paragraph_embedder,
            max_cells=max_cells,
        )
        coarse_intervals += int(was_coarse)
        landmark_rows.extend(
            {
                "structural_link_index": structural_index,
                "arabic_paragraph_id": ar_paragraphs[anchor.arabic_index].id,
                "english_paragraph_id": en_paragraphs[anchor.english_index].id,
                "score": anchor.score,
                "evidence": list(anchor.evidence),
            }
            for anchor in anchors
        )

        for step in path:
            ar_slice = ar_paragraphs[step.arabic_start:step.arabic_end]
            en_slice = en_paragraphs[step.english_start:step.english_end]
            paragraph_index = len(paragraph_links)
            paragraph_link = ParagraphLink(
                arabic_paragraph_ids=tuple(value.id for value in ar_slice),
                english_paragraph_ids=tuple(value.id for value in en_slice),
                operation=step.operation,
                score_confidence=step.score_confidence,
                uncertainty_radius=step.uncertainty_radius,
                structural_link_index=structural_index,
                flags=step.flags,
            )
            paragraph_links.append(paragraph_link)

            ar_sentences, next_ar_sentence = _sentences(
                ar_slice, language="ar", global_start=next_ar_sentence
            )
            en_sentences, next_en_sentence = _sentences(
                en_slice, language="en", global_start=next_en_sentence
            )
            ar_sentences_all.extend(ar_sentences)
            en_sentences_all.extend(en_sentences)
            local_sentence_links: list[SentenceLink] = []

            sentence_allowed = (
                bool(ar_slice)
                and bool(en_slice)
                and step.score_confidence >= paragraph_detail_threshold
                and "coarse_interval" not in step.flags
                and "skip" not in step.flags
            )
            if sentence_allowed:
                sentence_path = align_spans(
                    [value.text for value in ar_sentences],
                    [value.text for value in en_sentences],
                    span_scorer=(
                        sentence_embedder.scorer(
                            [value.text for value in ar_sentences],
                            [value.text for value in en_sentences],
                        )
                        if sentence_embedder else sentence_scorer
                    ),
                    moves=SENTENCE_MOVES,
                    skip_cost=0.55 if sentence_embedder else 1.1,
                    max_cells=max_cells,
                )
                for sentence_step in sentence_path:
                    sentence_link = SentenceLink(
                        arabic_sentence_ids=tuple(
                            value.id
                            for value in ar_sentences[sentence_step.arabic_start:sentence_step.arabic_end]
                        ),
                        english_sentence_ids=tuple(
                            value.id
                            for value in en_sentences[sentence_step.english_start:sentence_step.english_end]
                        ),
                        operation=sentence_step.operation,
                        score_confidence=sentence_step.score_confidence,
                        uncertainty_radius=sentence_step.uncertainty_radius,
                        paragraph_link_index=paragraph_index,
                        flags=sentence_step.flags,
                    )
                    sentence_links.append(sentence_link)
                    local_sentence_links.append(sentence_link)

            usable_sentence_links = [
                value
                for value in local_sentence_links
                if value.arabic_sentence_ids
                and value.english_sentence_ids
                and "skip" not in value.flags
            ]
            if (
                usable_sentence_links
                and min(value.score_confidence for value in usable_sentence_links)
                >= sentence_detail_threshold
            ):
                recommended.append(
                    RecommendedLink(
                        arabic_ids=tuple(value.id for value in ar_sentences),
                        english_ids=tuple(value.id for value in en_sentences),
                        resolution="sentence",
                        score_confidence=round(mean(value.score_confidence for value in usable_sentence_links), 6),
                        uncertainty_radius=max(value.uncertainty_radius for value in usable_sentence_links),
                        reason="sentence_path_above_threshold",
                    )
                )
            elif ar_slice and en_slice and step.score_confidence >= paragraph_detail_threshold:
                recommended.append(
                    RecommendedLink(
                        arabic_ids=paragraph_link.arabic_paragraph_ids,
                        english_ids=paragraph_link.english_paragraph_ids,
                        resolution="paragraph",
                        score_confidence=step.score_confidence,
                        uncertainty_radius=step.uncertainty_radius,
                        reason="sentence_evidence_too_weak",
                        flags=step.flags,
                    )
                )
            elif ar_slice and en_slice:
                recommended.append(
                    RecommendedLink(
                        arabic_ids=paragraph_link.arabic_paragraph_ids,
                        english_ids=paragraph_link.english_paragraph_ids,
                        resolution="region",
                        score_confidence=step.score_confidence,
                        uncertainty_radius=max(3, step.uncertainty_radius),
                        reason="paragraph_evidence_too_weak",
                        flags=tuple(sorted({*step.flags, "local_region_fallback"})),
                    )
                )
            else:
                recommended.append(
                    RecommendedLink(
                        arabic_ids=structural.arabic_structure_ids,
                        english_ids=structural.english_structure_ids,
                        resolution="structure",
                        score_confidence=structural.score_confidence,
                        uncertainty_radius=3,
                        reason="one_sided_omission_or_addition",
                        flags=tuple(sorted({*structural.flags, *step.flags})),
                    )
                )

    ar_paragraph_ids = {
        paragraph.id for structure in arabic.structures for paragraph in structure.paragraphs
        if "exclude_from_alignment" not in paragraph.flags
    }
    en_paragraph_ids = {
        paragraph.id for structure in english.structures for paragraph in structure.paragraphs
        if "exclude_from_alignment" not in paragraph.flags
    }
    covered_ar = {value for link in paragraph_links for value in link.arabic_paragraph_ids}
    covered_en = {value for link in paragraph_links for value in link.english_paragraph_ids}
    review_items = _review_items(
        recommended,
        arabic_source_hash=arabic.source_hash,
        english_source_hash=english.source_hash,
    )
    diagnostics = {
        "structural_links": len(links),
        "paragraph_links": len(paragraph_links),
        "sentence_links": len(sentence_links),
        "recommended_links": len(recommended),
        "review_items": len(review_items),
        "review_priority": dict(sorted(Counter(value.priority for value in review_items).items())),
        "recommended_resolution": dict(sorted(Counter(value.resolution for value in recommended).items())),
        "arabic_paragraph_coverage": _coverage(ar_paragraph_ids, covered_ar),
        "english_paragraph_coverage": _coverage(en_paragraph_ids, covered_en),
        "landmarks": landmark_rows,
        "coarse_intervals": coarse_intervals,
        "confidence_is_calibrated_probability": False,
        "paragraph_semantic_model": getattr(paragraph_embedder, "model_name", None),
        "sentence_semantic_model": getattr(sentence_embedder, "model_name", None),
        "semantic_context_waypoints": getattr(paragraph_embedder, "waypoint_count", 0),
    }
    result = AlignmentResult(
        arabic=arabic,
        english=english,
        structural_links=links,
        paragraph_links=tuple(paragraph_links),
        arabic_sentences=tuple(ar_sentences_all),
        english_sentences=tuple(en_sentences_all),
        sentence_links=tuple(sentence_links),
        recommended_links=tuple(recommended),
        review_items=review_items,
        diagnostics=diagnostics,
        metrics={
            "status": "unscored",
            "reason": "no independent gold links supplied",
            "coverage_diagnostics_are_not_accuracy": True,
        },
    )
    validate_alignment_result(result)
    return result
