"""Portable public types for the versed PDF-to-Markdown engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BlockType(str, Enum):
    """Semantic block types used by the public markdown builder."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    BASMALA = "basmala"
    VERSE = "verse"
    VERSE_LINE = "verse_line"
    FOOTNOTE = "footnote"
    ISNAD = "isnad"
    MATN = "matn"
    FIGURE = "figure"


@dataclass
class TextBlock:
    """A semantic block of extracted text."""

    type: BlockType
    text: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "text": self.text,
            "meta": dict(self.meta),
        }


@dataclass
class Document:
    """A structured document composed of semantic text blocks."""

    title: str = ""
    subtitle: str = ""
    language: str = "en"
    blocks: List[TextBlock] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "language": self.language,
            "blocks": [block.to_dict() for block in self.blocks],
            "meta": dict(self.meta),
        }


@dataclass
class WordBox:
    """A positioned token on a page."""

    word: str
    page: int
    x: Optional[float] = None
    y: Optional[float] = None
    w: Optional[float] = None
    h: Optional[float] = None
    start: Optional[int] = None
    end: Optional[int] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "page": self.page,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "start": self.start,
            "end": self.end,
            "meta": dict(self.meta),
        }


@dataclass
class AlignedWord:
    """A portable aligned word used by the public layout and markdown builders."""

    text: str
    spoken_text: str
    language: str
    role: str
    section_type: str = "body"
    verse_key: Optional[str] = None
    hadith_ref: Optional[str] = None
    block_no: int = 0
    line_no: int = 0
    word_no: int = 0
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "spoken_text": self.spoken_text,
            "language": self.language,
            "role": self.role,
            "section_type": self.section_type,
            "verse_key": self.verse_key,
            "hadith_ref": self.hadith_ref,
            "block_no": self.block_no,
            "line_no": self.line_no,
            "word_no": self.word_no,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "meta": dict(self.meta),
        }

