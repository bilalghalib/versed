"""Tests for public page classification."""

from versed.classify import (
    BackendConfig,
    PageProbe,
    PageType,
    classify_page,
    select_backend,
)


class TestClassifyPage:
    def test_qcf_probe_takes_priority(self, monkeypatch):
        monkeypatch.setattr(
            "versed.classify._probe_page",
            lambda pdf_path, page_number: PageProbe(12, 0, 0, 1, True, 0.0, True),
        )
        assert classify_page("dummy.pdf", 1) == PageType.QCF_QURAN

    def test_scanned_arabic_probe(self, monkeypatch):
        monkeypatch.setattr(
            "versed.classify._probe_page",
            lambda pdf_path, page_number: PageProbe(2, 2, 0, 0, False, 0.1, True),
        )
        assert classify_page("dummy.pdf", 1) == PageType.SCANNED_ARABIC

    def test_image_heavy_probe(self, monkeypatch):
        monkeypatch.setattr(
            "versed.classify._probe_page",
            lambda pdf_path, page_number: PageProbe(1, 0, 0, 0, False, 0.8, True),
        )
        assert classify_page("dummy.pdf", 1) == PageType.IMAGE_HEAVY


class TestSelectBackend:
    def test_select_backend_returns_config(self):
        config = select_backend(PageType.TEXT_ENGLISH)
        assert isinstance(config, BackendConfig)
        assert config.ocr_backend == "pymupdf"
        assert config.force_ocr is False

