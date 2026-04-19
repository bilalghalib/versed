"""OpenITI book rendering via Pango/Cairo.

This module owns the public OpenITI rendering contract for the Python library.
It renders the parsed OpenITI block model into book-style PDFs with theme-aware
typography, running headers, marginal page refs, and poetry layout.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from .openiti_parser import ARABIC_CHAR, BlockType, ParsedDocument


TATWEEL = "\u0640"
NON_CONNECTING = set("اأإآدذرزوؤء")
LAM_CHARS = set("لﻝﻞﻟ")
ALIF_CHARS = set("اأإآﺍﺎﺃﺄﺇﺈﺁﺂ")


def _kashida_positions(word: str) -> list[int]:
    pos = []
    for i, ch in enumerate(word[:-1]):
        nxt = word[i + 1]
        if ch in NON_CONNECTING:
            continue
        if "\u064B" <= nxt <= "\u065F" or nxt == "\u0670":
            continue
        if ch in LAM_CHARS and nxt in ALIF_CHARS:
            continue
        if not ARABIC_CHAR.search(ch + nxt):
            continue
        pos.append(i + 1)
    return pos


def apply_kashida(
    text: str,
    target_w: float,
    measure_fn: Callable[[str], float],
    max_per_line: int = 10,
) -> str:
    cur_w = measure_fn(text)
    gap = target_w - cur_w
    if gap <= 2:
        return text
    tat_w = measure_fn(TATWEEL)
    if tat_w <= 0:
        return text
    need = min(max_per_line, int(math.ceil(gap / tat_w)))
    if need <= 0:
        return text
    words = text.split(" ")
    candidates = []
    for wi, word in enumerate(words):
        if not ARABIC_CHAR.search(word):
            continue
        for p in _kashida_positions(word):
            candidates.append((wi, p))
    if not candidates:
        return text
    inserts = {i: [] for i in range(len(words))}
    for k in range(need):
        wi, p = candidates[k % len(candidates)]
        inserts[wi].append(p)
    new_words = []
    for wi, word in enumerate(words):
        if not inserts[wi]:
            new_words.append(word)
            continue
        ps = sorted(inserts[wi], reverse=True)
        updated = word
        for p in ps:
            if 0 < p <= len(updated):
                updated = updated[:p] + TATWEEL + updated[p:]
        new_words.append(updated)
    return " ".join(new_words)


@dataclass
class BookTheme:
    name: str
    page_w: float = 595.0
    page_h: float = 842.0
    margin_top: float = 80.0
    margin_bottom: float = 72.0
    margin_inner: float = 90.0
    margin_outer: float = 70.0
    font_body: str = "Amiri"
    font_heading: str = "Amiri"
    size_body: int = 12
    size_h1: int = 20
    size_h2: int = 16
    size_h3: int = 13
    size_h4: int = 12
    size_h5: int = 11
    size_basmala: int = 16
    size_verse: int = 13
    size_page_num: int = 9
    size_running_header: int = 8
    size_page_ref: int = 7
    size_bio_marker: int = 10
    line_height: float = 1.4
    color_body: Tuple[float, float, float] = (0.15, 0.12, 0.10)
    color_heading: Tuple[float, float, float] = (0.20, 0.10, 0.05)
    color_basmala: Tuple[float, float, float] = (0.0, 0.38, 0.18)
    color_quran: Tuple[float, float, float] = (0.0, 0.40, 0.20)
    color_hadith: Tuple[float, float, float] = (0.40, 0.08, 0.40)
    color_isnad: Tuple[float, float, float] = (0.35, 0.15, 0.35)
    color_hukm: Tuple[float, float, float] = (0.10, 0.30, 0.50)
    color_verse: Tuple[float, float, float] = (0.30, 0.18, 0.10)
    color_ornament: Tuple[float, float, float] = (0.55, 0.45, 0.35)
    color_page_ref: Tuple[float, float, float] = (0.50, 0.45, 0.40)
    color_running_header: Tuple[float, float, float] = (0.50, 0.45, 0.40)
    color_bio: Tuple[float, float, float] = (0.20, 0.35, 0.20)
    color_event: Tuple[float, float, float] = (0.35, 0.20, 0.10)
    color_dict: Tuple[float, float, float] = (0.10, 0.25, 0.40)
    color_lacuna: Tuple[float, float, float] = (0.60, 0.40, 0.40)
    color_morpho: Tuple[float, float, float] = (0.40, 0.40, 0.40)
    color_admin: Tuple[float, float, float] = (0.25, 0.30, 0.20)
    kashida: bool = True
    kashida_max: int = 10
    running_headers: bool = True
    ornamental_chapters: bool = True
    marginal_page_refs: bool = True
    verse_ornament: str = "✦"


THEMES = {
    "scholarly": BookTheme(
        name="Scholarly Edition",
        size_body=11,
        size_h1=16,
        size_h2=13,
        size_h3=12,
        size_h4=11,
        size_h5=10,
        size_basmala=13,
        size_verse=11,
        line_height=1.35,
        margin_inner=90,
        margin_outer=60,
        margin_top=70,
        margin_bottom=65,
        color_body=(0.10, 0.10, 0.10),
        color_heading=(0.10, 0.08, 0.05),
        color_ornament=(0.40, 0.35, 0.30),
        verse_ornament="*",
        ornamental_chapters=False,
        running_headers=True,
        marginal_page_refs=True,
        kashida=False,
    ),
    "literary": BookTheme(
        name="Literary Edition",
        size_body=13,
        size_h1=22,
        size_h2=16,
        size_h3=14,
        size_h4=13,
        size_h5=12,
        size_basmala=18,
        size_verse=14,
        line_height=1.45,
        margin_inner=85,
        margin_outer=70,
        margin_top=80,
        margin_bottom=80,
        color_body=(0.18, 0.14, 0.10),
        color_heading=(0.25, 0.15, 0.08),
        color_verse=(0.35, 0.22, 0.12),
        color_ornament=(0.60, 0.48, 0.35),
        verse_ornament="❖",
        ornamental_chapters=True,
        kashida=True,
        kashida_max=8,
    ),
    "large_print": BookTheme(
        name="Large Print (Accessibility)",
        size_body=13,
        size_h1=22,
        size_h2=16,
        size_h3=14,
        size_h4=13,
        size_h5=12,
        size_basmala=18,
        size_verse=14,
        line_height=1.45,
        margin_inner=85,
        margin_outer=70,
        margin_top=80,
        margin_bottom=80,
        color_body=(0.18, 0.14, 0.10),
        color_heading=(0.25, 0.15, 0.08),
        color_verse=(0.35, 0.22, 0.12),
        color_ornament=(0.60, 0.48, 0.35),
        verse_ornament="❖",
        ornamental_chapters=True,
        kashida=True,
        kashida_max=8,
    ),
}

W2E = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

ENTRY_MARKERS = {
    BlockType.BIO_MAN: "◆",
    BlockType.BIO_WOMAN: "◇",
    BlockType.BIO_REF: "↗",
    BlockType.BIO_NAMELIST: "☰",
    BlockType.EVENT: "⊕",
    BlockType.EVENT_BATCH: "⊕⊕",
    BlockType.DIC_NISBA: "▸",
    BlockType.DIC_TOPONYM: "▸",
    BlockType.DIC_LEXICAL: "▸",
    BlockType.DIC_BOOK: "▸",
    BlockType.DOX_POSITION: "◎",
    BlockType.DOX_SECT: "◎",
}

ENTRY_COLORS = {
    BlockType.BIO_MAN: "color_bio",
    BlockType.BIO_WOMAN: "color_bio",
    BlockType.BIO_REF: "color_bio",
    BlockType.BIO_NAMELIST: "color_bio",
    BlockType.EVENT: "color_event",
    BlockType.EVENT_BATCH: "color_event",
    BlockType.DIC_NISBA: "color_dict",
    BlockType.DIC_TOPONYM: "color_dict",
    BlockType.DIC_LEXICAL: "color_dict",
    BlockType.DIC_BOOK: "color_dict",
    BlockType.DOX_POSITION: "color_dict",
    BlockType.DOX_SECT: "color_dict",
}


def render_book(
    doc: ParsedDocument,
    out_path: str,
    theme_name: str = "scholarly",
    cover_metadata: Optional[dict] = None,
    cover_style: str = "auto",
    cover_renderer: Optional[Callable[[Any, float, float, dict, str], None]] = None,
) -> Dict[str, Any]:
    """Render an OpenITI parsed document to PDF using Pango/Cairo."""
    import cairo
    import gi

    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    theme = THEMES.get(theme_name, THEMES["scholarly"])
    W, H = theme.page_w, theme.page_h

    surface = cairo.PDFSurface(out_path, W, H)
    cr = cairo.Context(surface)

    page_num = 0
    y = theme.margin_top
    current_chapter = doc.title or ""
    current_section = ""
    all_word_coords: list[dict] = []
    current_block_index = 0

    def ml() -> float:
        return theme.margin_inner if page_num % 2 == 0 else theme.margin_outer

    def mr() -> float:
        return theme.margin_outer if page_num % 2 == 0 else theme.margin_inner

    def tw() -> float:
        return W - ml() - mr()

    def make_layout(font_size: Optional[int] = None, bold: bool = False, width: Optional[float] = None):
        layout = PangoCairo.create_layout(cr)
        font_name = theme.font_body
        size = font_size or theme.size_body
        weight = " Bold" if bold else ""
        layout.set_font_description(Pango.FontDescription.from_string(f"{font_name}{weight} {size}"))
        layout.set_width(int((width or tw()) * Pango.SCALE))
        layout.set_wrap(Pango.WrapMode.WORD)
        layout.set_auto_dir(True)
        return layout

    def measure(text: str, font_size: Optional[int] = None) -> int:
        layout = make_layout(font_size=font_size)
        layout.set_text(text, -1)
        _, ext = layout.get_pixel_extents()
        return ext.width

    def new_page() -> None:
        nonlocal y, page_num
        if page_num > 0:
            num_str = str(page_num).translate(W2E)
            cr.set_source_rgb(*theme.color_ornament)
            num_layout = make_layout(font_size=theme.size_page_num, width=W)
            num_layout.set_alignment(Pango.Alignment.CENTER)
            num_layout.set_text(num_str, -1)
            cr.move_to(0, H - theme.margin_bottom / 2)
            PangoCairo.show_layout(cr, num_layout)
            if theme.running_headers and current_chapter:
                cr.set_source_rgb(*theme.color_running_header)
                header_layout = make_layout(font_size=theme.size_running_header, width=tw())
                header_text = current_section or current_chapter
                if len(header_text) > 60:
                    header_text = header_text[:57] + "..."
                header_layout.set_alignment(Pango.Alignment.CENTER)
                header_layout.set_text(header_text, -1)
                cr.move_to(ml(), theme.margin_top - 30)
                PangoCairo.show_layout(cr, header_layout)
                cr.set_line_width(0.3)
                cr.move_to(ml(), theme.margin_top - 8)
                cr.line_to(ml() + tw(), theme.margin_top - 8)
                cr.stroke()
        cr.show_page()
        page_num += 1
        y = theme.margin_top

    def max_y() -> float:
        return H - theme.margin_bottom - 55

    def check_space(needed: float) -> None:
        if y + needed > max_y():
            new_page()

    def draw_text(
        text: str,
        font_size: Optional[int] = None,
        color: Optional[Tuple[float, float, float]] = None,
        centered: bool = False,
        bold: bool = False,
        justify: bool = True,
        spacing_after: Optional[float] = None,
        use_kashida: bool = False,
        track_words: bool = True,
    ) -> None:
        nonlocal y, current_block_index
        layout = make_layout(font_size=font_size, bold=bold)
        layout.set_alignment(Pango.Alignment.CENTER if centered else Pango.Alignment.RIGHT)
        layout.set_justify(justify and not centered)
        if use_kashida and theme.kashida and not centered:
            text = apply_kashida(text, tw(), lambda t: measure(t, font_size), theme.kashida_max)
        layout.set_text(text, -1)
        layout.set_line_spacing(theme.line_height)
        _, ext = layout.get_pixel_extents()
        spacing = spacing_after if spacing_after is not None else theme.size_body * 0.35
        check_space(ext.height + spacing)
        if y + ext.height > max_y():
            new_page()

        # Extract per-word coordinates before rendering
        if track_words:
            origin_x = ml()
            origin_y = y
            text_bytes = text.encode("utf-8")
            words = text.split()
            byte_offset = 0
            for word_index, word in enumerate(words):
                word_bytes = word.encode("utf-8")
                # Find the byte offset of this word in the full text
                pos_in_bytes = text_bytes.find(word_bytes, byte_offset)
                if pos_in_bytes < 0:
                    continue
                # Get position of first char and end of last char
                rect_start = layout.index_to_pos(pos_in_bytes)
                end_byte = pos_in_bytes + len(word_bytes) - 1
                rect_end = layout.index_to_pos(end_byte)
                # Pango returns values in Pango units (1/1024 pixel)
                py = rect_start.y / Pango.SCALE
                ph = rect_start.height / Pango.SCALE
                # Compute word extent from start and end cursor positions
                # For RTL, start.x > end.x; for LTR, start.x < end.x
                edges = [
                    rect_start.x / Pango.SCALE,
                    (rect_start.x + rect_start.width) / Pango.SCALE,
                    rect_end.x / Pango.SCALE,
                    (rect_end.x + rect_end.width) / Pango.SCALE,
                ]
                px = min(edges)
                pw = max(edges) - px
                all_word_coords.append({
                    "text": word,
                    "x": origin_x + px,
                    "y": origin_y + py,
                    "width": pw,
                    "height": ph,
                    "page": page_num,
                    "block_index": current_block_index,
                    "word_index": word_index,
                })
                byte_offset = pos_in_bytes + len(word_bytes)

        cr.set_source_rgb(*(color or theme.color_body))
        cr.move_to(ml(), y)
        PangoCairo.show_layout(cr, layout)
        y += ext.height + spacing

    def draw_line(width_frac: float = 0.5, thickness: float = 0.5) -> None:
        nonlocal y
        line_width = tw() * width_frac
        x = ml() + (tw() - line_width) / 2
        cr.set_source_rgb(*theme.color_ornament)
        cr.set_line_width(thickness)
        cr.move_to(x, y)
        cr.line_to(x + line_width, y)
        cr.stroke()
        y += 6

    def draw_double_line(width_frac: float = 0.6) -> None:
        nonlocal y
        line_width = tw() * width_frac
        x = ml() + (tw() - line_width) / 2
        cr.set_source_rgb(*theme.color_ornament)
        cr.set_line_width(0.4)
        cr.move_to(x, y)
        cr.line_to(x + line_width, y)
        cr.stroke()
        cr.move_to(x, y + 3)
        cr.line_to(x + line_width, y + 3)
        cr.stroke()
        y += 10

    def draw_verse_pair(a: str, b: str) -> None:
        nonlocal y
        col_w = (tw() - 40) / 2
        left_layout = make_layout(font_size=theme.size_verse, width=col_w)
        left_layout.set_alignment(Pango.Alignment.LEFT)
        left_layout.set_text(a, -1)
        _, left_ext = left_layout.get_pixel_extents()
        right_layout = make_layout(font_size=theme.size_verse, width=col_w)
        right_layout.set_alignment(Pango.Alignment.RIGHT)
        right_layout.set_text(b, -1)
        _, right_ext = right_layout.get_pixel_extents()
        row_h = max(left_ext.height, right_ext.height)
        check_space(row_h + 10)
        cr.set_source_rgb(*theme.color_verse)
        cr.move_to(ml() + col_w + 40, y)
        PangoCairo.show_layout(cr, left_layout)
        cr.set_source_rgb(*theme.color_ornament)
        ornament_layout = make_layout(font_size=theme.size_verse, width=40)
        ornament_layout.set_alignment(Pango.Alignment.CENTER)
        ornament_layout.set_text(theme.verse_ornament, -1)
        cr.move_to(ml() + col_w, y)
        PangoCairo.show_layout(cr, ornament_layout)
        cr.set_source_rgb(*theme.color_verse)
        cr.move_to(ml(), y)
        PangoCairo.show_layout(cr, right_layout)
        y += row_h + 4

    page_num = 0
    if cover_metadata and cover_renderer is not None:
        cover_renderer(cr, W, H, cover_metadata, cover_style)
    elif doc.title:
        y = H * 0.30
        draw_line(0.4, 0.8)
        y += 15
        draw_text(
            doc.title,
            font_size=theme.size_h1 + 6,
            color=theme.color_heading,
            centered=True,
            bold=True,
            spacing_after=15,
        )
        if doc.author:
            draw_text(
                doc.author,
                font_size=theme.size_h2,
                color=theme.color_ornament,
                centered=True,
                spacing_after=20,
            )
        y += 5
        draw_line(0.4, 0.8)
    new_page()

    prev = None
    i = 0
    while i < len(doc.blocks):
        block = doc.blocks[i]

        if block.type == BlockType.PAGE_REF:
            if theme.marginal_page_refs:
                page_ref = block.meta.get("page", 0)
                ref = f"[{str(page_ref).translate(W2E)}]"
                cr.set_source_rgb(*theme.color_page_ref)
                ref_layout = make_layout(font_size=theme.size_page_ref, width=50)
                ref_layout.set_alignment(Pango.Alignment.CENTER)
                ref_layout.set_text(ref, -1)
                x = W - mr() + 8 if page_num % 2 == 0 else ml() - 50
                cr.move_to(x, y - 5)
                PangoCairo.show_layout(cr, ref_layout)
            i += 1
            continue

        if block.type == BlockType.MILESTONE:
            i += 1
            continue

        if block.type == BlockType.HEADING_1:
            if prev and prev != BlockType.PAGE_REF:
                y += theme.size_body * 2
            check_space(80)
            if theme.ornamental_chapters:
                draw_double_line(0.5)
                y += 4
            current_chapter = block.text
            current_section = ""
            draw_text(
                block.text,
                font_size=theme.size_h1,
                color=theme.color_heading,
                centered=True,
                bold=True,
                spacing_after=8,
            )
            if theme.ornamental_chapters:
                draw_double_line(0.5)
                y += 8

        elif block.type == BlockType.HEADING_2:
            if prev and prev not in (BlockType.HEADING_1, BlockType.PAGE_REF):
                y += theme.size_body * 1.5
            check_space(50)
            current_section = block.text
            draw_line(0.3, 0.3)
            y += 6
            draw_text(
                block.text,
                font_size=theme.size_h2,
                color=theme.color_heading,
                centered=True,
                bold=True,
                spacing_after=10,
            )

        elif block.type in (BlockType.HEADING_3, BlockType.HEADING_4, BlockType.HEADING_5):
            size = {
                BlockType.HEADING_3: theme.size_h3,
                BlockType.HEADING_4: theme.size_h4,
                BlockType.HEADING_5: theme.size_h5,
            }.get(block.type, theme.size_h3)
            if prev:
                y += theme.size_body * 1.3
            check_space(40)
            draw_text(block.text, font_size=size, color=theme.color_heading, bold=True, spacing_after=4)

        elif block.type == BlockType.EDITORIAL_SECTION:
            if prev:
                y += theme.size_body
            draw_line(0.2, 0.3)
            label = f"[{block.text}]" if block.text else "[قسم تحريري]"
            draw_text(
                label,
                font_size=theme.size_body - 1,
                color=theme.color_morpho,
                centered=True,
                spacing_after=8,
            )

        elif block.type in ENTRY_MARKERS:
            if prev:
                y += theme.size_body * 0.5
            check_space(40)
            marker = ENTRY_MARKERS[block.type]
            color_key = ENTRY_COLORS.get(block.type, "color_body")
            color = getattr(theme, color_key, theme.color_body)
            draw_text(f"{marker}  {block.text}", font_size=theme.size_body, color=color, bold=True, spacing_after=4)

        elif block.type == BlockType.BASMALA:
            y += 8
            check_space(40)
            draw_text(
                block.text,
                font_size=theme.size_basmala,
                color=theme.color_basmala,
                centered=True,
                spacing_after=8,
            )

        elif block.type == BlockType.HAMDALA:
            draw_text(
                block.text,
                font_size=theme.size_body + 1,
                color=theme.color_body,
                centered=True,
                spacing_after=10,
            )

        elif block.type == BlockType.VERSE_PAIR:
            if prev and prev != BlockType.VERSE_PAIR:
                y += 6
            draw_verse_pair(block.hemistich_a, block.hemistich_b)

        elif block.type == BlockType.VERSE_LINE:
            draw_text(
                block.text,
                font_size=theme.size_verse,
                color=theme.color_verse,
                centered=True,
                spacing_after=4,
            )

        elif block.type == BlockType.QURAN_CITATION:
            if prev != BlockType.QURAN_CITATION:
                y += 4
            draw_text(
                block.text,
                font_size=theme.size_body + 1,
                color=theme.color_quran,
                use_kashida=True,
                spacing_after=10,
            )

        elif block.type == BlockType.HADITH_UNIT:
            if prev:
                y += 4
            if block.isnad_text:
                draw_text(
                    block.isnad_text,
                    font_size=theme.size_body,
                    color=theme.color_isnad,
                    use_kashida=True,
                    spacing_after=4,
                )
            if block.matn_text:
                draw_text(
                    block.matn_text,
                    font_size=theme.size_body,
                    color=theme.color_hadith,
                    use_kashida=True,
                    spacing_after=4,
                )
            if block.hukm_text:
                draw_text(
                    block.hukm_text,
                    font_size=theme.size_body - 1,
                    color=theme.color_hukm,
                    use_kashida=True,
                    spacing_after=8,
                )

        elif block.type == BlockType.ISNAD:
            draw_text(
                block.text,
                font_size=theme.size_body,
                color=theme.color_isnad,
                use_kashida=True,
                spacing_after=8,
            )

        elif block.type == BlockType.MATN:
            draw_text(
                block.text,
                font_size=theme.size_body,
                color=theme.color_hadith,
                use_kashida=True,
                spacing_after=8,
            )

        elif block.type == BlockType.HUKM:
            draw_text(
                block.text,
                font_size=theme.size_body - 1,
                color=theme.color_hukm,
                use_kashida=True,
                spacing_after=8,
            )

        elif block.type == BlockType.MORPHO_TAG:
            cat = block.meta.get("category", "?")
            draw_text(
                f"— {cat} —",
                font_size=theme.size_body - 2,
                color=theme.color_morpho,
                centered=True,
                spacing_after=4,
            )

        elif block.type == BlockType.ADMIN_DIVISION:
            atype = block.meta.get("admin_type", "")
            admin_labels = {"PROV": "الإقليم", "TYPE": "النوع", "STTL": "المدينة"}
            label = admin_labels.get(atype, f"المنطقة {atype[-1]}" if atype.startswith("REG") else atype)
            draw_text(
                f"{label}: {block.text}",
                font_size=theme.size_body - 1,
                color=theme.color_admin,
                spacing_after=2,
            )

        elif block.type == BlockType.ROUTE:
            rtype = block.meta.get("route_type", "")
            route_labels = {"FROM": "من", "TOWA": "إلى", "DIST": "المسافة"}
            label = route_labels.get(rtype, rtype)
            draw_text(
                f"{label}: {block.text}",
                font_size=theme.size_body - 1,
                color=theme.color_admin,
                spacing_after=2,
            )

        elif block.type == BlockType.LACUNA:
            draw_text(
                "[ . . . . . . ]",
                font_size=theme.size_body,
                color=theme.color_lacuna,
                centered=True,
                spacing_after=6,
            )

        elif block.type == BlockType.PARAGRAPH:
            draw_text(block.text, font_size=theme.size_body, color=theme.color_body, use_kashida=True)

        prev = block.type
        i += 1
        if block.type not in (BlockType.PAGE_REF, BlockType.MILESTONE):
            current_block_index += 1

    num = str(page_num).translate(W2E)
    cr.set_source_rgb(*theme.color_ornament)
    num_layout = make_layout(font_size=theme.size_page_num, width=W)
    num_layout.set_alignment(Pango.Alignment.CENTER)
    num_layout.set_text(num, -1)
    cr.move_to(0, H - theme.margin_bottom / 2)
    PangoCairo.show_layout(cr, num_layout)

    surface.finish()

    type_counts: Dict[str, int] = {}
    for block in doc.blocks:
        type_counts[block.type.value] = type_counts.get(block.type.value, 0) + 1
    entity_count = sum(len(block.entities) for block in doc.blocks)
    review_count = sum(len(block.review_tags) for block in doc.blocks)

    return {
        "path": out_path,
        "pages": page_num,
        "blocks": len(doc.blocks),
        "block_types": type_counts,
        "entities": entity_count,
        "review_tags": review_count,
        "theme": theme_name,
        "word_coordinates": all_word_coords,
    }
