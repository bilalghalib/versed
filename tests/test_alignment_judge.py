from versed.alignment.engine import align_documents
from versed.alignment.judge import JudgeDecision, OllamaJudge, review_with_judge
from versed.alignment.models import (
    AlignmentDocument,
    AlignmentParagraph,
    AlignmentStructure,
    sha256_text,
)


def _document(language: str, text: str) -> AlignmentDocument:
    paragraph = AlignmentParagraph.create(
        paragraph_id=f"{language}:u0000:p0000", sequence=0, text=text
    )
    structure = AlignmentStructure(f"{language}:u0000", 0, "", (paragraph,))
    return AlignmentDocument("demo", language, f"{language}.txt", sha256_text(text), (structure,))


class _Judge:
    model_name = "test-judge"

    def judge(self, arabic: str, english: str) -> JudgeDecision:
        assert "المدينة" in arabic
        assert "city" in english
        return JudgeDecision("aligned", 0.91, "Same journey.", self.model_name)


def test_model_review_is_provenance_and_does_not_rewrite_the_link():
    result = align_documents(
        _document("ar", "دخل الرجل المدينة ثم عاد إلى أهله."),
        _document("en", "A traveler entered the city and later returned home."),
    )
    original = result.recommended_links

    reviewed = review_with_judge(result, _Judge())

    assert reviewed.recommended_links == original
    assert reviewed.review_items[0].status == "model_accepted"
    assert reviewed.review_items[0].evidence["model_review"]["verdict"] == "aligned"
    assert reviewed.diagnostics["model_review"]["rewrote_alignment"] is False


def test_ollama_endpoint_is_restricted_to_loopback():
    try:
        OllamaJudge("gemma3:1b", base_url="https://example.com")
    except ValueError as exc:
        assert "local HTTP endpoint" in str(exc)
    else:
        raise AssertionError("remote Ollama endpoint was accepted")
