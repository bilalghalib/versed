"""Versioned, rights-neutral contracts for Arabic-English alignment.

The alignment package records correspondence and uncertainty. It deliberately
does not decide whether either source may be published or redistributed.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

DOCUMENT_SCHEMA = "versed.alignment.document.v1"
BUNDLE_SCHEMA = "versed.alignment.bundle.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

Resolution = Literal["sentence", "paragraph", "region", "structure"]
ReviewPriority = Literal["high", "medium", "low"]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AlignmentParagraph:
    id: str
    sequence: int
    text: str
    source_hash: str
    flags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        paragraph_id: str,
        sequence: int,
        text: str,
        flags: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> AlignmentParagraph:
        cleaned = " ".join(text.split()).strip()
        if not paragraph_id.strip():
            raise ValueError("paragraph id must not be blank")
        if sequence < 0:
            raise ValueError("paragraph sequence must be non-negative")
        if not cleaned:
            raise ValueError(f"paragraph {paragraph_id!r} has no text")
        return cls(
            id=paragraph_id,
            sequence=sequence,
            text=cleaned,
            source_hash=sha256_text(cleaned),
            flags=tuple(sorted(set(flags))),
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True)
class AlignmentStructure:
    id: str
    sequence: int
    heading: str
    paragraphs: tuple[AlignmentParagraph, ...]
    anchor_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(paragraph.text for paragraph in self.paragraphs)

    @property
    def word_count(self) -> int:
        return sum(len(paragraph.text.split()) for paragraph in self.paragraphs)


@dataclass(frozen=True)
class AlignmentDocument:
    work_id: str
    language: str
    source_name: str
    source_hash: str
    structures: tuple[AlignmentStructure, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema: str = DOCUMENT_SCHEMA

    def validate(self) -> None:
        if self.schema != DOCUMENT_SCHEMA:
            raise ValueError(f"unsupported alignment document schema: {self.schema!r}")
        if not self.work_id.strip():
            raise ValueError("work_id must not be blank")
        if self.language not in {"ar", "en"}:
            raise ValueError(f"unsupported alignment language: {self.language!r}")
        if not self.source_name.strip():
            raise ValueError("source_name must not be blank")
        if not _SHA256_RE.fullmatch(self.source_hash):
            raise ValueError("source_hash must be a lowercase SHA-256 digest")
        if not self.structures:
            raise ValueError(f"{self.language} document has no structural units")

        structure_ids: set[str] = set()
        paragraph_ids: set[str] = set()
        for expected_structure, structure in enumerate(self.structures):
            if not structure.id.strip() or structure.id in structure_ids:
                raise ValueError(f"blank or duplicate structural unit id: {structure.id!r}")
            if structure.sequence != expected_structure:
                raise ValueError(
                    f"non-contiguous structural sequence at {structure.id}: "
                    f"expected {expected_structure}, got {structure.sequence}"
                )
            if not structure.paragraphs:
                raise ValueError(f"structural unit {structure.id!r} has no paragraphs")
            structure_ids.add(structure.id)
            for expected_paragraph, paragraph in enumerate(structure.paragraphs):
                if paragraph.id in paragraph_ids:
                    raise ValueError(f"duplicate paragraph id: {paragraph.id}")
                if paragraph.sequence != expected_paragraph:
                    raise ValueError(
                        f"non-contiguous paragraph sequence at {paragraph.id}: "
                        f"expected {expected_paragraph}, got {paragraph.sequence}"
                    )
                if paragraph.source_hash != sha256_text(paragraph.text):
                    raise ValueError(f"paragraph source hash mismatch: {paragraph.id!r}")
                paragraph_ids.add(paragraph.id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StructuralLink:
    arabic_structure_ids: tuple[str, ...]
    english_structure_ids: tuple[str, ...]
    method: str
    score_confidence: float
    evidence: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParagraphLink:
    arabic_paragraph_ids: tuple[str, ...]
    english_paragraph_ids: tuple[str, ...]
    operation: str
    score_confidence: float
    uncertainty_radius: int
    structural_link_index: int
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlignmentSentence:
    id: str
    paragraph_id: str
    sequence: int
    global_sequence: int
    text: str
    source_hash: str


@dataclass(frozen=True)
class SentenceLink:
    arabic_sentence_ids: tuple[str, ...]
    english_sentence_ids: tuple[str, ...]
    operation: str
    score_confidence: float
    uncertainty_radius: int
    paragraph_link_index: int
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecommendedLink:
    """The finest correspondence currently justified for one source span."""

    arabic_ids: tuple[str, ...]
    english_ids: tuple[str, ...]
    resolution: Resolution
    score_confidence: float
    uncertainty_radius: int
    reason: str
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewItem:
    """A stable, human-editable record of an alignment doubt."""

    id: str
    recommended_link_index: int
    priority: ReviewPriority
    arabic_ids: tuple[str, ...]
    english_ids: tuple[str, ...]
    resolution: Resolution
    score_confidence: float
    uncertainty_radius: int
    reasons: tuple[str, ...]
    status: str = "needs_review"
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AlignmentResult:
    arabic: AlignmentDocument
    english: AlignmentDocument
    structural_links: tuple[StructuralLink, ...]
    paragraph_links: tuple[ParagraphLink, ...]
    arabic_sentences: tuple[AlignmentSentence, ...]
    english_sentences: tuple[AlignmentSentence, ...]
    sentence_links: tuple[SentenceLink, ...]
    recommended_links: tuple[RecommendedLink, ...]
    review_items: tuple[ReviewItem, ...]
    diagnostics: dict[str, Any]
    metrics: dict[str, Any]
