"""Public local PDF-to-Markdown extraction orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .arabic import is_arabic
from .classify import PageType, classify_page, select_backend
from .filtering import filter_spurious_tokens
from .honorifics import decode_honorific, normalize_text
from .markdown import BUILDER_VERSION, build_enhanced_markdown
from .qcf import QCFDecoder, is_qcf_text
from .repair import extract_repairable_font_spans, repair_words_with_font_info
from .types import AlignedWord, Document


ENGINE_VERSION = "1.1.0"


@dataclass
class ExtractResult:
    """Full result of a public extraction run."""

    markdown: str
    plain_text: str
    document: Document
    pages: List[Dict[str, Any]]
    stats: Dict[str, Any]
    version: str = ENGINE_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "markdown": self.markdown,
            "plain_text": self.plain_text,
            "document": self.document.to_dict(),
            "pages": self.pages,
            "stats": self.stats,
            "version": self.version,
        }


def extract_document(
    pdf_path: str,
    *,
    title: str = "",
    allow_ocr: bool = False,
    output_format: str = "markdown",
) -> ExtractResult:
    """Extract a local PDF into semantic markdown and structured diagnostics."""
    del output_format  # Reserved for future behavior switches.

    pymupdf = _load_pymupdf()
    document = pymupdf.open(pdf_path)
    decoder = QCFDecoder.get_instance()

    aligned_words: List[AlignedWord] = []
    page_reports: List[Dict[str, Any]] = []
    unsupported_pages: List[int] = []

    for page_index in range(len(document)):
        page_number = page_index + 1
        page = document[page_index]
        page_type = classify_page(pdf_path, page_number)
        backend = select_backend(page_type)

        report = {
            "page_number": page_number,
            "page_type": page_type.value,
            "backend": backend.ocr_backend,
            "used_ocr": False,
            "warnings": [],
        }

        if backend.force_ocr:
            if allow_ocr:
                try:
                    ocr_text = _extract_ocr_text(page)
                except ImportError as exc:
                    report["warnings"].append(str(exc))
                except Exception as exc:
                    report["warnings"].append(f"OCR failed for this page: {exc}")
                else:
                    if ocr_text.strip():
                        aligned_words.extend(_build_words_from_text(ocr_text, page_number, source="ocr"))
                        report["used_ocr"] = True
                    else:
                        report["warnings"].append("OCR produced no text for this page.")
            else:
                report["warnings"].append(
                    "OCR required for this page. Re-run with --allow-ocr and install 'versed-pdf[ocr]'."
                )
        else:
            native_words = _extract_native_page_words(page, page_number, decoder, page_type)
            if native_words:
                aligned_words.extend(native_words)
            elif page_type == PageType.QCF_QURAN:
                report["warnings"].append("QCF page detected but no decodable text was recovered.")

        if backend.force_ocr and not report["used_ocr"]:
            unsupported_pages.append(page_number)

        page_reports.append(report)

    document.close()

    markdown_result = build_enhanced_markdown(aligned_words, title=title)
    public_document = _document_from_words(aligned_words, title)

    used_ocr_pages = [report["page_number"] for report in page_reports if report["used_ocr"]]

    stats = {
        "input_path": str(Path(pdf_path)),
        "total_pages": len(page_reports),
        "processed_pages": len(page_reports) - len(unsupported_pages),
        "unsupported_pages": unsupported_pages,
        "used_ocr_pages": used_ocr_pages,
        "word_count": len(aligned_words),
        "builder_version": BUILDER_VERSION,
    }

    return ExtractResult(
        markdown=markdown_result.markdown,
        plain_text=markdown_result.plain_text,
        document=public_document,
        pages=page_reports,
        stats=stats,
        version=ENGINE_VERSION,
    )


def _document_from_words(aligned_words: List[AlignedWord], title: str) -> Document:
    from .layout import document_from_aligned_words

    return document_from_aligned_words(aligned_words, title=title)


def _load_pymupdf():
    try:
        import pymupdf
    except ImportError as exc:
        raise ImportError(
            "extract_document requires pymupdf: pip install 'versed-pdf[pdf]'"
        ) from exc
    return pymupdf


def _load_ocr_dependencies():
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise ImportError(
            "OCR requested but unavailable. Install with: pip install 'versed-pdf[ocr]'."
        ) from exc
    return pytesseract, Image


def _extract_native_page_words(
    page: Any,
    page_number: int,
    decoder: QCFDecoder,
    page_type: PageType,
) -> List[AlignedWord]:
    words_raw = page.get_text("words")
    if not words_raw:
        return []

    font_spans = extract_repairable_font_spans(page)
    repaired_words = repair_words_with_font_info(words_raw, font_spans)
    qcf_font = _find_qcf_font_name(page)

    aligned_words: List[AlignedWord] = []
    for word in repaired_words:
        if len(word) < 5:
            continue

        x0, y0, x1, y1 = word[0], word[1], word[2], word[3]
        text = word[4] or ""
        block_no = int(word[5]) if len(word) > 5 else 0
        line_no = int(word[6]) if len(word) > 6 else 0
        word_no = int(word[7]) if len(word) > 7 else 0

        verse_key: Optional[str] = None
        role = "quran" if page_type == PageType.QCF_QURAN else "body"

        if qcf_font and is_qcf_text(text):
            decoded_text, decoded_words = decoder.decode_text(text, qcf_font)
            text = decoded_text.strip()
            verse_keys = {item.verse_key for item in decoded_words if item.verse_key}
            if len(verse_keys) == 1:
                verse_key = next(iter(verse_keys))
            role = "quran"

        display_text, spoken_text = _expand_token_text(text)
        if not display_text and not spoken_text:
            continue

        aligned_words.append(
            AlignedWord(
                text=display_text or spoken_text,
                spoken_text=spoken_text or display_text,
                language="ar" if is_arabic(display_text or spoken_text) else "en",
                role=role,
                section_type="body",
                verse_key=verse_key,
                block_no=(page_number * 1_000_000) + block_no,
                line_no=line_no,
                word_no=word_no,
                x=x0,
                y=y0,
                width=x1 - x0,
                height=y1 - y0,
                meta={"page": page_number},
            )
        )

    filtered_words = filter_spurious_tokens(aligned_words)
    result: List[AlignedWord] = []
    for word in filtered_words:
        if isinstance(word, AlignedWord):
            result.append(word)
    return result


def _extract_ocr_text(page: Any) -> str:
    pytesseract, Image = _load_ocr_dependencies()
    pymupdf = _load_pymupdf()
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
    mode = "RGBA" if pixmap.alpha else "RGB"
    image = Image.frombytes(mode, [pixmap.width, pixmap.height], pixmap.samples)
    return pytesseract.image_to_string(image)


def _build_words_from_text(text: str, page_number: int, *, source: str) -> List[AlignedWord]:
    aligned_words: List[AlignedWord] = []
    block_base = page_number * 1_000_000
    for line_index, line in enumerate(text.splitlines()):
        tokens = line.split()
        for word_index, token in enumerate(tokens):
            display_text, spoken_text = _expand_token_text(token)
            if not display_text and not spoken_text:
                continue
            aligned_words.append(
                AlignedWord(
                    text=display_text or spoken_text,
                    spoken_text=spoken_text or display_text,
                    language="ar" if is_arabic(display_text or spoken_text) else "en",
                    role="body",
                    section_type="body",
                    block_no=block_base + line_index,
                    line_no=line_index,
                    word_no=word_index,
                    meta={"page": page_number, "source": source},
                )
            )
    return aligned_words


def _expand_token_text(text: str) -> tuple[str, str]:
    normalized = normalize_text(text or "").strip()
    if not normalized:
        return "", ""

    cleaned, honorifics = decode_honorific(normalized)
    display_text = cleaned.strip() or normalized
    spoken_text = display_text

    if honorifics:
        expansions = [item.get("arabic", "").strip() for item in honorifics if item.get("arabic")]
        if not cleaned.strip():
            display_text = " ".join(item.get("unicode", "").strip() for item in honorifics).strip() or normalized
        if expansions:
            spoken_text = " ".join(part for part in [cleaned.strip(), " ".join(expansions)] if part).strip()
            if not spoken_text:
                spoken_text = " ".join(expansions).strip()

    return display_text.strip(), spoken_text.strip() or display_text.strip()


def _find_qcf_font_name(page: Any) -> Optional[str]:
    try:
        text_dict = page.get_text("dict")
    except Exception:
        return None

    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                font = span.get("font", "")
                if font.startswith("QCF_") or font.startswith("KFGQPC"):
                    return font
    return None
