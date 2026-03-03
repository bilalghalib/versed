"""Deterministic cost-aware routing heuristics for local extraction results."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from .detect import KNOWN_MOJIBAKE_CHARS


EnrichmentAction = Literal["skip", "enrich_text", "enrich_vision"]


@dataclass
class TaskNeeds:
    """Output-quality requirements used by the router."""

    need_semantic_roles: bool = False
    need_visual_descriptions: bool = False
    need_high_fidelity: bool = False


@dataclass
class PageObservations:
    """Measured page-level facts from a local probe."""

    has_text_layer: bool = False
    word_count: int = 0
    text_coverage: float = 0.0
    mojibake_count: int = 0
    mojibake_rate: float = 0.0
    image_count: int = 0
    image_area_ratio: float = 0.0
    table_detected: bool = False
    qcf_detected: bool = False
    arabic_ratio: float = 0.0
    has_pua_glyphs: bool = False
    primary_type: str = "unknown"


@dataclass
class EnrichmentDecision:
    """Concrete routing decision plus explanation."""

    action: EnrichmentAction
    reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0


def observe_page(pdf_path: str, page_number: int) -> PageObservations:
    """Observe a page using PyMuPDF only."""
    try:
        import pymupdf
    except ImportError as exc:
        raise ImportError(
            "observe_page requires pymupdf: pip install 'versed-pdf[pdf]'"
        ) from exc

    observations = PageObservations()
    try:
        document = pymupdf.open(pdf_path)
    except Exception:
        return observations

    page_index = page_number - 1
    if page_index < 0 or page_index >= len(document):
        document.close()
        return observations

    page = document[page_index]
    page_area = page.rect.width * page.rect.height
    if page_area == 0:
        document.close()
        return observations

    words_raw = page.get_text("words")
    observations.word_count = len(words_raw)
    observations.has_text_layer = observations.word_count > 0

    arabic_regex = re.compile(r"[\u0600-\u06FF]")
    arabic_count = 0
    total_chars = 0
    mojibake_count = 0

    for word in words_raw:
        text = word[4] if len(word) > 4 else ""
        total_chars += len(text)
        if arabic_regex.search(text):
            arabic_count += 1
        if any("\uE000" <= char <= "\uF8FF" for char in text):
            observations.has_pua_glyphs = True
        for char in text:
            if char in KNOWN_MOJIBAKE_CHARS:
                mojibake_count += 1

    observations.arabic_ratio = arabic_count / observations.word_count if observations.word_count else 0.0
    observations.mojibake_count = mojibake_count
    observations.mojibake_rate = mojibake_count / max(total_chars, 1)

    blocks = []
    try:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    font = span.get("font", "")
                    if font.startswith("QCF_") or font.startswith("KFGQPC"):
                        observations.qcf_detected = True
                        break
                if observations.qcf_detected:
                    break
            if observations.qcf_detected:
                break
    except Exception:
        blocks = []

    text_area = 0.0
    image_area = 0.0
    for block in blocks:
        bbox = block.get("bbox", (0, 0, 0, 0))
        area = max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
        if block.get("type") == 0:
            text_area += area
        elif block.get("type") == 1:
            image_area += area

    observations.text_coverage = text_area / page_area
    observations.image_area_ratio = image_area / page_area

    try:
        observations.image_count = len(page.get_images())
    except Exception:
        observations.image_count = 0

    try:
        table_finder = page.find_tables()
        observations.table_detected = bool(getattr(table_finder, "tables", []))
    except Exception:
        observations.table_detected = False

    if observations.qcf_detected:
        observations.primary_type = "qcf_quran"
    elif not observations.has_text_layer:
        observations.primary_type = "scanned"
    elif observations.word_count < 10:
        observations.primary_type = "sparse"
    elif observations.arabic_ratio > 0.1:
        observations.primary_type = "text_arabic_english"
    else:
        observations.primary_type = "text_english"

    document.close()
    return observations


def observe_from_extraction(word_bboxes: list, pdf_path: str, page_number: int) -> PageObservations:
    """Build observations from already-extracted words plus PDF-level metadata."""
    observations = observe_page(pdf_path, page_number)
    observations.word_count = len(word_bboxes)
    observations.has_text_layer = observations.word_count > 0

    arabic_regex = re.compile(r"[\u0600-\u06FF]")
    arabic_count = 0
    total_chars = 0
    mojibake_count = 0

    for bbox in word_bboxes:
        text = getattr(bbox, "text", "") or ""
        total_chars += len(text)
        if arabic_regex.search(text):
            arabic_count += 1
        for char in text:
            if char in KNOWN_MOJIBAKE_CHARS:
                mojibake_count += 1

    observations.arabic_ratio = arabic_count / max(observations.word_count, 1)
    observations.mojibake_count = mojibake_count
    observations.mojibake_rate = mojibake_count / max(total_chars, 1)
    return observations


def route_enrichment(obs: PageObservations, task: TaskNeeds | None = None) -> EnrichmentDecision:
    """Route between skip/text/vision based on measured page conditions."""
    task = task or TaskNeeds()
    reasons: list[str] = []

    if not obs.has_text_layer:
        reasons.append(f"no native text layer (word_count={obs.word_count})")
        return EnrichmentDecision("enrich_vision", reasons, 0.95)

    if task.need_visual_descriptions and obs.table_detected:
        reasons.append("table detected and visual descriptions requested")
        return EnrichmentDecision("enrich_vision", reasons, 0.90)

    if task.need_visual_descriptions and obs.image_count > 0:
        reasons.append(f"{obs.image_count} image(s) detected and visual descriptions requested")
        return EnrichmentDecision("enrich_vision", reasons, 0.85)

    if obs.text_coverage < 0.05 and obs.image_area_ratio > 0.5 and obs.word_count < 30:
        reasons.append(
            f"low text coverage ({obs.text_coverage:.1%}) + high image area "
            f"({obs.image_area_ratio:.0%}) + low word_count ({obs.word_count})"
        )
        return EnrichmentDecision("enrich_vision", reasons, 0.80)

    if obs.mojibake_count >= 3 or obs.mojibake_rate > 0.005:
        reasons.append(
            "extraction corruption detected "
            f"(mojibake_count={obs.mojibake_count}, mojibake_rate={obs.mojibake_rate:.2%})"
        )
        return EnrichmentDecision("enrich_text", reasons, 0.80)

    if task.need_semantic_roles and not obs.qcf_detected:
        reasons.append("semantic roles requested and page is not QCF-structured")
        return EnrichmentDecision("enrich_text", reasons, 0.70)

    if task.need_high_fidelity:
        reasons.append("high-fidelity mode requested")
        return EnrichmentDecision("enrich_text", reasons, 0.65)

    reasons.append("local processing sufficient for requested task")
    if obs.qcf_detected:
        reasons.append("QCF/local decoders handle Quran text and honorifics locally")
    if obs.word_count > 50:
        reasons.append(f"clean native extraction available ({obs.word_count} words)")
    return EnrichmentDecision("skip", reasons, 0.85)

