"""High-level public API for OpenITI-to-English alignment."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .bundle import write_bundle
from .corrections import apply_review_corrections
from .embeddings import TransformerEmbedder
from .engine import align_documents
from .judge import OllamaJudge, review_with_judge
from .metrics import score_region_gold, score_sentence_gold
from .models import AlignmentResult
from .sources import load_english_translation, load_openiti, openiti_alignment_document


def _load_jsonl(path: str | Path, *, label: str) -> list[dict]:
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size > 32 * 1024 * 1024:
        raise ValueError(f"{label} JSONL must be an existing file no larger than 32 MiB")
    rows: list[dict] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise TypeError(f"{label} row {line_number} must be a JSON object")
        rows.append(row)
    return rows


def align_translation(
    openiti: str | Path,
    translation: str | Path,
    *,
    output: str | Path | None = None,
    work_id: str | None = None,
    allow_ocr: bool = False,
    allow_partial_pdf: bool = False,
    max_cells: int = 2_000_000,
    sentence_detail_threshold: float = 0.60,
    paragraph_detail_threshold: float = 0.45,
    gold: str | Path | None = None,
    force: bool = False,
    semantic_model: str | None = None,
    semantic_local_only: bool = False,
    semantic_batch_size: int = 32,
    semantic_sentences: bool = False,
    ollama_model: str | None = None,
    ollama_url: str = "http://127.0.0.1:11434",
    ollama_max_reviews: int | None = None,
    corrections: str | Path | None = None,
) -> AlignmentResult:
    """Align an OpenITI reference/file with an English TXT or PDF translation.

    The returned result always retains structural and paragraph links. Sentence
    links and recommendations are emitted only where local evidence supports
    them; weak evidence explicitly falls back to paragraph, local region, or
    structure level.
    """
    loaded = load_openiti(openiti, work_id=work_id)
    arabic = openiti_alignment_document(loaded)
    english = load_english_translation(
        translation,
        work_id=arabic.work_id,
        allow_ocr=allow_ocr,
        allow_partial_pdf=allow_partial_pdf,
    )
    embedder = (
        TransformerEmbedder(
            semantic_model,
            local_files_only=semantic_local_only,
            batch_size=semantic_batch_size,
        )
        if semantic_model else None
    )
    result = align_documents(
        arabic,
        english,
        max_cells=max_cells,
        sentence_detail_threshold=sentence_detail_threshold,
        paragraph_detail_threshold=paragraph_detail_threshold,
        paragraph_embedder=embedder,
        sentence_embedder=embedder if semantic_sentences else None,
    )
    if ollama_model:
        judge = OllamaJudge(ollama_model, base_url=ollama_url)
        judge.validate()
        result = review_with_judge(result, judge, max_items=ollama_max_reviews)
    if corrections is not None:
        result = apply_review_corrections(
            result,
            _load_jsonl(corrections, label="correction"),
        )
    if gold is not None:
        gold_rows = _load_jsonl(gold, label="gold")
        scorer = (
            score_sentence_gold
            if gold_rows and gold_rows[0].get("arabic_sentence_ids")
            else score_region_gold
        )
        result = replace(
            result,
            metrics=scorer(result, gold_rows),
        )
    if output is not None:
        write_bundle(result, output, force=force)
    return result
