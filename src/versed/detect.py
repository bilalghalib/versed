"""
Mojibake detection for Arabic PDF text.

Scans text for known encoding corruption patterns — Sabon font mojibake,
replacement characters, and other indicators of broken ToUnicode CMaps.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Known mojibake characters from Sabon font analysis.
# SabondiexPlain/SabondiacriticRoman fonts with MacRomanEncoding
# produce these when the PDF has broken ToUnicode CMaps for
# transliteration diacriticals (ṣ→ß, ī→¬, ḥ→¤).
KNOWN_MOJIBAKE_CHARS = frozenset("\ufffd\u00df\u00ac\u00a4")


@dataclass
class MojibakeReport:
    """Diagnostic report from mojibake detection."""
    has_mojibake: bool
    mojibake_count: int
    mojibake_rate: float          # count / total_chars
    mojibake_chars: Dict[str, int] = field(default_factory=dict)  # {char: count}
    sample_contexts: List[str] = field(default_factory=list)       # first 5 occurrences with surrounding text
    total_chars: int = 0


def detect_mojibake(text: str) -> MojibakeReport:
    """Scan text for known mojibake characters and return a diagnostic report.

    Args:
        text: The text to scan.

    Returns:
        MojibakeReport with counts, rates, and sample contexts.
    """
    if not text:
        return MojibakeReport(
            has_mojibake=False,
            mojibake_count=0,
            mojibake_rate=0.0,
            total_chars=0,
        )

    total_chars = len(text)
    mojibake_count = 0
    char_counts: Dict[str, int] = {}
    samples: List[str] = []

    for i, c in enumerate(text):
        if c in KNOWN_MOJIBAKE_CHARS:
            mojibake_count += 1
            char_counts[c] = char_counts.get(c, 0) + 1

            # Capture context (up to 20 chars around the mojibake)
            if len(samples) < 5:
                start = max(0, i - 10)
                end = min(len(text), i + 11)
                context = text[start:end]
                # Mark the mojibake char
                offset = i - start
                marked = context[:offset] + f"[{c!r}]" + context[offset + 1:]
                samples.append(marked)

    mojibake_rate = mojibake_count / max(total_chars, 1)

    return MojibakeReport(
        has_mojibake=mojibake_count > 0,
        mojibake_count=mojibake_count,
        mojibake_rate=mojibake_rate,
        mojibake_chars=char_counts,
        sample_contexts=samples,
        total_chars=total_chars,
    )


def detect_mojibake_in_pdf(
    pdf_path: str,
    page_number: Optional[int] = None,
) -> MojibakeReport:
    """Extract text from PDF page(s) and detect mojibake.

    Args:
        pdf_path: Path to the PDF file.
        page_number: 1-indexed page number. If None, scans all pages.

    Returns:
        MojibakeReport aggregated across scanned pages.

    Raises:
        ImportError: If pymupdf is not installed.
    """
    try:
        import pymupdf
    except ImportError:
        raise ImportError(
            "detect_mojibake_in_pdf requires pymupdf: pip install 'versed-repair[pdf]'"
        )

    doc = pymupdf.open(pdf_path)

    if page_number is not None:
        pages = [doc[page_number - 1]]
    else:
        pages = list(doc)

    all_text_parts = []
    for page in pages:
        words = page.get_text("words")
        for w in words:
            text = w[4] if len(w) > 4 else ""
            all_text_parts.append(text)

    doc.close()

    combined_text = " ".join(all_text_parts)
    return detect_mojibake(combined_text)
