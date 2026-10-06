"""Raw OpenITI mARkdown parsing via an upstream parser bridge.

This module owns the public OpenITI parser contract for the Python library.
It shells out to ``@openiti/markdown-parser`` and adapts the result into the
block model historically used by the app's OpenITI renderer/ingestor.
"""

from __future__ import annotations

from collections import deque
import json
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum


class BlockType(Enum):
    TITLE = "title"
    HEADING_1 = "chapter"
    HEADING_2 = "section"
    HEADING_3 = "subsection"
    HEADING_4 = "sub_subsection"
    HEADING_5 = "sub_sub_subsection"
    EDITORIAL_SECTION = "editorial_section"
    PARAGRAPH = "paragraph"
    BASMALA = "invocation"
    HAMDALA = "praise"
    VERSE_PAIR = "verse_pair"
    VERSE_LINE = "verse_line"
    QURAN_CITATION = "quran_citation"
    HADITH_UNIT = "hadith_unit"
    ISNAD = "chain_of_narration"
    MATN = "hadith_content"
    HUKM = "hadith_ruling"
    BIO_MAN = "biography_male"
    BIO_WOMAN = "biography_female"
    BIO_REF = "biography_crossref"
    BIO_NAMELIST = "biography_namelist"
    EVENT = "historical_event"
    EVENT_BATCH = "event_batch"
    DIC_NISBA = "dict_descriptive_name"
    DIC_TOPONYM = "dict_toponym"
    DIC_LEXICAL = "dict_lexical"
    DIC_BOOK = "dict_book_title"
    DOX_POSITION = "dox_theological_position"
    DOX_SECT = "dox_religious_sect"
    APPARATUS_NOTE = "apparatus_note"
    MORPHO_TAG = "morphological_passage"
    ADMIN_DIVISION = "administrative_division"
    ROUTE = "route_distance"
    LACUNA = "lacuna"
    PAGE_REF = "page_reference"
    MILESTONE = "milestone"


@dataclass
class NamedEntity:
    tag: str
    index: int
    start: int
    end: int
    full_tag: str


@dataclass
class ReviewTag:
    scholar: str
    category: str
    subcategory: str
    status_truth: str
    status_review: str
    start: int
    end: int
    full_tag: str


@dataclass
class Block:
    type: BlockType
    text: str
    level: int = 1
    meta: Dict[str, Any] = field(default_factory=dict)
    hemistich_a: str = ""
    hemistich_b: str = ""
    entities: List[NamedEntity] = field(default_factory=list)
    review_tags: List[ReviewTag] = field(default_factory=list)
    isnad_text: str = ""
    matn_text: str = ""
    hukm_text: str = ""


@dataclass
class ParsedDocument:
    title: str = ""
    author: str = ""
    blocks: List[Block] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


# Page anchors may be glued together ("PageV01P298PageV01P300"); a letter
# before "Page" means another scheme element (PageWrongV…, StartingPageV…).
# Some sources add a folio side ("PageV01P003b"), absorbed with the anchor.
PAGE_TAG = re.compile(r"(?<![A-Za-z])PageV(\d+)P(\d+)(?:[ab](?![A-Za-z]))?")
MS_TAG = re.compile(r"\bms\d+\b|\b\d+ms\b")
MILESTONE = re.compile(r"\bMilestone\d+\b")
APPARATUS_SEP = re.compile(r"\s+\+\s+")
APPARATUS_START = re.compile(r"^(?:حديث|أثر|تنبيه|قلت|قال المحقق)\b")
INLINE_TITLE_SEP = re.compile(r"\s+\$\s+")
HEMI_MARK = re.compile(r"[%\u066a]\s*~\s*[%\u066a]")
META_END = "#META#Header#End#"
BASMALA_PAT = re.compile(r"^بسم الله الرحمن الرحيم\s*$")
HAMDALA_PAT = re.compile(r"^الحمد لله رب العالمين")
LACUNA_PAT = re.compile(r"\.{6,}")
MORPHO_PAT = re.compile(r"^#~:(\w+):$")
ARABIC_CHAR = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
# Arabic guillemets «…» are ordinary quotation marks throughout OpenITI and
# occur around dialogue, book titles, maxims, and other non-Qur'anic prose.
# Only the dedicated Qur'an ornaments route a block as a citation. A later
# semantic pass can resolve the exact verse span within a mixed paragraph.
QURAN_BRACKET = re.compile(r"[﴿﴾]")
RWY_MARKER = re.compile(r"^\$RWY\$\s*")
MATN_MARKER = re.compile(r"@MATN@")
HUKM_MARKER = re.compile(r"@HUKM@")
ADMIN_PAT = re.compile(r"^#\$#(PROV|REG\d|TYPE|STTL)\s+(.*)")
ROUTE_PAT = re.compile(r"^#\$#(FROM|TOWA|DIST)\s+(.*)")
FULL_TAG = re.compile(r"^###\s*\$([A-Z]{3}_[A-Z]{3})\$\s*(.*)")

_OPENITI_EXTRA_CONTEXT = {
    "man_biography": BlockType.BIO_MAN,
    "woman_biography": BlockType.BIO_WOMAN,
    "cross_reference_biography": BlockType.BIO_REF,
    "names_list": BlockType.BIO_NAMELIST,
    "historical_events": BlockType.EVENT,
    "historical_events_batch": BlockType.EVENT_BATCH,
    "dictionary_nis": BlockType.DIC_NISBA,
    "dictionary_top": BlockType.DIC_TOPONYM,
    "dictionary_lex": BlockType.DIC_LEXICAL,
    "dictionary_bib": BlockType.DIC_BOOK,
    "dox_pos": BlockType.DOX_POSITION,
    "dox_sec": BlockType.DOX_SECT,
    "editorial": BlockType.APPARATUS_NOTE,
}


def _usable_metadata_value(meta: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(meta.get(key) or "").strip()
        if value and value.upper() not in {"NODATA", "NOTGIVEN"}:
            return value
    return ""


_NODE_OPENITI_PARSER = r"""
const { parseMarkdown } = require('@openiti/markdown-parser');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  const result = parseMarkdown(input);
  process.stdout.write(JSON.stringify(result));
});
"""


def _resolve_parser_cwd() -> str:
    env_cwd = os.environ.get("OPENITI_PARSER_CWD")
    if env_cwd:
        return env_cwd

    for candidate in [Path.cwd(), *Path(__file__).resolve().parents]:
        if (candidate / "package.json").exists():
            return str(candidate)

    return str(Path.cwd())


def _normalize_input_for_openiti_parser(text: str) -> str:
    normalized_lines: List[str] = []
    in_body = META_END not in text
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not in_body:
            # Header lines (#META#, #NewRec#, ...) are not body text.
            normalized_lines.append(raw_line)
            in_body = META_END in raw_line
            continue
        # The bridge only sees space-separated page anchors.
        raw_line = re.sub(r"(PageV\d+P\d+)(?=PageV)", r"\1 ", raw_line)
        stripped = raw_line.strip()
        if not stripped:
            normalized_lines.append(raw_line)
            continue

        page_lead = PAGE_TAG.match(stripped)
        if page_lead and stripped[page_lead.end():].strip():
            # "PageV01P023 text": the page ends inside a running paragraph and
            # the text continues it; as its own line the bridge drops the text.
            normalized_lines.append(f"~~{stripped}")
            continue

        if stripped.startswith(("######OpenITI", "#META#", "### ", "# ", "#~:", "~~", "PageV", "ms", "Milestone")):
            normalized_lines.append(raw_line)
            continue

        normalized_lines.append(f"# {stripped}")

    return "\n".join(normalized_lines)


# Patterns from the OpenITI mARkdown scheme (EditPad Pro 8 syntax file,
# https://github.com/OpenITI/mARkdown_scheme). Tags are removed and the words
# they mark are kept; "ignore elements" are removed with their content.
_SCHEME_IGNORED = re.compile(
    r"~!~[^~]+~!!~"
    r"|\bNoteV\d+P\d+N\d+\b"
    r"|\bPage(?:Wrong|Start|Beg|End)V\d+P\d+\b"
    r"|\bStartingPageV\d+P\d+\b"
)
_SCHEME_TAGS = re.compile(
    # Open tagging pattern, e.g. @TOP@TOP@baghdad_1@-@true@
    r"@[A-Z]{3}@[A-Z]{2,}@[A-Za-z_0-9,]+@(?:-?@?(?:true|0+|review|tr|fr)@?)?"
    # Qur'an citation and text-reuse boundaries
    r"|@QURS\d+A\d+_(?:BEG|END)\b"
    r"|@[A-Z]{4}V\d+P\d+[A-Z]_(?:BEG|END)(?:_[A-Z]+)*\b"
    r"|\b(?:[A-Z]{3}_)?[A-Z]{4}V\d+P\d+[A-Z]\b"
    # Named entities (auto-tagged and manual), year tags, REF magic values
    r"|@(?:TOP|SOC|PER|BOK|SOURCE|SRC|[TSBP])\d+\b"
    r"|@Y[ABD]\d+\b"
    r"|\bREF\d{10}\b"
)
_SCHEME_DROPPED_LINE = re.compile(r"^(?:#COMMENT#|#ENTITIES#|#@COMMENT)")
_EDITORIAL_HEADER = re.compile(r"^\|?\s*(EDITOR|SKIP)\|\s*(.*)$")


def _strip_scheme_markup(text: str) -> str:
    """Remove scheme tags and ignorable elements from the body, keep the words."""
    lines: List[str] = []
    in_body = META_END not in text
    for line in text.splitlines():
        if not in_body:
            lines.append(line)
            in_body = META_END in line
            continue
        if _SCHEME_DROPPED_LINE.match(line.strip()):
            continue
        cleaned = _SCHEME_TAGS.sub("", _SCHEME_IGNORED.sub("", line))
        if cleaned != line:
            cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).rstrip()
        lines.append(cleaned)
    return "\n".join(lines)


def _has_words(text: str) -> bool:
    return any(unicodedata.category(char).startswith("L") for char in text)


def _verse_block(first: str, second: str) -> Block:
    """A couplet needs words on both sides of the divider.

    OCR margin noise in some sources carries the divider (``قدهة 1 %~% 11``);
    such a line stays one verse line with every character kept.
    """
    if _has_words(first) and _has_words(second):
        return Block(BlockType.VERSE_PAIR, "", hemistich_a=first, hemistich_b=second)
    return Block(BlockType.VERSE_LINE, " ".join(part for part in (first, second) if part))


_VERSE_TOKEN = re.compile(r"\bVRSDVERSE(\d+)\b")
_VERSE_NUMBER = re.compile(r"^\(?[0-9٠-٩]+\)?$")
_PERCENT_VERSE_LINE = re.compile(r"^#?\s*%")


def _percent_verse_blocks(body: str) -> List[Block]:
    """Parse one ``%``-delimited verse line (with its ``~~`` continuations).

    Shamela-derived OpenITI poetry writes ``% A % B % % 3``: hemistichs
    between ``%`` marks, sometimes a doubled ``%``, and a trailing verse
    number. The upstream parser reads the number as the second hemistich and
    turns the real first hemistich into a paragraph, so these lines are split
    here instead. A purely numeric segment closes the verse(s) before it and
    is kept as ``meta["verse_number"]``; every other segment is a hemistich,
    paired in source order, with an odd one left as a verse line.
    """
    segments = [
        _strip_inline_markers(part).strip()
        for part in body.split("%")
    ]
    segments = [part for part in segments if part and part not in {"~", "|"}]

    blocks: List[Block] = []
    pending: List[str] = []

    def flush() -> None:
        for index in range(0, len(pending) - 1, 2):
            blocks.append(_verse_block(pending[index], pending[index + 1]))
        if len(pending) % 2:
            blocks.append(Block(BlockType.VERSE_LINE, pending[-1]))
        pending.clear()

    for segment in segments:
        if _VERSE_NUMBER.match(segment):
            had_pending = bool(pending)
            flush()
            if had_pending and "verse_number" not in blocks[-1].meta:
                blocks[-1].meta["verse_number"] = segment
            else:
                # A number with no verse of its own is still source text.
                blocks.append(Block(BlockType.PARAGRAPH, segment))
            continue
        if segment.endswith(" |"):
            segment = segment[:-2].rstrip()
        if segment == "$":
            # An inline title separator with no title: markup only.
            continue
        if segment.startswith("$ "):
            # Inline title separator (" $ ") inside a verse line.
            flush()
            blocks.append(Block(BlockType.TITLE, segment[2:].strip(), level=2, meta={"marker": "$"}))
            continue
        pending.append(segment)
    flush()
    return blocks


def _canonical_verse_blocks(body: str) -> List[Block]:
    """Parse one ``%~%`` verse line (scheme "In-text Elements").

    Hemistichs pair in source order; an odd last one is a verse line. The
    upstream parser turns a trailing divider ("4 %~%") into prose "4 ~".
    """
    segments = [_strip_inline_markers(part).strip() for part in HEMI_MARK.split(body)]
    segments = [part for part in segments if part]
    blocks = [
        _verse_block(segments[index], segments[index + 1])
        for index in range(0, len(segments) - 1, 2)
    ]
    if len(segments) % 2:
        blocks.append(Block(BlockType.VERSE_LINE, segments[-1]))
    return blocks


def _extract_percent_verses(text: str) -> Tuple[str, List[List[Block]]]:
    """Replace ``%``-delimited verse lines with placeholders for the bridge.

    Page markers on the line stay on the placeholder line so the upstream
    parser still assigns the verse to the right printed page.
    """
    out: List[str] = []
    verses: List[List[Block]] = []
    lines = text.splitlines()
    index = 0
    in_body = META_END not in text
    while index < len(lines):
        raw_line = lines[index]
        index += 1
        stripped = raw_line.strip()
        if not in_body:
            out.append(raw_line)
            in_body = META_END in raw_line
            continue
        if stripped.startswith("#") and stripped[1:2] not in ("", " ", "%"):
            out.append(raw_line)
            continue
        canonical = bool(HEMI_MARK.search(stripped)) and not (
            RWY_MARKER.search(stripped.lstrip("#").strip())
            or APPARATUS_SEP.search(stripped)
            or INLINE_TITLE_SEP.search(stripped)
        )
        if not canonical and not _PERCENT_VERSE_LINE.match(stripped):
            out.append(raw_line)
            continue
        logical = stripped.lstrip("#").strip()
        while index < len(lines) and lines[index].lstrip().startswith("~~"):
            logical += " " + lines[index].lstrip()[2:].strip()
            index += 1
        pages = PAGE_TAG.findall(logical)
        if canonical:
            blocks = _canonical_verse_blocks(PAGE_TAG.sub(" ", logical))
        else:
            blocks = _percent_verse_blocks(PAGE_TAG.sub(" ", logical))
        if not blocks:
            out.append(raw_line)
            continue
        tags = " ".join(f"PageV{vol}P{page}" for vol, page in pages)
        out.append(f"# VRSDVERSE{len(verses)} {tags}".rstrip())
        verses.append(blocks)
    return "\n".join(out), verses


def _run_external_openiti_parser(text: str) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            ["node", "-e", _NODE_OPENITI_PARSER],
            input=text,
            text=True,
            capture_output=True,
            cwd=_resolve_parser_cwd(),
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Node.js is required to parse OpenITI mARkdown.") from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(
            "OpenITI parser failed. Install @openiti/markdown-parser next to the versed package. "
            f"stderr: {stderr or '(empty)'}"
        )

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenITI parser returned invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("OpenITI parser returned an unexpected payload.")

    return payload


def _flatten_external_blocks(payload: Dict[str, Any]) -> deque[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for section in payload.get("content", []) or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks", []) or []:
            if isinstance(block, dict):
                items.append(block)
    return deque(items)


def _extract_metadata(header_text: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    for line in header_text.splitlines():
        if line.startswith("#META#") and "::" in line:
            key, val = line.split("::", 1)
            meta[key.replace("#META#", "").strip()] = val.strip()
        elif line.startswith("#META#"):
            val = line.replace("#META#", "").strip()
            if val:
                meta.setdefault("notes", []).append(val)
    return meta


def _page_block(match: re.Match[str]) -> Block:
    return Block(
        BlockType.PAGE_REF,
        "",
        meta={"vol": int(match.group(1)), "page": int(match.group(2))},
    )


def _strip_inline_markers(text: str) -> str:
    cleaned = PAGE_TAG.sub("", text)
    cleaned = MS_TAG.sub("", cleaned)
    cleaned = MILESTONE.sub("", cleaned)
    cleaned = re.sub(r"\s+\+\s*$", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _strip_visible_markup(text: str) -> str:
    cleaned = _strip_inline_markers(text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _split_hadith(text: str) -> Tuple[str, str, str]:
    raw = RWY_MARKER.sub("", text).strip()
    isnad = raw
    matn = ""
    hukm = ""

    if MATN_MARKER.search(raw):
        parts = MATN_MARKER.split(raw, 1)
        isnad = parts[0].strip()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if HUKM_MARKER.search(rest):
            verdict_parts = HUKM_MARKER.split(rest, 1)
            matn = verdict_parts[0].strip()
            hukm = verdict_parts[1].strip() if len(verdict_parts) > 1 else ""
        else:
            matn = rest

    return isnad, matn, hukm


def _pop_external_block(
    blocks: deque[Dict[str, Any]],
    *,
    allowed_types: Optional[Tuple[str, ...]] = None,
) -> Optional[Dict[str, Any]]:
    if not blocks:
        return None

    if allowed_types is not None and blocks[0].get("type") not in allowed_types:
        return None

    return blocks.popleft()


def _block_from_external_context(raw_line: str, content: str, external_block: Optional[Dict[str, Any]]) -> Block:
    if RWY_MARKER.search(content):
        isnad, matn, hukm = _split_hadith(content)
        return Block(BlockType.HADITH_UNIT, "", isnad_text=isnad, matn_text=matn, hukm_text=hukm)

    if HEMI_MARK.search(content):
        parts = [part.strip() for part in HEMI_MARK.split(content) if part.strip()]
        if len(parts) == 2:
            return _verse_block(parts[0], parts[1])
        if len(parts) == 1:
            return Block(BlockType.VERSE_LINE, parts[0])
        return Block(BlockType.VERSE_LINE, content)

    if BASMALA_PAT.match(content):
        return Block(BlockType.BASMALA, content)

    if HAMDALA_PAT.match(content):
        return Block(BlockType.HAMDALA, content)

    if LACUNA_PAT.fullmatch(content):
        return Block(BlockType.LACUNA, "")

    if QURAN_BRACKET.search(content):
        return Block(BlockType.QURAN_CITATION, content)

    extra_context = (external_block or {}).get("extraContext")
    block_type = _OPENITI_EXTRA_CONTEXT.get(extra_context)
    if block_type is not None:
        meta: Dict[str, Any] = {}
        full_tag = FULL_TAG.match(raw_line.strip())
        if full_tag:
            meta["full_tag"] = full_tag.group(1)
        return Block(block_type, content, meta=meta)

    if external_block and external_block.get("type") == "verse":
        parts = [str(part).strip() for part in external_block.get("content", []) if str(part).strip()]
        if len(parts) == 2:
            return _verse_block(parts[0], parts[1])
        return Block(BlockType.VERSE_LINE, content)

    return Block(BlockType.PARAGRAPH, content)


def _classify_content(text: str, ext_block: Optional[Dict[str, Any]] = None) -> Block:
    """Classify a content string into a typed Block using inline markers."""
    cleaned = _strip_inline_markers(text)
    if not cleaned:
        return Block(BlockType.PARAGRAPH, "")
    return _block_from_external_context(text, cleaned, ext_block)


def _split_apparatus(text: str, ext_block: Optional[Dict[str, Any]] = None) -> List[Block]:
    """Split OpenITI inline apparatus separated with `` + `` into layout blocks.

    In many OpenITI texts, ``+`` marks a secondary note stream (for example
    takhrij / source notes) inside the same paragraph. Treating it as body text
    causes bad justification and makes source apparatus look like authorial
    prose. The separator is only recognized with surrounding whitespace so
    ordinary plus signs remain visible text.
    """
    parts = [part.strip() for part in APPARATUS_SEP.split(text) if part.strip()]
    if not parts:
        return []

    blocks: List[Block] = []
    for index, part in enumerate(parts):
        cleaned_part = _strip_visible_markup(part)
        if not cleaned_part:
            continue
        if index > 0 and APPARATUS_START.match(cleaned_part):
            blocks.append(Block(
                BlockType.APPARATUS_NOTE,
                cleaned_part,
                meta={"marker": "+"},
            ))
        else:
            blocks.append(_block_from_external_context(text, cleaned_part, ext_block))
    return blocks


def _split_inline_titles_and_apparatus(
    text: str,
    ext_block: Optional[Dict[str, Any]] = None,
) -> List[Block]:
    """Split inline OpenITI title separators before apparatus classification."""
    parts = [part.strip() for part in INLINE_TITLE_SEP.split(text) if part.strip()]
    if not parts:
        return []

    blocks: List[Block] = []
    blocks.extend(_split_apparatus(parts[0], ext_block))
    for part in parts[1:]:
        cleaned_part = _strip_visible_markup(part)
        if cleaned_part:
            blocks.append(Block(
                BlockType.TITLE,
                cleaned_part,
                level=2,
                meta={"marker": "$"},
            ))
    return blocks


def _layout_blocks_from_content(text: str, ext_block: Optional[Dict[str, Any]] = None) -> List[Block]:
    """Convert one parser content payload into ordered layout blocks.

    This is the book-agnostic source cleanup layer: page refs become structural
    marginal markers, milestones are removed from visible prose, and inline
    apparatus is separated from body text before rendering.
    """
    blocks: List[Block] = []
    cursor = 0

    for match in PAGE_TAG.finditer(text):
        before = text[cursor:match.start()].strip()
        if before:
            blocks.extend(_split_inline_titles_and_apparatus(before, ext_block))
        blocks.append(_page_block(match))
        cursor = match.end()

    rest = text[cursor:].strip()
    if rest:
        blocks.extend(_split_inline_titles_and_apparatus(rest, ext_block))

    if not blocks:
        cleaned = _strip_visible_markup(text)
        if cleaned:
            blocks.append(_block_from_external_context(text, cleaned, ext_block))

    return [block for block in blocks if block.text or block.type == BlockType.PAGE_REF]


def parse_openiti(text: str, title: str = "", author: str = "") -> ParsedDocument:
    """Parse OpenITI mARkdown via @openiti/markdown-parser.

    Delegates to the canonical ``@openiti/markdown-parser`` npm package
    and converts its structured JSON output into our Block model.
    """

    header_text = ""
    if META_END in text:
        header_text, _ = text.split(META_END, 1)

    bridge_text, percent_verses = _extract_percent_verses(_strip_scheme_markup(text))
    payload = _run_external_openiti_parser(_normalize_input_for_openiti_parser(bridge_text))
    header_meta = _extract_metadata(header_text)
    doc = ParsedDocument(title=title, author=author, meta=header_meta)

    parser_meta = payload.get("metadata") or {}
    if not doc.title and isinstance(parser_meta, dict):
        doc.title = _usable_metadata_value(parser_meta, "title")
    if not doc.author and isinstance(parser_meta, dict):
        doc.author = _usable_metadata_value(parser_meta, "author")
    if not doc.title:
        doc.title = _usable_metadata_value(header_meta, "020.BookTITLE", "020.BookTITLESUB")
    if not doc.author:
        doc.author = _usable_metadata_value(header_meta, "010.AuthorNAME", "010.AuthorAKA")

    _HEADING_MAP = {
        1: BlockType.HEADING_1,
        2: BlockType.HEADING_2,
        3: BlockType.HEADING_3,
        4: BlockType.HEADING_4,
        5: BlockType.HEADING_5,
    }

    _EXTRA_CONTEXT_MAP = _OPENITI_EXTRA_CONTEXT
    skip_editorial_echo: Optional[str] = None

    for section in payload.get("content", []) or []:
        if not isinstance(section, dict):
            continue

        vol = section.get("volume")
        page = section.get("page")
        if isinstance(vol, int) and isinstance(page, int):
            doc.blocks.append(Block(
                BlockType.PAGE_REF, "",
                meta={"vol": vol, "page": page},
            ))

        for ext_block in section.get("blocks", []) or []:
            if not isinstance(ext_block, dict):
                continue

            btype = ext_block.get("type", "")
            content = ext_block.get("content", "")
            extra = ext_block.get("extraContext")

            # Normalize content to string
            if isinstance(content, list):
                content_parts = [str(c).strip() for c in content if str(c).strip()]
            else:
                content_parts = [str(content).strip()] if str(content).strip() else []

            content_str = " ".join(content_parts)
            if skip_editorial_echo is not None:
                echo, skip_editorial_echo = skip_editorial_echo, None
                if extra == "editorial" and content_str == echo:
                    continue

            if btype == "title":
                doc.blocks.append(Block(BlockType.TITLE, content_str))

            elif btype == "header" and _EDITORIAL_HEADER.match(content_str):
                # "### |EDITOR|" / "### |SKIP|" open an editorial section.
                # The upstream parser also repeats its title as an editorial
                # paragraph; keep a single block.
                editorial_title = _EDITORIAL_HEADER.match(content_str).group(2).strip()
                doc.blocks.append(Block(BlockType.EDITORIAL_SECTION, editorial_title))
                skip_editorial_echo = editorial_title
                continue

            elif btype == "header":
                level = int(ext_block.get("level") or 1)
                doc.blocks.append(Block(
                    _HEADING_MAP.get(level, BlockType.HEADING_5),
                    content_str, level=level,
                ))

            elif btype == "verse":
                if len(content_parts) == 2:
                    doc.blocks.append(_verse_block(content_parts[0], content_parts[1]))
                else:
                    doc.blocks.append(Block(BlockType.VERSE_LINE, content_str))

            elif btype == "category":
                doc.blocks.append(Block(
                    BlockType.MORPHO_TAG, "",
                    meta={"category": content_str},
                ))

            elif btype == "blockquote":
                doc.blocks.extend(_layout_blocks_from_content(content_str, ext_block))

            elif extra and extra in _EXTRA_CONTEXT_MAP:
                # The upstream parser leaves the tag of "### $BIO_REP$" lines.
                cleaned = _strip_visible_markup(re.sub(r"^[A-Z]{3}_[A-Z]{3}\$\s*", "", content_str))
                if cleaned:
                    doc.blocks.append(Block(_EXTRA_CONTEXT_MAP[extra], cleaned))

            else:
                # Default: paragraph — apply inline classification
                # Skip stray markup artifacts (lone #, empty content)
                cleaned = _strip_inline_markers(content_str)
                if _VERSE_TOKEN.search(cleaned):
                    # Verses the bridge merged with neighbouring text are
                    # still substituted; the text around them is kept.
                    for piece in _VERSE_TOKEN.split(content_str):
                        if piece.isdigit() and int(piece) < len(percent_verses):
                            doc.blocks.extend(percent_verses[int(piece)])
                        elif _strip_inline_markers(piece):
                            doc.blocks.extend(_layout_blocks_from_content(piece.strip(), ext_block))
                    continue
                if not cleaned or cleaned in ("#", "##", "###"):
                    continue
                doc.blocks.extend(_layout_blocks_from_content(content_str, ext_block))

    return doc
