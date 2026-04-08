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


def parse_openiti(text: str, title: str = "", author: str = "") -> ParsedDocument:
    """Parse OpenITI mARkdown via @openiti/markdown-parser."""

    header_text = ""
    body_text = text
    if META_END in text:
        header_text, body_text = text.split(META_END, 1)

    payload = _run_external_openiti_parser(_normalize_input_for_openiti_parser(text))
    doc = ParsedDocument(title=title, author=author, meta=_extract_metadata(header_text))
    external_blocks = _flatten_external_blocks(payload)

    parser_meta = payload.get("metadata") or {}
    if not doc.title and isinstance(parser_meta, dict):
        doc.title = str(parser_meta.get("title") or "").strip()
    if not doc.author and isinstance(parser_meta, dict):
        doc.author = str(parser_meta.get("author") or "").strip()

    lines = body_text.splitlines()
    para_lines: List[str] = []
    title_lines: List[str] = []
    seen_first_heading = False

    def flush_paragraph() -> None:
        if not para_lines:
            return

        raw = " ".join(para_lines).strip()
        para_lines.clear()
        if not raw:
            return

        for match in PAGE_TAG.finditer(raw):
            doc.blocks.append(_page_block(match))

        cleaned = _strip_inline_markers(raw)
        if not cleaned:
            return

        external_block = _pop_external_block(external_blocks, allowed_types=("paragraph", "verse", "category"))
        if external_block and external_block.get("type") == "category":
            doc.blocks.append(Block(BlockType.MORPHO_TAG, "", meta={"category": str(external_block.get("content") or "").strip()}))
            return

        doc.blocks.append(_block_from_external_context(raw, cleaned, external_block))

    def absorb_title_lines() -> None:
        nonlocal seen_first_heading
        if seen_first_heading:
            return
        seen_first_heading = True
        if not title_lines:
            return
        if not doc.title:
            doc.title = title_lines[0]
        if not doc.author and len(title_lines) > 1:
            doc.author = title_lines[-1]
        if len(title_lines) > 2:
            doc.meta["subtitle"] = " — ".join(title_lines[1:-1])
        title_lines.clear()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue

        if line.startswith("######OpenITI") or line.startswith("#META#"):
            continue

        morpho = MORPHO_PAT.match(line)
        if morpho:
            flush_paragraph()
            _pop_external_block(external_blocks, allowed_types=("category",))
            doc.blocks.append(Block(BlockType.MORPHO_TAG, "", meta={"category": morpho.group(1)}))
            continue

        admin = ADMIN_PAT.match(line)
        if admin:
            flush_paragraph()
            doc.blocks.append(Block(BlockType.ADMIN_DIVISION, admin.group(2).strip(), meta={"admin_type": admin.group(1)}))
            continue

        route = ROUTE_PAT.match(line)
        if route:
            flush_paragraph()
            doc.blocks.append(Block(BlockType.ROUTE, route.group(2).strip(), meta={"route_type": route.group(1)}))
            continue

        stripped = line.lstrip("# ").strip()
        if stripped.startswith("PageV") and len(stripped) < 25:
            page_match = PAGE_TAG.search(stripped)
            if page_match:
                if line.startswith("# "):
                    doc.blocks.append(_page_block(page_match))
                    flush_paragraph()
                else:
                    flush_paragraph()
                    doc.blocks.append(_page_block(page_match))
                after = PAGE_TAG.sub("", stripped).strip()
                if after:
                    para_lines.append(after)
                continue

        if line.startswith("###"):
            flush_paragraph()
            absorb_title_lines()

            if line.startswith("### |EDITOR|"):
                _pop_external_block(external_blocks, allowed_types=("header",))
                editorial_block = _pop_external_block(external_blocks, allowed_types=("paragraph",))
                editorial_text = str((editorial_block or {}).get("content") or line.replace("### |EDITOR|", "", 1)).strip()
                doc.blocks.append(Block(BlockType.EDITORIAL_SECTION, editorial_text))
                continue

            external_block = _pop_external_block(external_blocks, allowed_types=("header", "paragraph"))
            if external_block and external_block.get("type") == "header":
                level = int(external_block.get("level") or 1)
                heading_map = {
                    1: BlockType.HEADING_1,
                    2: BlockType.HEADING_2,
                    3: BlockType.HEADING_3,
                    4: BlockType.HEADING_4,
                    5: BlockType.HEADING_5,
                }
                doc.blocks.append(Block(heading_map.get(level, BlockType.HEADING_5), str(external_block.get("content") or "").strip(), level=level))
                continue

            if external_block:
                content = str(external_block.get("content") or "").strip()
                if content:
                    doc.blocks.append(_block_from_external_context(line, content, external_block))
                continue

        if line.startswith("# "):
            content = line[2:].strip()
            if not content:
                continue

            if not seen_first_heading and not BASMALA_PAT.match(content) and not HAMDALA_PAT.match(content):
                title_lines.append(content)
                continue

            flush_paragraph()

            if HEMI_MARK.search(content):
                verse_block = _pop_external_block(external_blocks, allowed_types=("verse",))
                doc.blocks.append(_block_from_external_context(content, _strip_inline_markers(content), verse_block))
                continue

            para_lines.append(content)
            continue

        if line.startswith("~~"):
            content = line[2:].strip()
            if HEMI_MARK.search(content):
                flush_paragraph()
                verse_block = _pop_external_block(external_blocks, allowed_types=("verse",))
                doc.blocks.append(_block_from_external_context(content, _strip_inline_markers(content), verse_block))
                continue
            para_lines.append(content)
            continue

        if HEMI_MARK.search(line):
            flush_paragraph()
            verse_block = _pop_external_block(external_blocks, allowed_types=("verse",))
            doc.blocks.append(_block_from_external_context(line, _strip_inline_markers(line), verse_block))
            continue

        para_lines.append(line)

    flush_paragraph()

    if title_lines:
        if not doc.title:
            doc.title = title_lines[0]
        if not doc.author and len(title_lines) > 1:
            doc.author = title_lines[-1]
        if len(title_lines) > 2:
            doc.meta["subtitle"] = " — ".join(title_lines[1:-1])

    return doc
