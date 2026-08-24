"""Serial, resumable manifest runner for portable alignment bundles."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .bundle import verify_bundle, write_bundle
from .embeddings import TransformerEmbedder
from .engine import align_documents
from .sources import (
    load_english_translations,
    load_openiti,
    openiti_alignment_document,
)

_SAFE_ITEM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024


def _manifest_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size > _MAX_MANIFEST_BYTES:
        raise ValueError("alignment manifest must be a file no larger than 16 MiB")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        rows = payload.get("items") if isinstance(payload, dict) else payload
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(rows, list) or not rows:
        raise ValueError("alignment manifest must contain a non-empty item list")
    if not all(isinstance(row, dict) for row in rows):
        raise TypeError("every alignment manifest item must be an object")
    return rows


def _resolve_local(value: str, *, base: Path) -> str:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return str(candidate.resolve())


def _translation_paths(row: dict[str, Any], *, base: Path) -> list[str]:
    values = row.get("translations")
    if values is None:
        values = [row.get("translation")]
    if not isinstance(values, list) or not values or not all(isinstance(value, str) for value in values):
        raise ValueError("manifest item requires translation or a translations list")
    return [_resolve_local(value, base=base) for value in values]


def _openiti_reference(row: dict[str, Any], *, base: Path) -> str:
    value = row.get("openiti")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("manifest item requires an OpenITI reference")
    candidate = Path(value).expanduser()
    relative = base / candidate if not candidate.is_absolute() else candidate
    return str(relative.resolve()) if relative.is_file() else value.strip()


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def align_manifest(
    manifest: str | Path,
    output_dir: str | Path,
    *,
    semantic_model: str | None = None,
    semantic_local_only: bool = False,
    semantic_batch_size: int = 32,
    semantic_sentences: bool = False,
    max_cells: int = 2_000_000,
    sentence_detail_threshold: float = 0.60,
    paragraph_detail_threshold: float = 0.45,
    force: bool = False,
    resume: bool = True,
) -> dict[str, Any]:
    """Align every rights-neutral manifest item and write an incremental report."""
    manifest_path = Path(manifest).expanduser().resolve()
    rows = _manifest_rows(manifest_path)
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    report_path = destination / "batch-report.json"
    embedder = (
        TransformerEmbedder(
            semantic_model,
            local_files_only=semantic_local_only,
            batch_size=semantic_batch_size,
        )
        if semantic_model
        else None
    )
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema": "versed.alignment.batch.v1",
        "manifest": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "semantic_model": semantic_model,
        "semantic_sentences": semantic_sentences,
        "items": results,
    }

    for row in rows:
        item_id = row.get("id")
        if not isinstance(item_id, str) or not _SAFE_ITEM_ID.fullmatch(item_id):
            raise ValueError(f"unsafe or missing alignment item id: {item_id!r}")
        if item_id in seen:
            raise ValueError(f"duplicate alignment item id: {item_id}")
        seen.add(item_id)
        output = destination / f"{item_id}.alignment.zip"
        if resume and output.is_file() and not force:
            try:
                bundle = verify_bundle(output)
                results.append(
                    {
                        "id": item_id,
                        "status": "skipped_verified",
                        "output": str(output),
                        "bundle_id": bundle["bundle_id"],
                        "counts": bundle["counts"],
                    }
                )
                _write_report(report_path, report)
                continue
            except (OSError, TypeError, ValueError):
                pass

        try:
            loaded = load_openiti(
                _openiti_reference(row, base=manifest_path.parent),
                work_id=row.get("work_id"),
            )
            arabic = openiti_alignment_document(loaded)
            english = load_english_translations(
                _translation_paths(row, base=manifest_path.parent),
                work_id=arabic.work_id,
            )
            if embedder is not None:
                embedder.clear_cache()
            result = align_documents(
                arabic,
                english,
                paragraph_embedder=embedder,
                sentence_embedder=embedder if semantic_sentences else None,
                max_cells=max_cells,
                sentence_detail_threshold=sentence_detail_threshold,
                paragraph_detail_threshold=paragraph_detail_threshold,
            )
            bundle = write_bundle(result, output, force=force)
            results.append(
                {
                    "id": item_id,
                    "status": "completed",
                    "output": str(output),
                    "bundle_id": bundle["bundle_id"],
                    "counts": bundle["counts"],
                    "diagnostics": result.diagnostics,
                    "accuracy": result.metrics,
                }
            )
        except (FileNotFoundError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
            results.append(
                {
                    "id": item_id,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
        _write_report(report_path, report)

    report["summary"] = {
        "total": len(results),
        "completed": sum(item["status"] == "completed" for item in results),
        "skipped_verified": sum(item["status"] == "skipped_verified" for item in results),
        "errors": sum(item["status"] == "error" for item in results),
    }
    _write_report(report_path, report)
    return report
