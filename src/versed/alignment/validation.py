"""Cross-layer invariants for alignment results."""

from __future__ import annotations

from .models import AlignmentResult


def validate_alignment_result(result: AlignmentResult) -> None:
    """Assert that every fine-grained link stays inside its structural pair."""
    result.arabic.validate()
    result.english.validate()
    ar_paragraph_unit = {
        paragraph.id: structure.id
        for structure in result.arabic.structures
        for paragraph in structure.paragraphs
    }
    en_paragraph_unit = {
        paragraph.id: structure.id
        for structure in result.english.structures
        for paragraph in structure.paragraphs
    }
    ar_sentence_paragraph = {value.id: value.paragraph_id for value in result.arabic_sentences}
    en_sentence_paragraph = {value.id: value.paragraph_id for value in result.english_sentences}

    def structural_pair(index: int) -> tuple[set[str], set[str]]:
        if index < 0 or index >= len(result.structural_links):
            raise ValueError(f"link references unknown structural pair {index}")
        link = result.structural_links[index]
        return set(link.arabic_structure_ids), set(link.english_structure_ids)

    for index, link in enumerate(result.paragraph_links):
        allowed_ar, allowed_en = structural_pair(link.structural_link_index)
        try:
            actual_ar = {ar_paragraph_unit[value] for value in link.arabic_paragraph_ids}
            actual_en = {en_paragraph_unit[value] for value in link.english_paragraph_ids}
        except KeyError as exc:
            raise ValueError(f"paragraph link {index} references unknown id {exc.args[0]!r}") from exc
        if not actual_ar <= allowed_ar or not actual_en <= allowed_en:
            raise ValueError(f"paragraph link {index} crosses its structural clamp")

    for index, link in enumerate(result.sentence_links):
        if link.paragraph_link_index < 0 or link.paragraph_link_index >= len(result.paragraph_links):
            raise ValueError(f"sentence link {index} references unknown paragraph link")
        parent = result.paragraph_links[link.paragraph_link_index]
        try:
            actual_ar = {ar_sentence_paragraph[value] for value in link.arabic_sentence_ids}
            actual_en = {en_sentence_paragraph[value] for value in link.english_sentence_ids}
        except KeyError as exc:
            raise ValueError(f"sentence link {index} references unknown id {exc.args[0]!r}") from exc
        if not actual_ar <= set(parent.arabic_paragraph_ids) or not actual_en <= set(parent.english_paragraph_ids):
            raise ValueError(f"sentence link {index} crosses its paragraph clamp")

    def recommendation_units(ids: tuple[str, ...], resolution: str, *, language: str) -> set[str]:
        paragraph_units = ar_paragraph_unit if language == "ar" else en_paragraph_unit
        sentence_paragraph = ar_sentence_paragraph if language == "ar" else en_sentence_paragraph
        try:
            if resolution == "structure":
                return set(ids)
            if resolution in {"paragraph", "region"}:
                return {paragraph_units[value] for value in ids}
            return {paragraph_units[sentence_paragraph[value]] for value in ids}
        except KeyError as exc:
            raise ValueError(f"recommendation references unknown {language} id {exc.args[0]!r}") from exc

    for index, link in enumerate(result.recommended_links):
        actual_ar = recommendation_units(link.arabic_ids, link.resolution, language="ar")
        actual_en = recommendation_units(link.english_ids, link.resolution, language="en")
        if not any(
            actual_ar <= set(structural.arabic_structure_ids)
            and actual_en <= set(structural.english_structure_ids)
            for structural in result.structural_links
        ):
            raise ValueError(f"recommended link {index} crosses the structural clamp")

    for index, item in enumerate(result.review_items):
        if item.recommended_link_index < 0 or item.recommended_link_index >= len(result.recommended_links):
            raise ValueError(f"review item {index} references unknown recommendation")
        link = result.recommended_links[item.recommended_link_index]
        if (
            item.arabic_ids != link.arabic_ids
            or item.english_ids != link.english_ids
            or item.resolution != link.resolution
        ):
            raise ValueError(f"review item {item.id!r} no longer matches its recommendation")
