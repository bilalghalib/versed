"""Portable Arabic-English document alignment."""

from .api import align_translation
from .bundle import verify_bundle, write_bundle
from .corrections import apply_review_corrections
from .engine import align_documents
from .judge import AlignmentJudge, JudgeDecision, OllamaJudge, review_with_judge
from .metrics import score_region_gold, score_sentence_gold
from .models import (
    AlignmentDocument,
    AlignmentParagraph,
    AlignmentResult,
    AlignmentSentence,
    AlignmentStructure,
    ParagraphLink,
    RecommendedLink,
    ReviewItem,
    SentenceLink,
    StructuralLink,
)
from .profiles import (
    AlignmentCapabilities,
    ProfileRecommendation,
    detect_alignment_capabilities,
    recommend_alignment_profile,
)
from .validation import validate_alignment_result

__all__ = [
    "AlignmentCapabilities",
    "AlignmentDocument",
    "AlignmentJudge",
    "AlignmentParagraph",
    "AlignmentResult",
    "AlignmentSentence",
    "AlignmentStructure",
    "JudgeDecision",
    "OllamaJudge",
    "ParagraphLink",
    "ProfileRecommendation",
    "RecommendedLink",
    "ReviewItem",
    "SentenceLink",
    "StructuralLink",
    "align_documents",
    "align_translation",
    "apply_review_corrections",
    "detect_alignment_capabilities",
    "recommend_alignment_profile",
    "review_with_judge",
    "score_region_gold",
    "score_sentence_gold",
    "validate_alignment_result",
    "verify_bundle",
    "write_bundle",
]
