"""Deterministic semantic markdown builder for public Document types."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from .layout import document_from_aligned_words
from .types import AlignedWord, BlockType, Document, TextBlock


BUILDER_VERSION = "1.0.0"


@dataclass
class EnhancedMarkdownResult:
    """Markdown output plus deterministic versioning metadata."""

    markdown: str
    plain_text: str
    version: str
    checksum: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "markdown": self.markdown,
            "plain_text": self.plain_text,
            "version": self.version,
            "checksum": self.checksum,
        }


def compute_aligned_words_checksum(
    aligned_words: Union[List[AlignedWord], List[Dict[str, object]]],
) -> str:
    """Compute a stable checksum over the semantic fields that affect rendering."""
    parts: List[str] = []
    for word in aligned_words:
        if isinstance(word, dict):
            spoken = str(word.get("spoken_text", word.get("text", "")))
            role = str(word.get("role", "body"))
            verse_key = str(word.get("verse_key") or "")
            block_no = int(word.get("block_no", 0) or 0)
        else:
            spoken = word.spoken_text or word.text
            role = word.role or "body"
            verse_key = word.verse_key or ""
            block_no = word.block_no or 0
        parts.append(f"{spoken}|{role}|{verse_key}|{block_no}")
    content = "\n".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def compute_cache_key(aligned_words_checksum: str, figures_checksum: str = "") -> str:
    """Combine content checksums with the builder version."""
    composite = f"{aligned_words_checksum}+{BUILDER_VERSION}+{figures_checksum}"
    return hashlib.sha256(composite.encode("utf-8")).hexdigest()[:16]


def build_enhanced_markdown(
    aligned_words: Union[List[AlignedWord], List[Dict[str, object]]],
    *,
    figures: Optional[List[Dict[str, object]]] = None,
    title: str = "",
) -> EnhancedMarkdownResult:
    """Build semantic markdown and plain text from aligned words."""
    document = document_from_aligned_words(aligned_words, title=title, figures=figures)
    words_checksum = compute_aligned_words_checksum(aligned_words)
    figures_checksum = _compute_figures_checksum(figures) if figures else ""
    return _build_markdown_from_document(
        document,
        checksum=compute_cache_key(words_checksum, figures_checksum),
    )

def build_markdown_from_document(document: Document) -> EnhancedMarkdownResult:
    """Build semantic markdown and plain text from a public Document."""
    return _build_markdown_from_document(
        document,
        checksum=_compute_document_checksum(document),
    )


def _build_markdown_from_document(
    document: Document,
    *,
    checksum: str,
) -> EnhancedMarkdownResult:
    markdown_parts: List[str] = []
    plain_parts: List[str] = []

    if document.title:
        markdown_parts.append(f"## {document.title}")
        plain_parts.append(document.title)

    for block in document.blocks:
        markdown_line, plain_line = _render_block(block)
        if markdown_line is not None:
            markdown_parts.append(markdown_line)
        if plain_line is not None:
            plain_parts.append(plain_line)

    return EnhancedMarkdownResult(
        markdown="\n\n".join(markdown_parts),
        plain_text="\n\n".join(plain_parts),
        version=BUILDER_VERSION,
        checksum=checksum,
    )


def _render_block(block: TextBlock) -> tuple[Optional[str], Optional[str]]:
    text = block.text.strip()
    if not text:
        return None, None

    meta = block.meta or {}
    verse_key = meta.get("verse_key")
    hadith_ref = meta.get("hadith_ref")
    dominant_role = meta.get("dominant_role", "body")

    if block.type == BlockType.HEADING:
        return f"## {text}", text

    if block.type == BlockType.VERSE:
        suffix_md = f" **[{verse_key}]**" if verse_key else ""
        suffix_plain = f" [{verse_key}]" if verse_key else ""
        return f"> {text}{suffix_md}", f"{text}{suffix_plain}"

    if block.type == BlockType.BASMALA:
        return f"> {text}", text

    if block.type == BlockType.FOOTNOTE:
        return f"---\n{text}", text

    if block.type == BlockType.FIGURE:
        figure_type = meta.get("figure_type", "image")
        label = meta.get("label", "Figure")
        caption = meta.get("caption", "")
        description = text

        markdown = (
            f'<!-- figure:start type={figure_type} label="{label}" -->\n'
            f"**{label} ({figure_type}):** {caption}\n"
        )
        if description and description != caption:
            markdown += f"\nDescription: {description}\n"
        markdown += "<!-- figure:end -->"
        plain = f"[Figure: {description or caption or label}]"
        return markdown, plain

    if block.type == BlockType.ISNAD:
        return f"**Isnad:** {text}", f"Isnad: {text}"

    if block.type == BlockType.MATN:
        return f"**Matn:** {text}", f"Matn: {text}"

    if dominant_role in ("quran", "quran_arabic"):
        suffix_md = f" **[{verse_key}]**" if verse_key else ""
        suffix_plain = f" [{verse_key}]" if verse_key else ""
        return f"> {text}{suffix_md}", f"{text}{suffix_plain}"

    if dominant_role in ("hadith", "hadith_arabic"):
        suffix_md = f" *({hadith_ref})*" if hadith_ref else ""
        suffix_plain = f" ({hadith_ref})" if hadith_ref else ""
        return f"> {text}{suffix_md}", f"{text}{suffix_plain}"

    return text, text


def _compute_figures_checksum(figures: List[Dict[str, object]]) -> str:
    parts = [json.dumps(figure, sort_keys=True, ensure_ascii=False) for figure in figures]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def _compute_document_checksum(document: Document) -> str:
    payload = {
        "title": document.title,
        "subtitle": document.subtitle,
        "language": document.language,
        "blocks": [block.to_dict() for block in document.blocks],
    }
    content = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{content}+{BUILDER_VERSION}".encode("utf-8")).hexdigest()[:16]
