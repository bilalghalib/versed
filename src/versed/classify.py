"""Evidence-based local page classification for PDF extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PageType(Enum):
    TEXT_ENGLISH = "text_english"
    TEXT_ARABIC_ENGLISH = "text_arabic_english"
    QCF_QURAN = "qcf_quran"
    SCANNED_ARABIC = "scanned_arabic"
    SCANNED_ENGLISH = "scanned_english"
    TABLE_LAYOUT = "table_layout"
    IMAGE_HEAVY = "image_heavy"


@dataclass
class BackendConfig:
    """Recommended extraction configuration for a page type."""

    force_ocr: bool
    ocr_backend: str
    arabic_engine: str
    confidence_note: str
    fallback: Optional[str] = None


@dataclass
class PageProbe:
    """Lightweight probe results from native extraction."""

    word_count: int
    arabic_word_count: int
    english_word_count: int
    pua_count: int
    has_qcf_fonts: bool
    image_area_ratio: float
    page_exists: bool


MIN_WORDS_FOR_TEXT = 10
ARABIC_RATIO_THRESHOLD = 0.1
IMAGE_HEAVY_THRESHOLD = 0.55


def _probe_page(pdf_path: str, page_number: int) -> PageProbe:
    """Run a fast native-text probe using PyMuPDF only."""
    try:
        import pymupdf
    except ImportError as exc:
        raise ImportError(
            "classify_page requires pymupdf: pip install 'versed-pdf[pdf]'"
        ) from exc

    try:
        document = pymupdf.open(pdf_path)
    except Exception:
        return PageProbe(0, 0, 0, 0, False, 0.0, False)

    page_index = page_number - 1
    if page_index < 0 or page_index >= len(document):
        document.close()
        return PageProbe(0, 0, 0, 0, False, 0.0, False)

    page = document[page_index]
    page_area = page.rect.width * page.rect.height
    words_raw = page.get_text("words")

    arabic_count = 0
    english_count = 0
    pua_count = 0
    has_qcf_fonts = False

    for word in words_raw:
        text = word[4] if len(word) > 4 else ""
        if re.search(r"[\u0600-\u06FF]", text):
            arabic_count += 1
        if re.search(r"[A-Za-z]{2,}", text):
            english_count += 1
        if any("\uE000" <= char <= "\uF8FF" for char in text):
            pua_count += 1

    blocks = []
    try:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    font = span.get("font", "")
                    if font.startswith("QCF_") or font.startswith("KFGQPC"):
                        has_qcf_fonts = True
                        break
                if has_qcf_fonts:
                    break
            if has_qcf_fonts:
                break
    except Exception:
        blocks = []

    image_area = 0.0
    for block in blocks:
        if block.get("type") == 1:
            bbox = block.get("bbox", (0, 0, 0, 0))
            image_area += max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])

    document.close()

    return PageProbe(
        word_count=len(words_raw),
        arabic_word_count=arabic_count,
        english_word_count=english_count,
        pua_count=pua_count,
        has_qcf_fonts=has_qcf_fonts,
        image_area_ratio=(image_area / page_area) if page_area else 0.0,
        page_exists=True,
    )


def classify_page(pdf_path: str, page_number: int) -> PageType:
    """Classify a PDF page with no OCR or API calls."""
    probe = _probe_page(pdf_path, page_number)

    if not probe.page_exists:
        return PageType.SCANNED_ENGLISH

    if probe.has_qcf_fonts or probe.pua_count > 0:
        return PageType.QCF_QURAN

    if probe.word_count < MIN_WORDS_FOR_TEXT:
        if probe.image_area_ratio >= IMAGE_HEAVY_THRESHOLD:
            return PageType.IMAGE_HEAVY
        if probe.arabic_word_count > probe.english_word_count:
            return PageType.SCANNED_ARABIC
        return PageType.SCANNED_ENGLISH

    arabic_ratio = (
        probe.arabic_word_count / probe.word_count if probe.word_count else 0.0
    )
    if arabic_ratio >= ARABIC_RATIO_THRESHOLD:
        return PageType.TEXT_ARABIC_ENGLISH

    return PageType.TEXT_ENGLISH


def select_backend(page_type: PageType) -> BackendConfig:
    """Return the recommended local extraction configuration for a page type."""
    configs = {
        PageType.TEXT_ENGLISH: BackendConfig(
            force_ocr=False,
            ocr_backend="pymupdf",
            arabic_engine="kraken",
            confidence_note="High: native text extraction is fastest and cleanest.",
            fallback="tesseract",
        ),
        PageType.TEXT_ARABIC_ENGLISH: BackendConfig(
            force_ocr=False,
            ocr_backend="pymupdf",
            arabic_engine="kraken",
            confidence_note="High: native text preserves mixed-language structure.",
            fallback="tesseract",
        ),
        PageType.QCF_QURAN: BackendConfig(
            force_ocr=False,
            ocr_backend="pymupdf",
            arabic_engine="kraken",
            confidence_note="Critical: native text preserves QCF glyphs for decoding.",
            fallback=None,
        ),
        PageType.TABLE_LAYOUT: BackendConfig(
            force_ocr=False,
            ocr_backend="pymupdf",
            arabic_engine="kraken",
            confidence_note="High: native layout is usually preferable for tables.",
            fallback="tesseract",
        ),
        PageType.SCANNED_ARABIC: BackendConfig(
            force_ocr=True,
            ocr_backend="tesseract",
            arabic_engine="kraken",
            confidence_note="Medium: scanned Arabic needs OCR.",
            fallback="nested",
        ),
        PageType.SCANNED_ENGLISH: BackendConfig(
            force_ocr=True,
            ocr_backend="tesseract",
            arabic_engine="kraken",
            confidence_note="Medium: scanned English needs OCR.",
            fallback=None,
        ),
        PageType.IMAGE_HEAVY: BackendConfig(
            force_ocr=True,
            ocr_backend="tesseract",
            arabic_engine="kraken",
            confidence_note="Low: image-heavy pages usually need OCR or human review.",
            fallback="nested",
        ),
    }
    return configs[page_type]


def classify_and_select(pdf_path: str, page_number: int) -> tuple[PageType, BackendConfig]:
    """Convenience wrapper that combines classification and backend selection."""
    page_type = classify_page(pdf_path, page_number)
    return page_type, select_backend(page_type)

