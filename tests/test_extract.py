"""Tests for the public extract orchestrator."""

from versed.classify import PageType
from versed.extract import extract_document


class _FakePage:
    def __init__(self, words):
        self._words = words

    def get_text(self, mode):
        if mode == "words":
            return self._words
        if mode == "dict":
            return {"blocks": []}
        raise ValueError(mode)


class _FakeDoc:
    def __init__(self, pages):
        self._pages = pages

    def __len__(self):
        return len(self._pages)

    def __getitem__(self, index):
        return self._pages[index]

    def close(self):
        return None


class _FakePyMuPDF:
    def __init__(self, doc):
        self._doc = doc

    def open(self, path):
        return self._doc


class TestExtractDocument:
    def test_extract_native_text_page(self, monkeypatch):
        fake_doc = _FakeDoc(
            [
                _FakePage(
                    [
                        (0.0, 0.0, 10.0, 10.0, "Hello", 0, 0, 0),
                        (11.0, 0.0, 20.0, 10.0, "world", 0, 0, 1),
                    ]
                )
            ]
        )

        monkeypatch.setattr("versed.extract._load_pymupdf", lambda: _FakePyMuPDF(fake_doc))
        monkeypatch.setattr("versed.extract.classify_page", lambda pdf_path, page_number: PageType.TEXT_ENGLISH)

        result = extract_document("dummy.pdf", title="Demo")
        assert "Hello world" in result.markdown
        assert result.stats["unsupported_pages"] == []

    def test_extract_reports_unsupported_scanned_page(self, monkeypatch):
        fake_doc = _FakeDoc([_FakePage([])])

        monkeypatch.setattr("versed.extract._load_pymupdf", lambda: _FakePyMuPDF(fake_doc))
        monkeypatch.setattr("versed.extract.classify_page", lambda pdf_path, page_number: PageType.SCANNED_ENGLISH)

        result = extract_document("dummy.pdf", title="Demo", allow_ocr=False)
        assert result.stats["unsupported_pages"] == [1]
        assert "OCR required" in result.pages[0]["warnings"][0]

