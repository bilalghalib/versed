"""Portable layout builders for semantic documents."""

from __future__ import annotations

import html as html_lib
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from .arabic import is_arabic
from .types import AlignedWord, BlockType, Document, TextBlock


MARKER_BLOCK_MAP = {
    "SectionHeader": BlockType.HEADING,
    "Text": BlockType.PARAGRAPH,
    "TextInlineMath": BlockType.PARAGRAPH,
    "ListItem": BlockType.PARAGRAPH,
    "Footnote": BlockType.FOOTNOTE,
    "Caption": BlockType.PARAGRAPH,
    "Equation": BlockType.VERSE,
    "Code": BlockType.PARAGRAPH,
}


def document_from_structured(
    structured: Optional[Dict[str, Any]],
    *,
    title: str = "",
    subtitle: str = "",
) -> Optional[Document]:
    """Build a public Document from structured extraction output."""
    if not structured:
        return None

    json_data = structured.get("json_data")
    markdown = structured.get("markdown") or ""
    plain_text = structured.get("plain_text") or ""

    if json_data and _looks_like_marker_json(json_data):
        return document_from_marker_json(json_data, title=title, subtitle=subtitle)

    if markdown.strip():
        return document_from_markdown(markdown, title=title, subtitle=subtitle)

    if plain_text.strip():
        blocks = [TextBlock(type=BlockType.PARAGRAPH, text=plain_text.strip())]
        return Document(
            title=title,
            subtitle=subtitle,
            language=_detect_language(plain_text),
            blocks=blocks,
            meta={"source": "plain_text"},
        )

    return None


def document_from_marker_json(
    json_data: Any,
    *,
    title: str = "",
    subtitle: str = "",
) -> Document:
    """Build a public Document from Marker-style JSON."""
    blocks: List[TextBlock] = []
    for node in _iter_marker_nodes(json_data):
        block_type = node.get("block_type")
        if block_type not in MARKER_BLOCK_MAP:
            continue
        if node.get("children"):
            continue

        text = node.get("text") or _html_to_text(node.get("html", ""))
        text = _clean_text(text)
        if not text:
            continue
        blocks.append(TextBlock(type=MARKER_BLOCK_MAP[block_type], text=text))

    if not blocks:
        fallback_text = _fallback_text_from_marker(json_data)
        if fallback_text:
            blocks.append(TextBlock(type=BlockType.PARAGRAPH, text=fallback_text))

    full_text = " ".join(block.text for block in blocks)
    return Document(
        title=title,
        subtitle=subtitle,
        language=_detect_language(full_text),
        blocks=blocks,
        meta={"source": "marker_json"},
    )


def document_from_markdown(
    markdown: str,
    *,
    title: str = "",
    subtitle: str = "",
) -> Document:
    """Build a public Document from raw markdown."""
    blocks: List[TextBlock] = []
    buffer: List[str] = []
    in_code_block = False

    def flush_paragraph() -> None:
        nonlocal buffer
        if not buffer:
            return
        paragraph = _strip_markdown_inline(" ".join(buffer))
        paragraph = _clean_text(paragraph)
        if paragraph:
            blocks.append(TextBlock(type=BlockType.PARAGRAPH, text=paragraph))
        buffer = []

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if not line.strip():
            flush_paragraph()
            continue
        if line.lstrip().startswith("#"):
            flush_paragraph()
            heading = re.sub(r"^#+\s*", "", line).strip()
            heading = _clean_text(_strip_markdown_inline(heading))
            if heading:
                blocks.append(TextBlock(type=BlockType.HEADING, text=heading))
            continue
        if line.lstrip().startswith(">"):
            flush_paragraph()
            quote = _clean_text(_strip_markdown_inline(line.lstrip()[1:].strip()))
            if quote:
                block_type = BlockType.VERSE if is_arabic(quote) else BlockType.PARAGRAPH
                blocks.append(TextBlock(type=block_type, text=quote))
            continue
        buffer.append(line)

    flush_paragraph()

    full_text = " ".join(block.text for block in blocks)
    return Document(
        title=title,
        subtitle=subtitle,
        language=_detect_language(full_text),
        blocks=blocks,
        meta={"source": "markdown"},
    )


def document_from_aligned_words(
    aligned_words: Union[List[AlignedWord], List[Dict[str, Any]]],
    *,
    title: str = "",
    subtitle: str = "",
    paragraph_gap_ratio: float = 1.5,
    figures: Optional[List[Dict[str, Any]]] = None,
) -> Document:
    """Build a public Document from aligned words and optional figure metadata."""
    if not aligned_words and not figures:
        return Document(
            title=title,
            subtitle=subtitle,
            language="en",
            blocks=[],
            meta={"source": "aligned_words", "word_count": 0},
        )

    words = [
        _dict_to_aligned_word(word) if isinstance(word, dict) else word
        for word in aligned_words
    ]

    sorted_words = _sort_words_by_reading_order(words)
    word_groups = _group_words_into_blocks(sorted_words, paragraph_gap_ratio)

    blocks_with_y: List[Tuple[int, float, TextBlock]] = []
    for word_group in word_groups:
        if not word_group:
            continue

        block_text = _assemble_block_text(word_group)
        if not block_text.strip():
            continue

        ys = [word.y for word in word_group if word.y is not None]
        avg_y = (sum(ys) / len(ys)) if ys else 0.0
        page_number = _group_page_identity(word_group) or 0
        block_type = _infer_block_type(word_group)
        meta = _extract_block_metadata(word_group)
        blocks_with_y.append((page_number, avg_y, TextBlock(type=block_type, text=block_text, meta=meta)))

    if figures:
        for figure in figures:
            bbox = figure.get("bbox", [0, 0, 0, 0])
            figure_y = bbox[1] if len(bbox) > 1 else 0
            figure_page = figure.get("page") or 0
            description = figure.get("description", "")
            if figure.get("caption"):
                description = f"{figure['caption']}. {description}".strip(". ")

            blocks_with_y.append(
                (
                    figure_page,
                    figure_y,
                    TextBlock(
                        type=BlockType.FIGURE,
                        text=description,
                        meta={
                            "figure_type": figure.get("type"),
                            "label": figure.get("label"),
                            "caption": figure.get("caption"),
                            "bbox": bbox,
                            "description_ar": figure.get("description_ar"),
                            "image_path": figure.get("image_path"),
                        },
                    ),
                )
            )

    blocks_with_y.sort(key=lambda item: (item[0], item[1]))
    blocks = [block for _, _, block in blocks_with_y]
    full_text = " ".join(block.text for block in blocks)

    return Document(
        title=title,
        subtitle=subtitle,
        language=_detect_language(full_text),
        blocks=blocks,
        meta={
            "source": "aligned_words",
            "word_count": len(aligned_words),
            "block_count": len(blocks),
            "figure_count": len(figures) if figures else 0,
        },
    )


def _iter_marker_nodes(data: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(data, list):
        for item in data:
            yield from _iter_marker_nodes(item)
    elif isinstance(data, dict):
        if "block_type" in data:
            yield data
        for child in data.get("children") or []:
            yield from _iter_marker_nodes(child)


def _looks_like_marker_json(data: Any) -> bool:
    return any(node.get("block_type") for node in _iter_marker_nodes(data))


def _fallback_text_from_marker(data: Any) -> str:
    parts: List[str] = []
    for node in _iter_marker_nodes(data):
        text = node.get("text") or _html_to_text(node.get("html", ""))
        text = _clean_text(text)
        if text:
            parts.append(text)
    return " ".join(parts)


def _html_to_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<content-ref[^>]*>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return _clean_text(text)


def _strip_markdown_inline(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^\)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", text)
    text = re.sub(r"[*_~]+", "", text)
    return text.strip()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _detect_language(text: str) -> str:
    if not text:
        return "en"
    arabic_chars = sum(1 for char in text if is_arabic(char))
    alpha_chars = sum(1 for char in text if char.isalpha())
    return "ar" if (arabic_chars / max(alpha_chars, 1)) > 0.3 else "en"


def _sort_words_by_reading_order(words: List[AlignedWord]) -> List[AlignedWord]:
    return sorted(words, key=lambda word: (word.block_no, word.line_no, word.word_no))


def _group_words_into_blocks(
    words: List[AlignedWord],
    paragraph_gap_ratio: float = 1.5,
) -> List[List[AlignedWord]]:
    if not words:
        return []

    heights = [word.height for word in words if word.height and word.height > 0]
    avg_line_height = (sum(heights) / len(heights)) if heights else 20.0
    gap_threshold = avg_line_height * paragraph_gap_ratio

    groups: List[List[AlignedWord]] = []
    current_group: List[AlignedWord] = [words[0]]

    for index in range(1, len(words)):
        word = words[index]
        previous = words[index - 1]

        if _page_identity(word) != _page_identity(previous):
            groups.append(current_group)
            current_group = [word]
            continue

        if word.role != previous.role:
            groups.append(current_group)
            current_group = [word]
            continue

        if word.role == "quran" and word.verse_key != previous.verse_key and word.verse_key and previous.verse_key:
            groups.append(current_group)
            current_group = [word]
            continue

        if word.role == "hadith" and word.hadith_ref != previous.hadith_ref and word.hadith_ref and previous.hadith_ref:
            groups.append(current_group)
            current_group = [word]
            continue

        if word.section_type != previous.section_type:
            groups.append(current_group)
            current_group = [word]
            continue

        if word.y is not None and previous.y is not None:
            y_gap = abs(word.y - previous.y)
            if y_gap > gap_threshold and word.y > previous.y:
                groups.append(current_group)
                current_group = [word]
                continue

        current_group.append(word)

    if current_group:
        groups.append(current_group)

    return groups


def _page_identity(word: AlignedWord) -> Optional[int]:
    page_number = word.meta.get("page")
    if isinstance(page_number, int):
        return page_number

    # The public extract pipeline encodes page buckets into large block numbers.
    if word.block_no >= 1_000_000:
        return word.block_no // 1_000_000

    return None


def _group_page_identity(words: List[AlignedWord]) -> Optional[int]:
    for word in words:
        page_number = _page_identity(word)
        if page_number is not None:
            return page_number
    return None


def _infer_block_type(words: List[AlignedWord]) -> BlockType:
    if not words:
        return BlockType.PARAGRAPH

    for word in words:
        if word.section_type == "header" or word.role == "heading":
            return BlockType.HEADING

    role_counts: Dict[str, int] = {}
    for word in words:
        role = word.role or "body"
        role_counts[role] = role_counts.get(role, 0) + 1

    quran_count = role_counts.get("quran", 0) + role_counts.get("quran_arabic", 0)
    if quran_count > len(words) * 0.5:
        return BlockType.VERSE

    return BlockType.PARAGRAPH


def _assemble_block_text(words: List[AlignedWord]) -> str:
    text_parts: List[str] = []
    for word in words:
        if word.meta.get("is_word_continuation"):
            continue
        spoken = word.spoken_text or word.text
        text_parts.append(spoken if spoken != word.text else word.text)
    return _clean_text(" ".join(text_parts))


def _extract_block_metadata(words: List[AlignedWord]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}

    verse_keys = {word.verse_key for word in words if word.verse_key}
    if len(verse_keys) == 1:
        meta["verse_key"] = next(iter(verse_keys))

    hadith_refs = {word.hadith_ref for word in words if word.hadith_ref}
    if len(hadith_refs) == 1:
        meta["hadith_ref"] = next(iter(hadith_refs))

    role_counts: Dict[str, int] = {}
    for word in words:
        role = word.role or "body"
        role_counts[role] = role_counts.get(role, 0) + 1
    if role_counts:
        meta["dominant_role"] = max(role_counts, key=role_counts.get)

    return meta


def _dict_to_aligned_word(data: Dict[str, Any]) -> AlignedWord:
    bbox = data.get("bbox", {})
    x = bbox.get("x") if isinstance(bbox, dict) else data.get("x")
    y = bbox.get("y") if isinstance(bbox, dict) else data.get("y")
    width = bbox.get("width") if isinstance(bbox, dict) else data.get("width")
    height = bbox.get("height") if isinstance(bbox, dict) else data.get("height")

    meta = dict(data.get("meta", {}))
    for key in ("is_word_continuation", "word_group_id", "expansion_type", "page"):
        if key in data and key not in meta:
            meta[key] = data[key]

    return AlignedWord(
        text=data.get("text", ""),
        spoken_text=data.get("spoken_text", data.get("text", "")),
        language=data.get("language", "en"),
        role=data.get("role", "body"),
        section_type=data.get("section_type", "body"),
        verse_key=data.get("verse_key"),
        hadith_ref=data.get("hadith_ref"),
        block_no=data.get("block_no", 0) or 0,
        line_no=data.get("line_no", 0) or 0,
        word_no=data.get("word_no", 0) or 0,
        x=x,
        y=y,
        width=width,
        height=height,
        meta=meta,
    )
