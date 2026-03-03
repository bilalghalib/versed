"""Tests for public routing heuristics."""

from versed.routing import PageObservations, TaskNeeds, route_enrichment


class TestRouting:
    def test_no_text_routes_to_vision(self):
        decision = route_enrichment(PageObservations(has_text_layer=False, word_count=0))
        assert decision.action == "enrich_vision"

    def test_mojibake_routes_to_text(self):
        decision = route_enrichment(
            PageObservations(
                has_text_layer=True,
                word_count=120,
                mojibake_count=5,
                mojibake_rate=0.01,
            )
        )
        assert decision.action == "enrich_text"

    def test_clean_page_skips(self):
        decision = route_enrichment(
            PageObservations(
                has_text_layer=True,
                word_count=120,
                qcf_detected=True,
            ),
            task=TaskNeeds(),
        )
        assert decision.action == "skip"

