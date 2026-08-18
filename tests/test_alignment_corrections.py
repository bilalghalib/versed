import pytest

from versed.alignment.corrections import apply_review_corrections
from versed.alignment.engine import align_documents
from versed.alignment.models import (
    AlignmentDocument,
    AlignmentParagraph,
    AlignmentStructure,
    sha256_text,
)


def _document(language: str, texts: list[str]) -> AlignmentDocument:
    paragraphs = tuple(
        AlignmentParagraph.create(
            paragraph_id=f"{language}:u0000:p{index:04d}",
            sequence=index,
            text=text,
        )
        for index, text in enumerate(texts)
    )
    structure = AlignmentStructure(f"{language}:u0000", 0, "", paragraphs)
    source = "\n".join(texts)
    return AlignmentDocument("demo", language, f"{language}.txt", sha256_text(source), (structure,))


def _result():
    return align_documents(
        _document("ar", ["دخل الرجل المدينة.", "ثم عاد إلى أهله."]),
        _document("en", ["A traveler entered the city.", "He later returned home."]),
    )


def test_human_acceptance_is_recorded_without_changing_correspondence():
    result = _result()
    item = result.review_items[0]

    corrected = apply_review_corrections(
        result,
        [{"review_id": item.id, "action": "accept", "note": "Checked against the scan."}],
    )

    assert corrected.recommended_links == result.recommended_links
    assert corrected.review_items[0].status == "human_accepted"


def test_replace_correction_changes_only_the_recommended_layer():
    result = _result()
    item = result.review_items[0]
    replacement = result.english.structures[0].paragraphs[-1].id

    corrected = apply_review_corrections(
        result,
        [
            {
                "review_id": item.id,
                "action": "replace",
                "note": "The second paragraph is the matching region.",
                "resolution": "paragraph",
                "arabic_ids": [result.arabic.structures[0].paragraphs[0].id],
                "english_ids": [replacement],
            }
        ],
    )

    assert corrected.recommended_links[item.recommended_link_index].english_ids == (replacement,)
    assert corrected.review_items[0].status == "human_corrected"


def test_stale_review_id_fails_loud():
    with pytest.raises(ValueError, match="stale or unknown"):
        apply_review_corrections(
            _result(),
            [{"review_id": "review:stale", "action": "reject", "note": "Wrong passage."}],
        )
