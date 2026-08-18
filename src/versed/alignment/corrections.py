"""Apply explicit human decisions to stable review records."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from .models import AlignmentResult, RecommendedLink, ReviewItem
from .validation import validate_alignment_result

_ACTIONS = frozenset({"accept", "reject", "replace"})


def apply_review_corrections(
    result: AlignmentResult,
    rows: Iterable[dict[str, Any]],
) -> AlignmentResult:
    """Apply review-id keyed decisions; stale or structurally invalid edits fail loud."""
    corrections: dict[str, dict[str, Any]] = {}
    for position, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise TypeError(f"correction row {position} must be a JSON object")
        review_id = str(row.get("review_id") or "").strip()
        action = str(row.get("action") or "").strip()
        note = str(row.get("note") or "").strip()
        if not review_id or action not in _ACTIONS or not note:
            raise ValueError(
                f"correction row {position} requires review_id, action accept/reject/replace, and note"
            )
        if review_id in corrections:
            raise ValueError(f"duplicate correction for {review_id!r}")
        corrections[review_id] = row

    known = {value.id for value in result.review_items}
    unknown = sorted(set(corrections) - known)
    if unknown:
        raise ValueError(f"corrections reference stale or unknown review ids: {unknown[:3]}")

    recommendations = list(result.recommended_links)
    review_items: list[ReviewItem] = []
    action_counts: dict[str, int] = {}
    for item in result.review_items:
        row = corrections.get(item.id)
        if row is None:
            review_items.append(item)
            continue
        action = str(row["action"])
        note = str(row["note"]).strip()
        action_counts[action] = action_counts.get(action, 0) + 1
        current = recommendations[item.recommended_link_index]
        evidence = dict(item.evidence)
        evidence["human_correction"] = {"action": action, "note": note}
        if action == "accept":
            review_items.append(replace(item, status="human_accepted", evidence=evidence))
            continue
        if action == "reject":
            review_items.append(replace(item, status="human_rejected", evidence=evidence))
            continue

        resolution = str(row.get("resolution") or current.resolution)
        arabic_ids = tuple(str(value) for value in row.get("arabic_ids") or current.arabic_ids)
        english_ids = tuple(str(value) for value in row.get("english_ids") or ())
        if resolution not in {"sentence", "paragraph", "region", "structure"} or not arabic_ids or not english_ids:
            raise ValueError(
                f"replace correction {item.id!r} requires valid resolution and non-empty ids"
            )
        replacement = RecommendedLink(
            arabic_ids=arabic_ids,
            english_ids=english_ids,
            resolution=resolution,  # type: ignore[arg-type]
            score_confidence=current.score_confidence,
            uncertainty_radius=int(row.get("uncertainty_radius", 0)),
            reason="human_correction",
            flags=tuple(sorted({*current.flags, "human_corrected"})),
        )
        recommendations[item.recommended_link_index] = replacement
        review_items.append(
            replace(
                item,
                status="human_corrected",
                arabic_ids=replacement.arabic_ids,
                english_ids=replacement.english_ids,
                resolution=replacement.resolution,
                uncertainty_radius=replacement.uncertainty_radius,
                reasons=tuple(sorted({*item.reasons, "human_corrected"})),
                evidence=evidence,
            )
        )

    diagnostics = dict(result.diagnostics)
    diagnostics["human_corrections"] = {
        "applied": sum(action_counts.values()),
        "actions": dict(sorted(action_counts.items())),
    }
    corrected = replace(
        result,
        recommended_links=tuple(recommendations),
        review_items=tuple(review_items),
        diagnostics=diagnostics,
    )
    validate_alignment_result(corrected)
    return corrected
