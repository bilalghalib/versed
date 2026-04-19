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


PAGE_TAG = re.compile(r"\bPageV(\d+)P(\d+)\b")
MS_TAG = re.compile(r"\bms\d+\b|\b\d+ms\b")
MILESTONE = re.compile(r"\bMilestone\d+\b")
HEMI_MARK = re.compile(r"[%\u066a]\s*~\s*[%\u066a]")
META_END = "#META#Header#End#"
BASMALA_PAT = re.compile(r"^بسم الله الرحمن الرحيم\s*$")
HAMDALA_PAT = re.compile(r"^الحمد لله رب العالمين")
LACUNA_PAT = re.compile(r"\.{6,}")
MORPHO_PAT = re.compile(r"^#~:(\w+):$")
ARABIC_CHAR = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
QURAN_BRACKET = re.compile(r"[«»﴿﴾]")
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
}

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
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            normalized_lines.append(raw_line)
            continue

        if stripped.startswith(("######OpenITI", "#META#", "### ", "# ", "~~", "PageV", "ms", "Milestone")):
            normalized_lines.append(raw_line)
            continue

        normalized_lines.append(f"# {stripped}")

    return "\n".join(normalized_lines)


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
            return Block(BlockType.VERSE_PAIR, "", hemistich_a=parts[0], hemistich_b=parts[1])
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
            return Block(BlockType.VERSE_PAIR, "", hemistich_a=parts[0], hemistich_b=parts[1])
        return Block(BlockType.VERSE_LINE, content)

    return Block(BlockType.PARAGRAPH, content)


def _classify_content(text: str, ext_block: Optional[Dict[str, Any]] = None) -> Block:
    """Classify a content string into a typed Block using inline markers."""
    cleaned = _strip_inline_markers(text)
    if not cleaned:
        return Block(BlockType.PARAGRAPH, "")
    return _block_from_external_context(text, cleaned, ext_block)


def parse_openiti(text: str, title: str = "", author: str = "") -> ParsedDocument:
    """Parse OpenITI mARkdown via @openiti/markdown-parser.

    Delegates to the canonical ``@openiti/markdown-parser`` npm package
    and converts its structured JSON output into our Block model.
    """

    header_text = ""
    if META_END in text:
        header_text, _ = text.split(META_END, 1)

    payload = _run_external_openiti_parser(_normalize_input_for_openiti_parser(text))
    doc = ParsedDocument(title=title, author=author, meta=_extract_metadata(header_text))

    parser_meta = payload.get("metadata") or {}
    if not doc.title and isinstance(parser_meta, dict):
        doc.title = str(parser_meta.get("title") or "").strip()
    if not doc.author and isinstance(parser_meta, dict):
        doc.author = str(parser_meta.get("author") or "").strip()

    _HEADING_MAP = {
        1: BlockType.HEADING_1,
        2: BlockType.HEADING_2,
        3: BlockType.HEADING_3,
        4: BlockType.HEADING_4,
        5: BlockType.HEADING_5,
    }

    _EXTRA_CONTEXT_MAP = _OPENITI_EXTRA_CONTEXT

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

            if btype == "title":
                doc.blocks.append(Block(BlockType.TITLE, content_str))

            elif btype == "header":
                level = int(ext_block.get("level") or 1)
                doc.blocks.append(Block(
                    _HEADING_MAP.get(level, BlockType.HEADING_5),
                    content_str, level=level,
                ))

            elif btype == "verse":
                if len(content_parts) == 2:
                    doc.blocks.append(Block(
                        BlockType.VERSE_PAIR, "",
                        hemistich_a=content_parts[0],
                        hemistich_b=content_parts[1],
                    ))
                else:
                    doc.blocks.append(Block(BlockType.VERSE_LINE, content_str))

            elif btype == "category":
                doc.blocks.append(Block(
                    BlockType.MORPHO_TAG, "",
                    meta={"category": content_str},
                ))

            elif btype == "blockquote":
                doc.blocks.append(_classify_content(content_str, ext_block))

            elif extra and extra in _EXTRA_CONTEXT_MAP:
                doc.blocks.append(Block(_EXTRA_CONTEXT_MAP[extra], content_str))

            else:
                # Default: paragraph — apply inline classification
                # Skip stray markup artifacts (lone #, empty content)
                cleaned = _strip_inline_markers(content_str)
                if not cleaned or cleaned in ("#", "##", "###"):
                    continue
                doc.blocks.append(_classify_content(content_str, ext_block))

    return doc
