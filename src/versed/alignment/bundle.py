"""Deterministic, checksummed ZIP format for portable alignment results."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import BUNDLE_SCHEMA, AlignmentResult
from .validation import validate_alignment_result

_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_MAX_BUNDLE_BYTES = 2 * 1024 * 1024 * 1024
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_PAYLOAD_NAMES = frozenset(
    {
        "documents/ar.structures.jsonl",
        "documents/en.structures.jsonl",
        "documents/ar.sentences.jsonl",
        "documents/en.sentences.jsonl",
        "alignments/structural.jsonl",
        "alignments/paragraphs.jsonl",
        "alignments/sentences.jsonl",
        "alignments/recommended.jsonl",
        "review/queue.jsonl",
        "review/README.txt",
        "reports/diagnostics.json",
        "reports/accuracy.json",
        "README.txt",
    }
)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _jsonl_bytes(values: Iterable[Any]) -> bytes:
    return b"".join(_json_bytes(value) for value in values)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _payloads(result: AlignmentResult) -> dict[str, bytes]:
    return {
        "documents/ar.structures.jsonl": _jsonl_bytes(asdict(value) for value in result.arabic.structures),
        "documents/en.structures.jsonl": _jsonl_bytes(asdict(value) for value in result.english.structures),
        "documents/ar.sentences.jsonl": _jsonl_bytes(asdict(value) for value in result.arabic_sentences),
        "documents/en.sentences.jsonl": _jsonl_bytes(asdict(value) for value in result.english_sentences),
        "alignments/structural.jsonl": _jsonl_bytes(asdict(value) for value in result.structural_links),
        "alignments/paragraphs.jsonl": _jsonl_bytes(asdict(value) for value in result.paragraph_links),
        "alignments/sentences.jsonl": _jsonl_bytes(asdict(value) for value in result.sentence_links),
        "alignments/recommended.jsonl": _jsonl_bytes(asdict(value) for value in result.recommended_links),
        "review/queue.jsonl": _jsonl_bytes(asdict(value) for value in result.review_items),
        "review/README.txt": (
            b"Rows in queue.jsonl are doubts, not failures.\n"
            b"The stable review id and source ids let later tools or people record a correction.\n"
            b"High priority means region/structural/coarse uncertainty; medium usually means paragraph-level;\n"
            b"low usually means a sentence link with a non-zero display radius.\n"
            b"Corrections are JSONL rows with review_id, action (accept/reject/replace), and note.\n"
            b"A replace row also supplies english_ids and may supply resolution, arabic_ids, and radius.\n"
            b"Re-run versed align with --corrections FILE; stale ids and cross-structure edits fail loud.\n"
        ),
        "reports/diagnostics.json": _json_bytes(result.diagnostics),
        "reports/accuracy.json": _json_bytes(result.metrics),
        "README.txt": (
            b"Versed Arabic-English alignment bundle\n\n"
            b"Source structures, paragraphs, and derived sentences remain separate.\n"
            b"alignments/recommended.jsonl zooms out when finer evidence is weak.\n"
            b"region recommendations are bounded paragraph spans, not exact paragraph claims.\n"
            b"score_confidence is a ranking score, not a calibrated probability.\n"
            b"Coverage is not accuracy; accuracy requires independent gold.\n"
            b"This bundle records correspondence and makes no rights decision.\n"
        ),
    }


def _manifest(result: AlignmentResult, payloads: dict[str, bytes]) -> dict[str, Any]:
    files = {
        name: {"sha256": _sha256(value), "bytes": len(value)}
        for name, value in sorted(payloads.items())
    }
    identity = {
        "schema": BUNDLE_SCHEMA,
        "work_id": result.arabic.work_id,
        "arabic_source_sha256": result.arabic.source_hash,
        "english_source_sha256": result.english.source_hash,
        "payload_sha256": {name: value["sha256"] for name, value in files.items()},
    }
    return {
        **identity,
        "bundle_id": _sha256(_json_bytes(identity)),
        "rights_policy": "not_evaluated_by_aligner",
        "sources": {
            "ar": {"name": result.arabic.source_name, "sha256": result.arabic.source_hash, "metadata": result.arabic.metadata},
            "en": {"name": result.english.source_name, "sha256": result.english.source_hash, "metadata": result.english.metadata},
        },
        "counts": {
            "structural_links": len(result.structural_links),
            "paragraph_links": len(result.paragraph_links),
            "sentence_links": len(result.sentence_links),
            "recommended_links": len(result.recommended_links),
            "review_items": len(result.review_items),
        },
        "accuracy_status": result.metrics.get("status", "unscored"),
        "files": files,
    }


def _write_member(archive: zipfile.ZipFile, name: str, value: bytes) -> None:
    if name.startswith("/") or ".." in Path(name).parts:
        raise ValueError(f"unsafe bundle member name: {name!r}")
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, value)


def write_bundle(result: AlignmentResult, output_path: str | Path, *, force: bool = False) -> dict[str, Any]:
    validate_alignment_result(result)
    output = Path(output_path).expanduser().resolve()
    if output.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing bundle: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    payloads = _payloads(result)
    if sum(len(value) for value in payloads.values()) > _MAX_BUNDLE_BYTES:
        raise ValueError("uncompressed alignment bundle is too large")
    manifest = _manifest(result, payloads)
    payloads["manifest.json"] = _json_bytes(manifest)
    with tempfile.NamedTemporaryFile(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as archive:
            for name, value in sorted(payloads.items()):
                _write_member(archive, name, value)
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return manifest


def verify_bundle(path: str | Path) -> dict[str, Any]:
    bundle = Path(path).expanduser().resolve()
    if not bundle.is_file():
        raise FileNotFoundError(bundle)
    if bundle.stat().st_size > _MAX_BUNDLE_BYTES:
        raise ValueError("alignment bundle is too large")
    with zipfile.ZipFile(bundle, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("bundle contains duplicate member names")
        if "manifest.json" not in names:
            raise ValueError("bundle has no manifest.json")
        if any(name.startswith("/") or ".." in Path(name).parts for name in names):
            raise ValueError("bundle contains an unsafe member name")
        manifest_info = archive.getinfo("manifest.json")
        if manifest_info.file_size > _MAX_MANIFEST_BYTES:
            raise ValueError("bundle manifest is too large")
        infos = [archive.getinfo(name) for name in names]
        if any(info.file_size > _MAX_BUNDLE_BYTES for info in infos):
            raise ValueError("bundle contains an oversized member")
        if sum(info.file_size for info in infos) > _MAX_BUNDLE_BYTES + _MAX_MANIFEST_BYTES:
            raise ValueError("uncompressed alignment bundle is too large")
        manifest = json.loads(archive.read("manifest.json"))
        if not isinstance(manifest, dict) or manifest.get("schema") != BUNDLE_SCHEMA:
            raise ValueError("unsupported or invalid bundle manifest")
        declared = manifest.get("files")
        if not isinstance(declared, dict):
            raise TypeError("manifest files must be a JSON object")
        actual = set(names) - {"manifest.json"}
        if actual != _PAYLOAD_NAMES or set(declared) != actual:
            raise ValueError("bundle members do not match manifest")
        for name, expected in declared.items():
            if not isinstance(expected, dict):
                raise TypeError(f"invalid manifest entry for {name}")
            digest = hashlib.sha256()
            size = 0
            with archive.open(name) as member:
                while chunk := member.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
            if size != int(expected["bytes"]):
                raise ValueError(f"size mismatch for {name}")
            if digest.hexdigest() != expected["sha256"]:
                raise ValueError(f"checksum mismatch for {name}")
        payload_sha256 = {name: value["sha256"] for name, value in sorted(declared.items())}
        identity = {
            "schema": manifest["schema"],
            "work_id": manifest.get("work_id"),
            "arabic_source_sha256": manifest.get("arabic_source_sha256"),
            "english_source_sha256": manifest.get("english_source_sha256"),
            "payload_sha256": payload_sha256,
        }
        if manifest.get("payload_sha256") != payload_sha256:
            raise ValueError("manifest payload identity does not match files")
        if manifest.get("bundle_id") != _sha256(_json_bytes(identity)):
            raise ValueError("bundle identity does not match manifest")
    return manifest
