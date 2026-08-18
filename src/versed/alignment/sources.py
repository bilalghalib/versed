"""Input adapters for OpenITI mARkdown and English TXT/PDF editions."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from versed.extract import extract_document
from versed.openiti_parser import BlockType as OpenITIBlockType
from versed.openiti_parser import parse_openiti
from versed.types import BlockType as PublicBlockType
from versed.types import Document as PublicDocument

from .models import (
    AlignmentDocument,
    AlignmentParagraph,
    AlignmentStructure,
    sha256_text,
)

OPENITI_METADATA_URL = (
    "https://raw.githubusercontent.com/OpenITI/kitab-metadata-automation/"
    "master/output/OpenITI_Github_clone_metadata_light.csv"
)
_ALLOWED_HOSTS = frozenset({"raw.githubusercontent.com", "github.com"})
_OPENITI_ID = re.compile(r"^\d{4}[A-Za-z][A-Za-z0-9]+\.[A-Za-z0-9]+(?:\.[A-Za-z0-9_-]+)?$")
_HEADING = re.compile(
    r"^(?:(?:chapter|book|part|section|volume|maqama|ode)\b|"
    r"(?:[IVXLCDM]+|\d+)\s*[.):-])",
    re.IGNORECASE,
)
_TEXT_SUFFIXES = frozenset({".txt", ".text", ".md", ".markdown"})
_GUTENBERG_START = re.compile(r"^\*{3}\s*START OF (?:THE )?PROJECT GUTENBERG", re.IGNORECASE)
_GUTENBERG_END = re.compile(r"^\*{3}\s*END OF (?:THE )?PROJECT GUTENBERG", re.IGNORECASE)
_FOOTNOTE_BLOCK = re.compile(r"^\[\s*footnote\s+\d+\s*:", re.IGNORECASE)
_MAX_TEXT_BYTES = 512 * 1024 * 1024
_MAX_METADATA_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class LoadedText:
    text: str
    source_name: str
    work_id: str
    metadata: dict[str, Any]


def _read_limited_file(path: Path, *, max_bytes: int = _MAX_TEXT_BYTES) -> str:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"source is not a file: {resolved}")
    if resolved.stat().st_size > max_bytes:
        raise ValueError(f"source exceeds {max_bytes} bytes: {resolved}")
    return resolved.read_text(encoding="utf-8-sig")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_openiti_url(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or host not in _ALLOWED_HOSTS
    ):
        raise ValueError("OpenITI URLs must use HTTPS on github.com or raw.githubusercontent.com")

    path = parsed.path
    if host == "github.com":
        parts = [part for part in path.split("/") if part]
        if len(parts) < 5 or parts[0].lower() != "openiti" or parts[2] != "blob":
            raise ValueError("unsupported OpenITI GitHub URL layout")
        path = "/" + "/".join([parts[0], parts[1], *parts[3:]])
        host = "raw.githubusercontent.com"
    elif not path.lower().startswith("/openiti/"):
        raise ValueError("raw GitHub URL is not inside the OpenITI organization")

    return urlunsplit(("https", host, path, "", ""))


def _read_https(url: str, *, max_bytes: int) -> str:
    safe_url = _validated_openiti_url(url)
    request = urllib.request.Request(safe_url, headers={"User-Agent": "versed-pdf/1"})

    class _RejectRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("OpenITI fetch refused an HTTP redirect")

    opener = urllib.request.build_opener(_RejectRedirects())
    with opener.open(request, timeout=45) as response:
        final_url = response.geturl()
        _validated_openiti_url(final_url)
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > max_bytes:
            raise ValueError(f"remote source exceeds {max_bytes} bytes")
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError(f"remote source exceeds {max_bytes} bytes")
    return payload.decode("utf-8-sig")


def _derive_work_id(source_name: str) -> str:
    name = Path(source_name).name
    parts = name.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else Path(name).stem


def _resolve_openiti_id(reference: str) -> tuple[str, dict[str, Any]]:
    metadata_text = _read_https(OPENITI_METADATA_URL, max_bytes=_MAX_METADATA_BYTES)
    rows = list(csv.DictReader(io.StringIO(metadata_text), delimiter="\t"))
    matches = [
        row
        for row in rows
        if (row.get("book") or "").strip() == reference
        or (row.get("version") or "").strip() == reference
        or (row.get("id") or "").strip() == reference
    ]
    if not matches:
        raise LookupError(f"OpenITI reference not found in current metadata: {reference}")
    matches.sort(key=lambda row: ((row.get("status") or "").strip() != "pri", row.get("url") or ""))
    selected = matches[0]
    url = (selected.get("url") or "").strip()
    if not url:
        raise LookupError(f"OpenITI metadata has no source URL for {reference}")
    return _validated_openiti_url(url), {key: value for key, value in selected.items() if value}


def load_openiti(reference: str | Path, *, work_id: str | None = None) -> LoadedText:
    """Load a local mARkdown file, an OpenITI URL, or an OpenITI book/version ID."""
    candidate = Path(reference).expanduser() if not isinstance(reference, Path) else reference.expanduser()
    if candidate.is_file():
        text = _read_limited_file(candidate)
        name = candidate.name
        return LoadedText(text, name, work_id or _derive_work_id(name), {"kind": "local"})

    value = str(reference).strip()
    metadata: dict[str, Any]
    if value.startswith(("https://", "http://")):
        url = _validated_openiti_url(value)
        metadata = {"kind": "url", "url": url}
    elif _OPENITI_ID.fullmatch(value):
        url, row = _resolve_openiti_id(value)
        metadata = {"kind": "openiti_reference", "url": url, "catalog": row}
    else:
        raise FileNotFoundError(
            f"OpenITI input is neither a file, supported URL, nor valid reference: {reference}"
        )
    text = _read_https(url, max_bytes=_MAX_TEXT_BYTES)
    name = Path(urlsplit(url).path).name
    return LoadedText(text, name, work_id or _derive_work_id(value or name), metadata)


def _block_text(block: Any) -> str:
    if block.type == OpenITIBlockType.VERSE_PAIR:
        return " ".join(value for value in (block.hemistich_a, block.hemistich_b) if value).strip()
    return str(block.text or "").strip()


def openiti_alignment_document(source: LoadedText) -> AlignmentDocument:
    parsed = parse_openiti(source.text)
    structures: list[AlignmentStructure] = []
    heading = ""
    pending: list[tuple[str, tuple[str, ...], dict[str, Any]]] = []

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        structure_id = f"ar:u{len(structures):04d}"
        paragraphs = tuple(
            AlignmentParagraph.create(
                paragraph_id=f"{structure_id}:p{index:04d}",
                sequence=index,
                text=text,
                flags=flags,
                metadata=metadata,
            )
            for index, (text, flags, metadata) in enumerate(pending)
        )
        structures.append(
            AlignmentStructure(
                id=structure_id,
                sequence=len(structures),
                heading=heading,
                anchor_key=heading,
                paragraphs=paragraphs,
            )
        )
        pending = []

    heading_types = {
        OpenITIBlockType.TITLE,
        OpenITIBlockType.HEADING_1,
        OpenITIBlockType.HEADING_2,
        OpenITIBlockType.HEADING_3,
        OpenITIBlockType.HEADING_4,
        OpenITIBlockType.HEADING_5,
    }
    for block in parsed.blocks:
        if block.type in heading_types:
            flush()
            heading = _block_text(block)
            continue
        if block.type in {OpenITIBlockType.PAGE_REF, OpenITIBlockType.MILESTONE}:
            continue
        text = _block_text(block)
        if not text:
            continue
        flags: tuple[str, ...] = ()
        if block.type == OpenITIBlockType.APPARATUS_NOTE:
            flags = ("exclude_from_alignment", "apparatus_note")
        pending.append((text, flags, {"openiti_block_type": block.type.value, **block.meta}))
    flush()
    if not structures:
        raise ValueError("OpenITI source contains no alignable text")
    document = AlignmentDocument(
        work_id=source.work_id,
        language="ar",
        source_name=source.source_name,
        source_hash=sha256_text(source.text),
        structures=tuple(structures),
        metadata={"adapter": "openiti_markdown", **source.metadata},
    )
    document.validate()
    return document


def _looks_like_heading(text: str) -> bool:
    words = text.split()
    if not words or len(words) > 16 or len(text) > 140:
        return False
    letters = [character for character in text if character.isalpha()]
    uppercase = sum(character.isupper() for character in letters)
    return bool(_HEADING.search(text)) or (bool(letters) and uppercase / len(letters) >= 0.78)


def _plain_text_document(text: str, *, source_name: str, work_id: str) -> AlignmentDocument:
    raw_blocks = [" ".join(block.split()) for block in re.split(r"\n\s*\n", text) if block.strip()]
    if not raw_blocks:
        raise ValueError("English source contains no text")
    structures: list[AlignmentStructure] = []
    heading = ""
    pending: list[tuple[str, tuple[str, ...], dict[str, Any]]] = []
    start_markers = [index for index, value in enumerate(raw_blocks) if _GUTENBERG_START.search(value)]
    end_markers = [index for index, value in enumerate(raw_blocks) if _GUTENBERG_END.search(value)]
    gutenberg_start = start_markers[0] if start_markers else None
    gutenberg_end = end_markers[-1] if end_markers else None
    excluded_count = 0

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        structure_id = f"en:u{len(structures):04d}"
        paragraphs = tuple(
            AlignmentParagraph.create(
                paragraph_id=f"{structure_id}:p{index:04d}",
                sequence=index,
                text=value,
                flags=flags,
                metadata=metadata,
            )
            for index, (value, flags, metadata) in enumerate(pending)
        )
        structures.append(AlignmentStructure(structure_id, len(structures), heading, paragraphs, heading))
        pending = []

    for block_index, block in enumerate(raw_blocks):
        flags: tuple[str, ...] = ()
        metadata: dict[str, Any] = {}
        outside_gutenberg_body = (
            (gutenberg_start is not None and block_index <= gutenberg_start)
            or (gutenberg_end is not None and block_index >= gutenberg_end)
        )
        if outside_gutenberg_body:
            flags = ("exclude_from_alignment", "gutenberg_boilerplate")
            metadata = {"paratext": "gutenberg_boilerplate"}
        elif _FOOTNOTE_BLOCK.match(block):
            flags = ("exclude_from_alignment", "footnote")
            metadata = {"paratext": "footnote"}
        if flags:
            excluded_count += 1

        if _looks_like_heading(block) and not flags:
            flush()
            heading = block
        else:
            pending.append((block, flags, metadata))
    flush()
    if not structures:
        # Heading detection is evidence, not permission to discard a source.
        structure_id = "en:u0000"
        structures.append(
            AlignmentStructure(
                structure_id,
                0,
                "",
                tuple(
                    AlignmentParagraph.create(
                        paragraph_id=f"{structure_id}:p{index:04d}",
                        sequence=index,
                        text=value,
                    )
                    for index, value in enumerate(raw_blocks)
                ),
            )
        )
    document = AlignmentDocument(
        work_id=work_id,
        language="en",
        source_name=source_name,
        source_hash=sha256_text(text),
        structures=tuple(structures),
        metadata={
            "adapter": "plain_text",
            "excluded_paragraphs": excluded_count,
            "gutenberg_markers_detected": bool(start_markers or end_markers),
        },
    )
    document.validate()
    return document


def _public_document_to_alignment(
    document: PublicDocument,
    *,
    source_name: str,
    source_hash: str,
    work_id: str,
    metadata: dict[str, Any],
) -> AlignmentDocument:
    structures: list[AlignmentStructure] = []
    heading = ""
    pending: list[tuple[str, tuple[str, ...], dict[str, Any]]] = []

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        structure_id = f"en:u{len(structures):04d}"
        paragraphs = tuple(
            AlignmentParagraph.create(
                paragraph_id=f"{structure_id}:p{index:04d}",
                sequence=index,
                text=text,
                flags=flags,
                metadata=block_meta,
            )
            for index, (text, flags, block_meta) in enumerate(pending)
        )
        structures.append(AlignmentStructure(structure_id, len(structures), heading, paragraphs, heading))
        pending = []

    for block in document.blocks:
        text = " ".join(block.text.split()).strip()
        if not text:
            continue
        if block.type == PublicBlockType.HEADING:
            flush()
            heading = text
            continue
        flags: tuple[str, ...] = ()
        if block.type == PublicBlockType.FOOTNOTE:
            flags = ("exclude_from_alignment", "footnote")
        pending.append((text, flags, {"block_type": block.type.value, **block.meta}))
    flush()
    if not structures:
        raise ValueError("English PDF contains no extracted alignable text")
    result = AlignmentDocument(
        work_id=work_id,
        language="en",
        source_name=source_name,
        source_hash=source_hash,
        structures=tuple(structures),
        metadata=metadata,
    )
    result.validate()
    return result


def load_english_translation(
    path: str | Path,
    *,
    work_id: str,
    allow_ocr: bool = False,
    allow_partial_pdf: bool = False,
) -> AlignmentDocument:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"translation is not a file: {source}")
    if source.stat().st_size > _MAX_TEXT_BYTES:
        raise ValueError(f"translation exceeds {_MAX_TEXT_BYTES} bytes")
    suffix = source.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        text = _read_limited_file(source)
        return _plain_text_document(text, source_name=source.name, work_id=work_id)
    if suffix != ".pdf":
        raise ValueError("English translation must be PDF, TXT, Markdown, or plain text")

    extraction = extract_document(str(source), allow_ocr=allow_ocr)
    unsupported = extraction.stats.get("unsupported_pages") or []
    if unsupported and not allow_partial_pdf:
        raise ValueError(
            "translation PDF has pages that were not extracted: "
            + ", ".join(str(value) for value in unsupported)
            + "; use OCR or explicitly allow a partial PDF"
        )
    return _public_document_to_alignment(
        extraction.document,
        source_name=source.name,
        source_hash=_sha256_file(source),
        work_id=work_id,
        metadata={
            "adapter": "pdf",
            "extraction_version": extraction.version,
            "extracted_text_sha256": sha256_text(extraction.plain_text),
            "extraction_stats": extraction.stats,
            "partial": bool(unsupported),
        },
    )
