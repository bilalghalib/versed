from dataclasses import replace

import pytest

from versed.alignment.anchors import (
    discover_paragraph_anchors,
    discover_structural_links,
)
from versed.alignment.engine import align_documents
from versed.alignment.metrics import score_region_gold
from versed.alignment.models import (
    AlignmentDocument,
    AlignmentParagraph,
    AlignmentStructure,
    sha256_text,
)
from versed.alignment.validation import validate_alignment_result


def _document(language, structures, *, work_id="demo"):
    units = []
    for unit_index, (heading, texts) in enumerate(structures):
        unit_id = f"{language}:u{unit_index:04d}"
        paragraphs = tuple(
            AlignmentParagraph.create(
                paragraph_id=f"{unit_id}:p{paragraph_index:04d}",
                sequence=paragraph_index,
                text=text,
            )
            for paragraph_index, text in enumerate(texts)
        )
        units.append(AlignmentStructure(unit_id, unit_index, heading, paragraphs, heading))
    source = "\n".join(heading + "\n" + "\n".join(texts) for heading, texts in structures)
    return AlignmentDocument(work_id, language, f"{language}.txt", sha256_text(source), tuple(units))


def test_distinctive_number_becomes_monotonic_landmark_and_sentence_detail():
    arabic = _document("ar", [("", ["بلغ الفتى ٢١ عاما ثم خرج إلى المدينة."])])
    english = _document("en", [("", ["The youth reached 21 years, then left for the city."])])

    result = align_documents(arabic, english)

    assert result.diagnostics["landmarks"][0]["evidence"] == ["number:21"]
    assert result.recommended_links[0].resolution == "sentence"
    assert "hard_landmark" in result.paragraph_links[0].flags


def test_length_only_zooms_out_to_paragraph_instead_of_claiming_sentence_precision():
    arabic = _document("ar", [("", ["دخل الرجل المدينة ثم عاد إلى أهله."])])
    english = _document("en", [("", ["A traveler entered the city and later returned home."])])

    result = align_documents(arabic, english)

    assert result.diagnostics["landmarks"] == []
    assert result.recommended_links[0].resolution == "paragraph"
    assert result.metrics["status"] == "unscored"


def test_oversized_unanchored_interval_zooms_out_to_local_region():
    arabic = _document("ar", [("", ["نص أول.", "نص ثان."])])
    english = _document("en", [("", ["First text.", "Second text."])])

    result = align_documents(arabic, english, max_cells=1)

    assert result.diagnostics["coarse_intervals"] == 1
    assert result.recommended_links[0].resolution == "region"
    assert "dp_window_too_large" in result.recommended_links[0].flags


def test_oversized_interval_does_not_allocate_semantic_score_matrix():
    class FailIfCalled:
        model_name = "test"

        def encode(self, _texts):
            return []

        def scorer(self, _arabic, _english):
            raise AssertionError("semantic scorer must not be built for an oversized interval")

    arabic = _document("ar", [("", ["نص أول.", "نص ثان."])])
    english = _document("en", [("", ["First text.", "Second text."])])

    result = align_documents(arabic, english, paragraph_embedder=FailIfCalled(), max_cells=1)

    assert result.diagnostics["coarse_intervals"] == 1


def test_bilateral_numbered_headings_confirm_structural_sequence():
    arabic = _document("ar", [("الباب ١", ["ألف"]), ("الباب ٢", ["باء"])])
    english = _document("en", [("Chapter 1", ["A"]), ("Chapter 2", ["B"])])

    links = discover_structural_links(arabic, english)

    assert len(links) == 2
    assert all(link.method == "bilateral_structure_sequence" for link in links)


def test_bilateral_spine_ignores_quarantined_front_matter():
    arabic = _document(
        "ar",
        [
            ("المقامة البلخية", ["ألف"]),
            ("المقامة البغدادية", ["باء"]),
        ],
    )
    arabic = replace(
        arabic,
        structures=tuple(
            replace(unit, metadata={"heading_family": "maqama"})
            for unit in arabic.structures
        ),
    )
    english = _document(
        "en",
        [
            ("", ["Translator's preface"]),
            ("I. THE MAQAMA OF BALKH", ["A"]),
            ("II. THE MAQAMA OF BAGHDAD", ["B"]),
        ],
    )
    front = english.structures[0]
    english = replace(
        english,
        structures=(
            replace(
                front,
                paragraphs=tuple(
                    replace(
                        paragraph,
                        flags=("exclude_from_alignment", "front_matter"),
                    )
                    for paragraph in front.paragraphs
                ),
            ),
            *(
                replace(unit, metadata={"heading_family": "maqama"})
                for unit in english.structures[1:]
            ),
        ),
    )

    links = discover_structural_links(arabic, english)

    assert len(links) == 2
    assert all("en:u0000" not in link.english_structure_ids for link in links)


def test_one_weak_capitalized_word_does_not_become_a_landmark():
    arabic = _document("ar", [("", ["هذه جزيرة واسعة وفيها أشجار كثيرة."])])
    english = _document("en", [("", ["The Island contained trees and open country."])])

    anchors = discover_paragraph_anchors(
        list(arabic.structures[0].paragraphs),
        list(english.structures[0].paragraphs),
    )

    assert anchors == []


def test_large_landmark_search_keeps_unique_numbers_without_name_cross_product(
    monkeypatch,
):
    arabic = _document("ar", [("", [f"فقرة {index}" for index in range(501)])])
    english = _document("en", [("", [f"Paragraph {index}" for index in range(501)])])

    def fail_name_comparison(*_args, **_kwargs):
        raise AssertionError("large intervals must not enter pairwise name comparison")

    monkeypatch.setattr("versed.alignment.anchors.landmark_evidence", fail_name_comparison)
    anchors = discover_paragraph_anchors(
        list(arabic.structures[0].paragraphs),
        list(english.structures[0].paragraphs),
    )

    assert len(anchors) == 501
    assert anchors[250].evidence == ("number:250",)


def test_doubt_is_emitted_as_a_stable_review_item():
    arabic = _document("ar", [("", ["دخل الرجل المدينة ثم عاد إلى أهله."])])
    english = _document("en", [("", ["A traveler entered the city and later returned home."])])

    result = align_documents(arabic, english)

    assert len(result.review_items) == 1
    assert result.review_items[0].resolution == "paragraph"
    assert "zoomed_out_to_paragraph" in result.review_items[0].reasons
    assert result.review_items[0].id.startswith("review:")


def test_structural_clamp_rejects_cross_unit_paragraph_link():
    arabic = _document("ar", [("الباب ١", ["ألف"]), ("الباب ٢", ["باء"])])
    english = _document("en", [("Chapter 1", ["A"]), ("Chapter 2", ["B"])])
    result = align_documents(arabic, english)
    bad_link = replace(
        result.paragraph_links[0],
        english_paragraph_ids=(english.structures[1].paragraphs[0].id,),
    )
    bad = replace(result, paragraph_links=(bad_link, *result.paragraph_links[1:]))

    with pytest.raises(ValueError, match="crosses its structural clamp"):
        validate_alignment_result(bad)


def test_passage_text_gold_reports_span_precision_separately_from_recall():
    arabic = _document(
        "ar",
        [("", ["رأى الفتى النار المضيئة واقترب منها.", "ثم عاد إلى مأواه في الليل."])],
    )
    english = _document(
        "en",
        [("", ["The youth saw the bright fire and approached it.", "He returned home at night."])],
    )
    result = align_documents(arabic, english)

    metrics = score_region_gold(
        result,
        [
            {
                "id": "fire",
                "arabic": "رأى الفتى النار المضيئة واقترب منها.",
                "english": "The youth saw the bright fire and approached it.",
            }
        ],
    )

    assert metrics["status"] == "scored"
    assert metrics["paragraph_correct"] == 1.0
    assert 0 < metrics["span_precision_mean"] <= metrics["span_recall_mean"]
