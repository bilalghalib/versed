"""Public OpenITI normalization helpers.

These helpers intentionally do not parse raw OpenITI mARkdown syntax directly.
Instead, they adapt the structured block JSON produced by an upstream parser
such as ``@openiti/markdown-parser`` into versed's portable public types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .arabic import is_arabic
from .markdown import EnhancedMarkdownResult, build_markdown_from_document
from .types import BlockType, Document, TextBlock


_HEADING_TYPES = {"title", "header-1", "header-2", "header-3", "header-4", "header-5", "category"}
_PARAGRAPH_TYPES = {"paragraph", "year_of_birth", "year_of_death", "year", "age"}
_QUOTE_TYPES = {"blockquote", "verse"}


@dataclass(frozen=True)
class OpenITIPage:
    """A parsed OpenITI block paired with its effective page metadata."""

    block: Dict[str, Any]
    page: int
    volume: Optional[int] = None


def assign_openiti_pages(parse_result: Any) -> List[OpenITIPage]:
    """Attach the most recent OpenITI page marker to each content block."""
    blocks = _extract_content_blocks(parse_result)

    current_page = 1
    current_volume: Optional[int] = None
    numbered: List[OpenITIPage] = []

    for block in blocks:
        block_type = str(block.get("type") or "").strip()
        if block_type == "pageNumber":
            current_volume, current_page = _coerce_page_number(block.get("content"))
            continue

        numbered.append(OpenITIPage(block=dict(block), page=current_page, volume=current_volume))

    return numbered


def document_from_openiti_blocks(
    parse_result: Any,
    *,
    title: str = "",
    subtitle: str = "",
) -> Document:
    """Build a public Document from parsed OpenITI block JSON."""
    metadata = _extract_metadata(parse_result)
    numbered_blocks = assign_openiti_pages(parse_result)

    resolved_title = title or _coerce_text(metadata.get("title")) or _find_first_title(numbered_blocks)
    resolved_subtitle = subtitle or _coerce_text(metadata.get("subtitle"))

    blocks: List[TextBlock] = []
    page_numbers_seen: List[int] = []

    for item in numbered_blocks:
        normalized = _normalize_openiti_block(item)
        if normalized is None:
            continue
        blocks.extend(normalized)
        if item.page not in page_numbers_seen:
            page_numbers_seen.append(item.page)

    if not blocks and resolved_title:
        blocks.append(TextBlock(type=BlockType.HEADING, text=resolved_title))

    full_text = " ".join(block.text for block in blocks if block.text)
    meta: Dict[str, Any] = {
        "source": "openiti",
        "page_numbers": page_numbers_seen,
        "block_count": len(blocks),
    }
    if metadata:
        meta["openiti_metadata"] = metadata

    return Document(
        title=resolved_title,
        subtitle=resolved_subtitle,
        language="ar" if is_arabic(full_text) else "en",
        blocks=blocks,
        meta=meta,
    )


def build_openiti_markdown(
    parse_result: Any,
    *,
    title: str = "",
    subtitle: str = "",
) -> EnhancedMarkdownResult:
    """Render markdown/plain text from parsed OpenITI block JSON."""
    document = document_from_openiti_blocks(parse_result, title=title, subtitle=subtitle)
    return build_markdown_from_document(document)


def _extract_content_blocks(parse_result: Any) -> List[Dict[str, Any]]:
    if isinstance(parse_result, dict):
        content = parse_result.get("content")
        if content is None and isinstance(parse_result.get("blocks"), list):
            content = parse_result.get("blocks")
        if not isinstance(content, list):
            raise TypeError("OpenITI parse_result must contain a list under 'content' or 'blocks'.")
        return [dict(block) for block in content if isinstance(block, dict)]

    if isinstance(parse_result, Sequence) and not isinstance(parse_result, (str, bytes)):
        return [dict(block) for block in parse_result if isinstance(block, dict)]

    raise TypeError("OpenITI parse_result must be a mapping or sequence of block dictionaries.")


def _extract_metadata(parse_result: Any) -> Dict[str, Any]:
    if isinstance(parse_result, dict) and isinstance(parse_result.get("metadata"), dict):
        return dict(parse_result["metadata"])
    return {}


def _coerce_page_number(content: Any) -> Tuple[Optional[int], int]:
    if not isinstance(content, dict):
        return None, 1

    volume = _coerce_optional_int(content.get("volume"))
    page = _coerce_optional_int(content.get("page")) or 1
    return volume, page


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_coerce_text(item) for item in value if _coerce_text(item)).strip()
    if isinstance(value, dict):
        parts = [_coerce_text(item) for item in value.values()]
        return " ".join(part for part in parts if part).strip()
    return str(value).strip()


def _find_first_title(numbered_blocks: Iterable[OpenITIPage]) -> str:
    for item in numbered_blocks:
        if str(item.block.get("type") or "").strip() == "title":
            return _coerce_text(item.block.get("content"))
    return ""


def _normalize_openiti_block(item: OpenITIPage) -> Optional[List[TextBlock]]:
    block_type = str(item.block.get("type") or "").strip()
    content = item.block.get("content")

    if block_type == "pageNumber":
        return None

    if block_type in _HEADING_TYPES:
        text = _coerce_text(content)
        if not text:
            return None
        return [_make_text_block(BlockType.HEADING, text, item, openiti_type=block_type)]

    if block_type in _PARAGRAPH_TYPES:
        text = _normalize_labeled_paragraph(block_type, content)
        if not text:
            return None
        return [_make_text_block(BlockType.PARAGRAPH, text, item, openiti_type=block_type)]

    if block_type == "verse":
        text = _normalize_verse_content(content)
        if not text:
            return None
        return [_make_text_block(BlockType.VERSE, text, item, openiti_type=block_type)]

    if block_type == "blockquote":
        text = _coerce_text(content)
        if not text:
            return None
        block_kind = BlockType.VERSE if is_arabic(text) else BlockType.PARAGRAPH
        return [_make_text_block(block_kind, text, item, openiti_type=block_type)]

    text = _coerce_text(content)
    if not text:
        return None
    return [_make_text_block(BlockType.PARAGRAPH, text, item, openiti_type=block_type or "paragraph")]


def _normalize_labeled_paragraph(block_type: str, content: Any) -> str:
    text = _coerce_text(content)
    if not text:
        return ""

    labels = {
        "year_of_birth": "Year of birth",
        "year_of_death": "Year of death",
        "year": "Year",
        "age": "Age",
    }
    label = labels.get(block_type)
    if not label:
        return text
    return f"{label}: {text}"


def _normalize_verse_content(content: Any) -> str:
    if isinstance(content, list):
        parts = [_coerce_text(part) for part in content]
        parts = [part for part in parts if part]
        return " // ".join(parts).strip()
    return _coerce_text(content)


def _make_text_block(
    block_type: BlockType,
    text: str,
    item: OpenITIPage,
    *,
    openiti_type: str,
) -> TextBlock:
    meta: Dict[str, Any] = {
        "source": "openiti",
        "openiti_type": openiti_type,
        "page": item.page,
    }
    if item.volume is not None:
        meta["volume"] = item.volume
    return TextBlock(type=block_type, text=text, meta=meta)
