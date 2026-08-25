"""Input adapters for OpenITI mARkdown and English TXT/PDF editions."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import urllib.request
from collections import Counter
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
_UNIT_FAMILY = r"chapter|book|part|section|volume|maqama|maqaria|ode"
_PREFIXED_UNIT_HEADING = re.compile(
    rf"^\s*[•·\-*]?\s*(?P<label>[IVXLCDMHU]+|\d+)\s*[.)-]?\s*"
    rf"(?:the\s+)?(?P<family>{_UNIT_FAMILY})\b",
    re.IGNORECASE,
)
_SUFFIXED_UNIT_HEADING = re.compile(
    rf"^\s*(?:the\s+)?(?P<family>{_UNIT_FAMILY})\s+"
    rf"(?P<label>[IVXLCDMHU]+|\d+)\b",
    re.IGNORECASE,
)
_MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(?P<title>\S.*)$")
_PAGE_NUMBER = re.compile(r"^\s*[ivxlcdm]*\s*\d+\s*$", re.IGNORECASE)
_BACK_MATTER = re.compile(
    r"^\s*(?:index|glossary|bibliography|works\s+cited)\s*$",
    re.IGNORECASE,
)
_RUNNING_HEADER = re.compile(r"^[A-Z0-9'’*?.\- ]{4,70}\s+\d{1,4}$")
_SCHOLARLY_NOTE = re.compile(
    r"\b(?:ibid|freytag|arab\s+proverbs|literally|proper\s+name|"
    r"reference\s+to|for\s+a\s+list|the\s+metr(?:e|er)|qur.?an|"
    r"a\.h\.|a\.d\.|ob\.|vol\.|p\.\s*\d|pp\.\s*\d|see\s+[A-Z]|"
    r"another\s+reading|arabici[sz]ed|sanskrit|dictionary|lexicon|"
    r"manuscript|commentator|a\s+figure\s+for|"
    r"there\s+is\s+a\s+tradition|was\s+founded|died\s+(?:about|in)|"
    r"the\s+name\s+(?:of|applied)|the\s+person\s+referred|"
    r"the\s+(?:thief|swindler|sharper|robber)\b|"
    r"this\s+is\s+a\s+species|the\s+plan\s+is|the\s+practice\s+of|"
    r"would\s+make\s+better\s+sense|him\s+who.{0,80}[:;]|"
    r"allusion\s+to|means\s+the|signifies\s+the)\b",
    re.IGNORECASE,
)
_NUMBERED_NOTE = re.compile(r"^\s*\d{1,3}\s+\S.{0,100}?\s[:;]", re.DOTALL)
_FOOTNOTE_PREFIX = re.compile(r"^\s*\([a-z0-9]{1,3}\)\s+", re.IGNORECASE)
_OCR_JUNK = re.compile(r"^[\W_]*[A-Za-z]?[\W_]*$")
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


def _arabic_heading_family(heading: str) -> str:
    normalized = " ".join(heading.split())
    families = (
        ("maqama", "المقامة"),
        ("chapter", "الباب"),
        ("book", "الكتاب"),
        ("section", "الفصل"),
        ("part", "القسم"),
        ("volume", "الجزء"),
        ("ode", "القصيدة"),
    )
    return next((family for family, marker in families if marker in normalized), "")


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
                metadata={"heading_family": _arabic_heading_family(heading)},
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
    for source_sequence, block in enumerate(parsed.blocks):
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
        pending.append(
            (
                text,
                flags,
                {
                    "openiti_block_type": block.type.value,
                    **block.meta,
                    # Consumers key a block by its index into parse_openiti's
                    # block list, so this stays authoritative over block.meta.
                    "openiti_source_sequence": source_sequence,
                },
            )
        )
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


def _heading_signature(text: str) -> tuple[str, str] | None:
    """Return an explicit structural family and printed label.

    Capitalization is intentionally not evidence. OCR running heads are often
    uppercase and vastly outnumber real chapters. A plain-text structural unit
    must instead expose a unit word plus an ordinal, in either common order.
    Markdown headings are explicit by syntax and use their normalized title as
    the family-local label.
    """
    markdown = _MARKDOWN_HEADING.match(text)
    if markdown:
        return "markdown", " ".join(markdown.group("title").split())
    if len(text) > 180:
        return None
    match = _PREFIXED_UNIT_HEADING.match(text) or _SUFFIXED_UNIT_HEADING.match(text)
    if not match:
        return None
    family = match.group("family").casefold()
    if family == "maqaria":
        family = "maqama"
    return family, match.group("label").upper()


def _dehyphenate(lines: list[str]) -> str:
    output: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if output and output[-1].endswith("-") and line[:1].islower():
            output[-1] = output[-1][:-1] + line
        else:
            output.append(line)
    return " ".join(output)


def _repeated_running_headers(lines: list[str]) -> set[str]:
    candidates = [
        " ".join(line.split()).casefold()
        for line in lines
        if 8 <= len(line.strip()) <= 80
        and 2 <= len(line.split()) <= 8
        and any(character.isalpha() for character in line)
        and line.upper() == line
        and _heading_signature(line) is None
    ]
    return {value for value, count in Counter(candidates).items() if count >= 3}


def _plain_tokens(text: str) -> list[tuple[str, str, tuple[str, str] | None]]:
    """Split text into paragraphs and explicit heading lines without loss."""
    lines = text.lstrip("\ufeff").splitlines()
    repeated_headers = _repeated_running_headers(lines)
    tokens: list[tuple[str, str, tuple[str, str] | None]] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        value = _dehyphenate(paragraph_lines)
        if value:
            tokens.append(("paragraph", value, None))
        paragraph_lines = []

    for raw in lines:
        normalized = " ".join(raw.split())
        if not normalized:
            flush_paragraph()
            continue
        signature = _heading_signature(normalized)
        if signature is not None:
            flush_paragraph()
            heading = _MARKDOWN_HEADING.sub(lambda match: match.group("title"), normalized)
            tokens.append(("heading", heading, signature))
            continue
        if (
            normalized.casefold() in repeated_headers
            or _PAGE_NUMBER.fullmatch(normalized)
            or _RUNNING_HEADER.fullmatch(normalized)
        ):
            flush_paragraph()
            continue
        paragraph_lines.append(raw)
    flush_paragraph()
    return tokens


def _plain_text_document(text: str, *, source_name: str, work_id: str) -> AlignmentDocument:
    tokens = _plain_tokens(text)
    if not tokens:
        raise ValueError("English source contains no text")
    structures: list[AlignmentStructure] = []
    heading = ""
    heading_family = ""
    heading_label = ""
    pending: list[tuple[str, tuple[str, ...], dict[str, Any]]] = []
    paragraph_values = [value for kind, value, _signature in tokens if kind == "paragraph"]
    start_markers = [index for index, value in enumerate(paragraph_values) if _GUTENBERG_START.search(value)]
    end_markers = [index for index, value in enumerate(paragraph_values) if _GUTENBERG_END.search(value)]
    gutenberg_start = start_markers[0] if start_markers else None
    gutenberg_end = end_markers[-1] if end_markers else None
    excluded_count = 0
    paragraph_index = -1
    seen_body_heading = False
    in_back_matter = False
    previous_was_note = False

    # Gutenberg's license footer has its own recurring "Section 1...5"
    # spine. It must not make the actual book body look like front matter.
    # Heading positions are measured against the preceding paragraph because
    # headings themselves do not consume a paragraph index.
    family_counts: Counter[str] = Counter()
    family_paragraph_index = -1
    for kind, _value, signature in tokens:
        if kind == "paragraph":
            family_paragraph_index += 1
            continue
        inside_gutenberg_body = (
            (gutenberg_start is None or family_paragraph_index >= gutenberg_start)
            and (gutenberg_end is None or family_paragraph_index < gutenberg_end)
        )
        if signature is not None and inside_gutenberg_body:
            family_counts[signature[0]] += 1
    dominant_family = ""
    if family_counts:
        candidate, count = family_counts.most_common(1)[0]
        if count >= 2:
            dominant_family = candidate

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
        structures.append(
            AlignmentStructure(
                structure_id,
                len(structures),
                heading,
                paragraphs,
                heading,
                {
                    "heading_family": heading_family,
                    "heading_label": heading_label,
                    "paratext": not bool(heading_family),
                },
            )
        )
        pending = []

    for kind, block, signature in tokens:
        if kind == "heading":
            family, label = signature or ("", "")
            if dominant_family and family != dominant_family:
                flags: tuple[str, ...] = ()
                metadata: dict[str, Any] = {
                    "inline_heading": True,
                    "heading_family": family,
                }
                if not seen_body_heading:
                    flags = ("exclude_from_alignment", "front_matter")
                    metadata["paratext"] = "front_matter"
                    excluded_count += 1
                pending.append((block, flags, metadata))
                continue
            flush()
            heading = block
            heading_family = family
            heading_label = label
            seen_body_heading = True
            previous_was_note = False
            continue

        paragraph_index += 1
        flags = ()
        metadata = {}
        outside_gutenberg_body = (
            (gutenberg_start is not None and paragraph_index <= gutenberg_start)
            or (gutenberg_end is not None and paragraph_index >= gutenberg_end)
        )
        if _BACK_MATTER.fullmatch(block):
            in_back_matter = True
        if outside_gutenberg_body:
            flags = ("exclude_from_alignment", "gutenberg_boilerplate")
            metadata = {"paratext": "gutenberg_boilerplate"}
        elif _FOOTNOTE_BLOCK.match(block):
            flags = ("exclude_from_alignment", "footnote")
            metadata = {"paratext": "footnote"}
        elif dominant_family and not seen_body_heading:
            flags = ("exclude_from_alignment", "front_matter")
            metadata = {"paratext": "front_matter"}
        elif in_back_matter:
            flags = ("exclude_from_alignment", "back_matter")
            metadata = {"paratext": "back_matter"}
        else:
            word_count = len(block.split())
            looks_like_note = (
                bool(_NUMBERED_NOTE.match(block))
                or bool(_FOOTNOTE_PREFIX.match(block))
                or (bool(_SCHOLARLY_NOTE.search(block)) and word_count <= 180)
                or (previous_was_note and word_count <= 12)
            )
            looks_like_junk = word_count <= 4 and (
                bool(_OCR_JUNK.fullmatch(block))
                or sum(character.isalnum() for character in block) <= 3
            )
            if looks_like_note or looks_like_junk:
                paratext = "possible_footnote" if looks_like_note else "ocr_junk"
                flags = ("exclude_from_alignment", paratext)
                metadata = {"paratext": paratext}
            previous_was_note = looks_like_note
        if flags:
            excluded_count += 1
        pending.append((block, flags, metadata))
    flush()
    if not structures:
        raise ValueError("English source contains no alignable text")
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
            "dominant_heading_family": dominant_family,
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


def load_english_translations(
    paths: list[str | Path] | tuple[str | Path, ...],
    *,
    work_id: str,
    allow_ocr: bool = False,
    allow_partial_pdf: bool = False,
) -> AlignmentDocument:
    """Load one translation edition split across one or more source files.

    Multi-file editions are currently limited to text/Markdown witnesses. PDF
    volumes retain page-level extraction provenance and should first be
    normalized individually rather than silently flattened together.
    """
    if not paths:
        raise ValueError("translation edition must contain at least one source file")
    if len(paths) == 1:
        return load_english_translation(
            paths[0],
            work_id=work_id,
            allow_ocr=allow_ocr,
            allow_partial_pdf=allow_partial_pdf,
        )

    resolved = [Path(path).expanduser().resolve() for path in paths]
    if any(path.suffix.lower() not in _TEXT_SUFFIXES for path in resolved):
        raise ValueError("multi-file translation editions currently require text or Markdown")
    total_bytes = sum(path.stat().st_size for path in resolved if path.is_file())
    if total_bytes > _MAX_TEXT_BYTES:
        raise ValueError(f"combined translation exceeds {_MAX_TEXT_BYTES} bytes")
    texts = [_read_limited_file(path) for path in resolved]
    result = _plain_text_document(
        "\n\n".join(texts),
        source_name=" + ".join(path.name for path in resolved),
        work_id=work_id,
    )
    metadata = {
        **result.metadata,
        "adapter": "plain_text_multi_file",
        "source_files": [
            {"name": path.name, "sha256": _sha256_file(path)}
            for path in resolved
        ],
    }
    return AlignmentDocument(
        work_id=result.work_id,
        language=result.language,
        source_name=result.source_name,
        source_hash=result.source_hash,
        structures=result.structures,
        metadata=metadata,
    )
