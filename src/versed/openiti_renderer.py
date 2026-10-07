"""OpenITI book rendering via Pango/Cairo.

This module owns the public OpenITI rendering contract for the Python library.
It renders the parsed OpenITI block model into book-style PDFs with theme-aware
typography, running headers, marginal page refs, and poetry layout.
"""

from __future__ import annotations

import math
import os
import re
import sys
import tempfile
import unicodedata
from io import BytesIO
from dataclasses import dataclass
from typing import Any, Callable, Collection, Dict, Optional, Tuple

from .openiti_parser import ARABIC_CHAR, BlockType, ParsedDocument


TATWEEL = "\u0640"
LRI = "\u2066"  # LEFT-TO-RIGHT ISOLATE
PDI = "\u2069"  # POP DIRECTIONAL ISOLATE
RLM = "\u200f"  # RIGHT-TO-LEFT MARK
# An optional OPENING bracket is part of the run. Without it, a footnote
# reference like "(2)" matches only from the digit -- so the closing paren
# lands inside the isolate while the opening one stays outside. That splits
# the pair across a direction boundary, and the bidi algorithm then mirrors
# and reorders them, visually gluing the marker to the neighbouring Arabic
# word ("ربيعة (2) بن" rendering as "ربي)(2)بن").
_LTR_RUN = re.compile(r"[(\[]?[A-Za-z0-9][A-Za-z0-9\-\._/:()\[\]]*")
_ENTRY_NUMBER = re.compile(r"^(\d+)(\s*-\s*)")


def _balanced_page_line_counts(
    line_count: int,
    first_capacity: int,
    full_capacity: int,
    *,
    min_before_break: int = 3,
    min_after_break: int = 2,
) -> list[int]:
    """Distribute paragraph lines without widows or orphaned fragments.

    A leading zero means the paragraph should start on the next page. Keeping
    this decision independent of Pango makes the editorial rule testable on
    systems that do not have the GTK stack installed.
    """
    if line_count <= 0:
        return []
    if full_capacity <= 0:
        return [line_count]

    counts: list[int] = []
    remaining = line_count
    capacity = max(0, first_capacity)
    first_page = True

    while remaining > capacity:
        if capacity < min_before_break:
            if first_page:
                counts.append(0)
                capacity = full_capacity
                first_page = False
                continue
            return [*counts, remaining]

        take = capacity
        remainder = remaining - take
        if remainder < min_after_break:
            take -= min_after_break - remainder
            if take < min_before_break:
                if first_page:
                    counts.append(0)
                    capacity = full_capacity
                    first_page = False
                    continue
                return [*counts, remaining]

        counts.append(take)
        remaining -= take
        capacity = full_capacity
        first_page = False

    counts.append(remaining)
    return counts


def protect_ltr_runs(text: str) -> str:
    """Wrap Latin/digit runs in BiDi isolates so they don't disturb RTL flow.

    Mirrors the LRI/PDI strategy used in versed_core.rendering.pdf_renderer.
    Idempotent \u2014 already-isolated runs aren't re-wrapped.
    """
    if not text or LRI in text:
        return text
    return _LTR_RUN.sub(lambda m: f"{LRI}{m.group(0)}{PDI}", text)


def _semantic_pdf_text(text: str, synthetic: Collection[int] = (), base: int = 0) -> str:
    """Return source text suitable for the PDF reading layer and word stream.

    The isolates make mixed Arabic and Latin runs shape correctly, and kashida
    inserts tatweel only to fill a rendered line. Neither belongs in copied
    text or word ids. ``synthetic`` holds the UTF-8 byte offsets (relative to
    ``base``) of tatweel the justifier inserted, so tatweel that is part of
    the source, such as the hijri abbreviation "هـ", survives.
    """
    out: list[str] = []
    offset = base
    for char in text:
        if char not in (LRI, PDI) and not (char == TATWEEL and offset in synthetic):
            out.append(char)
        offset += len(char.encode("utf-8"))
    return "".join(out)


def _align_rendered_to_source(rendered: str, source: str) -> Tuple[list[int], frozenset[int]]:
    """Map each source character to its byte offset in the rendered text.

    Rendering only ever inserts characters into the source: kashida tatweel
    and hard line breaks. Returns the per-character byte offsets and the byte
    offsets of the inserted tatweel.
    """
    offsets: list[int] = []
    synthetic: set[int] = set()
    cursor = 0
    byte = 0
    for char in rendered:
        if cursor < len(source) and char == source[cursor]:
            offsets.append(byte)
            cursor += 1
        elif char == TATWEEL:
            synthetic.add(byte)
        elif char != "\n":
            raise ValueError("rendered text is not the source with insertions")
        byte += len(char.encode("utf-8"))
    if cursor != len(source):
        raise ValueError("rendered text dropped source characters")
    return offsets, frozenset(synthetic)


_PLACEHOLDER_ROW = re.compile(r"^[\s.…]*$")


def _is_placeholder_row(block: Any) -> bool:
    """A paragraph of dots only (". . . . ."), Shamela's mark for omitted text."""
    return (
        block.type == BlockType.PARAGRAPH
        and block.text.count(".") + 3 * block.text.count("…") >= 3
        and bool(_PLACEHOLDER_ROW.match(block.text))
    )


def _page_range_label(pages: list) -> str:
    """"63" for one page, "63–64" for a run of consecutive pages, else a list."""
    labels = [str(page) for page in dict.fromkeys(pages)]
    if len(labels) == 1:
        return labels[0]
    try:
        numbers = [int(label) for label in labels]
    except ValueError:
        return "، ".join(labels)
    if numbers == list(range(numbers[0], numbers[0] + len(numbers))):
        return f"{labels[0]}–{labels[-1]}"
    return "، ".join(labels)


def _accepts_keyword(function: Callable[..., Any], name: str) -> bool:
    """Whether ``function`` takes keyword ``name`` (or any ``**kwargs``)."""
    import inspect

    try:
        parameters = inspect.signature(function).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind == parameter.VAR_KEYWORD
        or (parameter.name == name and parameter.kind != parameter.POSITIONAL_ONLY)
        for parameter in parameters
    )


def _char_byte_offsets(text: str) -> list[int]:
    """Return the UTF-8 byte offset of each character of ``text``."""
    offsets: list[int] = []
    byte = 0
    for char in text:
        offsets.append(byte)
        byte += len(char.encode("utf-8"))
    return offsets


VisualRun = Tuple[int, list[Tuple[str, int]]]


def _bidi_runs(chars: list[tuple[str, int]], rtl: bool, context: Any) -> list[VisualRun]:
    """Split logical characters into UAX #9 level runs, in visual order.

    Returns ``(level, characters)`` pairs; an odd level is right-to-left and
    its characters are listed in visual order (reversed). Pango's own bidi
    implementation (FriBidi) resolves the levels. The drawn layout uses
    isolates (LRI/PDI) that the copied text does not carry, and readers
    rebuild logical order by running the bidi algorithm on the glyphs without
    them, so the runs are resolved on the isolate-free text.
    """
    from gi.repository import Pango

    prefix = RLM if rtl else "\u200e"
    text = prefix + "".join(char for char, _ in chars)
    layout = Pango.Layout.new(context)
    layout.set_auto_dir(True)
    layout.set_text(text, -1)
    encoded = text.encode("utf-8")
    starts: dict[int, int] = {}
    byte = len(prefix.encode("utf-8"))
    for index, (char, _) in enumerate(chars):
        starts[byte] = index
        byte += len(char.encode("utf-8"))
    runs: list[VisualRun] = []
    for line in layout.get_lines_readonly():
        for run in line.runs or []:
            item = run.item
            run_chars = []
            offset = item.offset
            for char in encoded[item.offset : item.offset + item.length].decode("utf-8"):
                if offset in starts:
                    run_chars.append(chars[starts[offset]])
                offset += len(char.encode("utf-8"))
            if run_chars:
                level = item.analysis.level
                runs.append((level, run_chars[::-1] if level % 2 else run_chars))
    return runs


def _visual_line_runs(
    layout_bytes: bytes, line: Any, synthetic: Collection[int], context: Any
) -> list[VisualRun]:
    """Return one laid-out line's text as bidi runs in visual order.

    Characters carry their logical byte offset; isolates and synthetic
    tatweel are dropped. A right-to-left line starts with a RIGHT-TO-LEFT
    MARK run (the line's logical end): readers that rebuild direction from
    the glyph stream (MuPDF) otherwise read a final vowel mark or closing
    quote at the left edge as left-to-right and move it.
    """
    logical: list[tuple[str, int]] = []
    right_to_left = False
    for run in line.runs or []:
        item = run.item
        right_to_left = right_to_left or bool(item.analysis.level % 2)
        offset = item.offset
        for char in layout_bytes[item.offset : item.offset + item.length].decode("utf-8"):
            if char not in (LRI, PDI, "\n") and not (char == TATWEEL and offset in synthetic):
                logical.append((char, offset))
            offset += len(char.encode("utf-8"))
    if not logical:
        return []
    logical.sort(key=lambda pair: pair[1])
    runs = _bidi_runs(logical, right_to_left, context)
    if right_to_left:
        runs.insert(0, (1, [(RLM, -1)]))
    return runs


_SEMANTIC_FONT_CANDIDATES = (
    # Broad symbol coverage first, then fonts that cover the whole Arabic
    # block (Arial Unicode lacks U+0653-U+0657 and the rarer letters).
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/SFArabic.ttf",
    "/System/Library/Fonts/GeezaPro.ttc",
    "/usr/share/fonts/opentype/fonts-hosny-amiri/Amiri-Regular.ttf",
    "/usr/share/fonts/opentype/amiri/Amiri-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _semantic_font_paths() -> list[str]:
    """Locate Unicode fonts whose cmaps name every text-layer character."""
    paths = [path for path in _SEMANTIC_FONT_CANDIDATES if os.path.isfile(path)]
    if not paths:
        raise RuntimeError(
            "OpenITI selectable PDFs need Arial Unicode, SF Arabic, Amiri, or Noto Naskh Arabic."
        )
    return paths


def _semantic_fonts(text: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Subset a fallback chain of fonts covering ``text``.

    Returns the fonts (resource name, bytes, glyph ids, advances) and the
    font index for each character. Letters, marks or digits that no font
    names fail loudly: a silently missing glyph is lost source text.
    """
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "OpenITI selectable PDFs need fonttools; install versed-pdf[pdf]."
        ) from exc

    remaining = {char for char in text if not (char.isspace() and char != " ")}
    fonts: list[dict[str, Any]] = []
    char_font: dict[str, int] = {}
    for path in _semantic_font_paths():
        if not remaining:
            break
        font = TTFont(path, fontNumber=0, lazy=True)
        covered = {char for char in remaining if ord(char) in (font.getBestCmap() or {})}
        if not covered:
            continue
        options = subset.Options()
        options.layout_features = []
        options.font_number = 0
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes={ord(char) for char in covered})
        font = TTFont(path, fontNumber=0)
        subsetter.subset(font)
        buffer = BytesIO()
        font.save(buffer)
        font_bytes = buffer.getvalue()
        font = TTFont(BytesIO(font_bytes))
        cmap = font.getBestCmap()
        glyph_order = font.getGlyphOrder()
        glyph_index = {glyph: index for index, glyph in enumerate(glyph_order)}
        metrics = font["hmtx"].metrics
        units = font["head"].unitsPerEm
        fonts.append({
            "name": f"VersedText{len(fonts)}",
            "bytes": font_bytes,
            "glyph": {char: glyph_index[cmap[ord(char)]] for char in covered},
            "advance": {char: metrics[cmap[ord(char)]][0] / units for char in covered},
        })
        for char in covered:
            char_font[char] = len(fonts) - 1
        remaining -= covered

    missing = sorted(
        char for char in remaining if unicodedata.category(char)[0] in "LMN"
    )
    if missing:
        raise RuntimeError(
            "OpenITI text layer fonts lack characters: "
            + " ".join(f"U+{ord(char):04X}" for char in missing)
        )
    return fonts, char_font


def _font_groups(chars: list[str], char_font: dict[str, int]) -> list[tuple[int, list[str]]]:
    """Group consecutive characters by font; the RLM anchor stays alone."""
    groups: list[tuple[int, list[str]]] = []
    for char in chars:
        index = char_font[char]
        if groups and groups[-1][0] == index and RLM not in (char, groups[-1][1][-1]):
            groups[-1][1].append(char)
        else:
            groups.append((index, [char]))
    return groups


def _attach_semantic_text_layer(
    out_path: str,
    page_text: dict[int, list[tuple[list[VisualRun], float, float, float, float]]],
) -> None:
    """Add an invisible, searchable text layer over the Cairo vector pages.

    The drawn page holds no text: each glyph is an outline fill in a shared
    Form XObject (see ``paint_layout``). Each laid-out line gets invisible glyphs (render mode 3) in
    visual order, one glyph per character, with the font's ToUnicode map
    naming the source character, stretched over the line's drawn extent.
    The vector page itself is left untouched.

    Each right-to-left line opens with a RIGHT-TO-LEFT MARK glyph inside an
    empty ``/ActualText`` span: MuPDF needs the strong RTL anchor to read a
    line-final vowel mark correctly, and the span keeps the mark itself out
    of MuPDF and Poppler text (PDFKit ignores ActualText and returns it as
    an invisible U+200F at the line end).

    Glyph order is UAX #9 visual order of the isolate-free line text, one
    text object per line. Measured against PyMuPDF, Poppler and PDFKit:

    - PDFKit reads the glyph stream and re-runs bidi: exact for Arabic,
      digits (Western and Arabic-Indic), brackets and embedded Latin.
    - Poppler sorts by position: exact for Arabic; next to an LTR run (digits,
      Latin) its RTL dump puts the separating space on the wrong side
      ("681بدمشق"). A Chrome-printed PDF of the same text extracts the same
      way, so this is Poppler's reorder, not the glyph order.
    - MuPDF keeps direction fragments in stream order: exact for Arabic,
      but digits and Latin inside an Arabic line come out of place. Writing
      the runs in logical order puts MuPDF's runs in place but breaks PDFKit,
      which is preferred (Archive.org search uses pdftotext-style text).

    Also rejected: line-level ``/ActualText`` (MuPDF and Poppler reverse it,
    PDFKit ignores it), per-bracket ``/ActualText`` with the mirrored
    character (all three then mirror brackets, PDFKit included), Cairo's own text (split words and presentation forms
    in all three), spaces as positional gaps (no change), and one text object
    per bidi run in visual order (worse in MuPDF).
    """
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "OpenITI PDF rendering needs PyMuPDF for a correct Arabic text layer. "
            "Install versed-pdf[pdf]."
        ) from exc

    all_text = "".join(
        char
        for lines in page_text.values()
        for line in lines
        for _, chars in line[0]
        for char, _ in chars
    )
    if not all_text.strip():
        return
    fonts, char_font = _semantic_fonts(all_text)

    output_dir = os.path.dirname(os.path.abspath(out_path))
    with tempfile.TemporaryDirectory(prefix=".versed-pdf-", dir=output_dir) as temp_dir:
        semantic_path = os.path.join(temp_dir, "semantic.pdf")
        with fitz.open(out_path) as pdf:
            for page_index in sorted(page_text):
                lines = page_text[page_index]
                if page_index >= pdf.page_count or not lines:
                    continue
                page = pdf[page_index]
                page_height = page.rect.height
                operators: list[str] = []
                used: set[int] = set()
                for runs, x, baseline, width, font_size in lines:
                    chars = [
                        char for _, run in runs for char, _ in run if char in char_font
                    ]
                    natural = sum(fonts[char_font[char]]["advance"][char] for char in chars)
                    if not chars or natural <= 0:
                        continue
                    scale = 100.0 * width / (natural * font_size) if width > 0 else 100.0
                    shows = []
                    for index, group in _font_groups(chars, char_font):
                        used.add(index)
                        glyphs = "".join(f"{fonts[index]['glyph'][char]:04X}" for char in group)
                        show = f"/{fonts[index]['name']} {font_size:.2f} Tf <{glyphs}> Tj"
                        if group == [RLM]:
                            # The direction anchor is not text: an empty
                            # /ActualText keeps it out of copied text in
                            # readers that honour it (MuPDF, Poppler).
                            show = f"/Span <</ActualText ()>> BDC {show} EMC"
                        shows.append(show)
                    operators.append(
                        f"BT 3 Tr {scale:.2f} Tz 1 0 0 1 {x:.2f} "
                        f"{page_height - baseline:.2f} Tm " + " ".join(shows) + " ET"
                    )
                if not operators:
                    continue
                page.wrap_contents()
                for index in sorted(used):
                    page.insert_font(fontname=fonts[index]["name"], fontbuffer=fonts[index]["bytes"])
                stream = "q\n" + "\n".join(operators) + "\nQ\n"
                xref = pdf.get_new_xref()
                pdf.update_object(xref, "<<>>")
                pdf.update_stream(xref, stream.encode("ascii"))
                contents = page.get_contents()
                pdf.xref_set_key(
                    page.xref,
                    "Contents",
                    "[" + " ".join(f"{item} 0 R" for item in [*contents, xref]) + "]",
                )
            pdf.save(semantic_path, garbage=4, deflate=True, deflate_fonts=True, use_objstms=1)
        os.replace(semantic_path, out_path)


_PANGO_GLYPH_EMPTY = 0x0FFFFFFF
_PANGO_GLYPH_UNKNOWN_FLAG = 0x10000000


def _layout_glyph_placements(layout: Any) -> Optional[list[tuple[Any, str, int, float, float]]]:
    """Return each drawn glyph of ``layout`` as (font, font key, glyph id, dx, dy).

    Offsets are in points from the layout origin and follow the placement
    Pango's own renderer uses for ``layout_path``: run x from the line
    iterator, then the shaped advances, x/y offsets and run rise. Kashida
    and mark positioning therefore come straight from HarfBuzz.

    Glyph ids and geometry are read from ``Pango.Layout.serialize`` because
    PyGObject mis-marshals ``PangoGlyphString.glyphs`` (it reads the 20-byte
    ``PangoGlyphInfo`` array with the wrong stride). Runs are paired with the
    iterator's runs in order and checked by text offset and glyph count.

    Returns ``None`` when the layout holds unknown-glyph boxes, which only
    ``layout_path`` can draw.
    """
    import json

    from gi.repository import Pango

    output = json.loads(
        layout.serialize(Pango.LayoutSerializeFlags.OUTPUT).get_data()
    )["output"]
    if output.get("unknown-glyphs"):
        return None
    runs = [run for line in output["lines"] for run in line.get("runs", [])]
    scale = Pango.SCALE
    placements: list[tuple[Any, str, int, float, float]] = []
    line_iter = layout.get_iter()
    index = 0
    while True:
        run = line_iter.get_run_readonly()
        if run is not None:
            if index >= len(runs):
                raise RuntimeError("Pango layout runs disagree with the serialized layout")
            data = runs[index]
            index += 1
            item = run.item
            analysis = item.analysis
            font = analysis.font
            glyph_string = run.glyphs
            if item.offset != data["offset"] or glyph_string.num_glyphs != len(data["glyphs"]):
                raise RuntimeError("Pango layout runs disagree with the serialized layout")
            font_key = json.dumps(data["font"], sort_keys=True)
            _, logical = line_iter.get_run_extents()
            base_x = logical.x + run.start_x_offset
            base_y = line_iter.get_baseline() - run.y_offset
            advance = 0
            for glyph in data["glyphs"]:
                glyph_id = glyph["glyph"]
                if glyph_id & _PANGO_GLYPH_UNKNOWN_FLAG:
                    return None
                if glyph_id != _PANGO_GLYPH_EMPTY:
                    placements.append((
                        font,
                        font_key,
                        glyph_id,
                        (base_x + advance + glyph.get("x-offset", 0)) / scale,
                        (base_y + glyph.get("y-offset", 0)) / scale,
                    ))
                advance += glyph["width"]
        if not line_iter.next_run():
            break
    if index != len(runs):
        raise RuntimeError("Pango layout runs disagree with the serialized layout")
    return placements


def _configure_pango_backend(
    platform: str = sys.platform,
    environ: Optional[Dict[str, str]] = None,
) -> None:
    """Use Fontconfig on macOS so Cairo preserves shaped glyph positions."""
    env = os.environ if environ is None else environ
    if platform == "darwin":
        env.setdefault("PANGOCAIRO_BACKEND", "fc")


def _resolved_font_family(family: str, sample: str = "بسم الله الرحمن الرحيم") -> str:
    """Return the family Pango actually uses to draw ``sample`` in ``family``.

    Pango silently substitutes another face when the requested one is not
    installed, or falls back per glyph when the face lacks a character;
    callers compare the result with the request.
    """
    _configure_pango_backend()
    import cairo
    import gi

    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    surface = cairo.ImageSurface(cairo.FORMAT_A8, 8, 8)
    context = PangoCairo.create_layout(cairo.Context(surface)).get_context()
    font = context.load_font(Pango.FontDescription.from_string(f"{family} 12"))
    if font is None:
        return ""
    resolved = font.describe().get_family() or ""
    coverage = font.get_coverage(Pango.Language.from_string("ar"))
    missing = [
        char for char in sample
        if not char.isspace() and coverage.get(ord(char)) == Pango.CoverageLevel.NONE
    ]
    if missing:
        return f"{resolved} (lacks {''.join(missing)}; per-glyph fallback)"
    return resolved


def _require_font_family(family: str) -> None:
    """Fail loudly instead of typesetting a book in a substituted face."""
    used = _resolved_font_family(family)
    if used.lower() != family.lower():
        raise RuntimeError(
            f"OpenITI font {family!r} is not available to Pango (it would use {used!r}). "
            "Install it and refresh fontconfig, e.g. on macOS "
            "`brew install --cask font-amiri && fc-cache -f`, on Debian/Ubuntu "
            "`apt install fonts-hosny-amiri`."
        )


def _format_entry_heading(text: str) -> str:
    """Use Arabic-Indic digits for entry ordinals in Arabic headings."""
    return _ENTRY_NUMBER.sub(
        lambda match: f"{match.group(1).translate(W2E)}{match.group(2)}",
        text,
        count=1,
    )


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


def _per_line_kashida(
    layout,
    text: str,
    target_w: float,
    measure_fn: Callable[[str], float],
    max_per_line: int,
) -> str:
    """Apply kashida to each Pango-laid line independently and return the
    joined text with hard line breaks. Caller should set WrapMode.NONE before
    re-applying the returned text to the layout.

    Skips the last line of the paragraph (justifying the last line looks bad).
    """
    n = layout.get_line_count()
    if n <= 0:
        return text
    text_bytes = text.encode("utf-8")
    out: list[str] = []
    for i in range(n):
        line = layout.get_line_readonly(i)
        start = line.start_index
        length = line.length
        line_text = text_bytes[start:start + length].decode("utf-8", "replace")
        line_text = line_text.rstrip("\n")
        is_last = i == n - 1
        if not is_last and line_text.strip() and ARABIC_CHAR.search(line_text):
            line_text = apply_kashida(line_text, target_w, measure_fn, max_per_line)
        out.append(line_text)
    return "\n".join(out)


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
    color_apparatus: Tuple[float, float, float] = (0.42, 0.38, 0.34)
    footnote_area_height: float = 92.0
    footnote_max_chars: int = 900
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
        margin_inner=75,
        margin_outer=75,
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
        kashida_max=8,
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
    """Render an OpenITI parsed document to PDF using Pango/Cairo.

    ``cover_renderer(cr, width, height, cover_metadata, cover_style)`` draws
    the first page. If it also accepts a ``paint_layout`` keyword it receives
    ``paint_layout(layout)``, which paints a Pango layout at the current
    point in the current solid colour exactly as the body text is painted:
    outline glyphs that copy nothing, plus the invisible logical-order text
    layer. Text drawn with ``PangoCairo.show_layout`` instead copies in
    visual order (reversed Arabic, spaced-out letter-spaced Latin).
    """
    _configure_pango_backend()
    import cairo
    import gi

    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    theme = THEMES.get(theme_name, THEMES["scholarly"])
    W, H = theme.page_w, theme.page_h
    for family in dict.fromkeys((theme.font_body, theme.font_heading)):
        _require_font_family(family)

    surface = cairo.PDFSurface(out_path, W, H)
    cr = cairo.Context(surface)

    page_num = 0
    y = theme.margin_top
    current_chapter = doc.title or ""
    current_section = ""
    all_word_coords: list[dict] = []
    semantic_page_text: dict[int, list[tuple[list[VisualRun], float, float, float, float]]] = {}
    glyph_forms: dict[tuple, Any] = {}
    current_block_index = 0
    pending_apparatus_notes: list[str] = []
    active_apparatus_notes: list[str] = []

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

    def paint_layout(layout: Any, synthetic: Collection[int] = frozenset()) -> None:
        """Paint shaped outlines and record each line for the text layer.

        Each glyph is drawn as a reference to one shared outline form at the
        position Pango's own ``layout_path`` would fill it (tested to match
        exactly), so the page has no font text and no repeated outlines.
        Layouts with unknown-glyph boxes or a non-solid source fall back to
        ``layout_path``.
        """
        x, y = cr.get_current_point()
        rendered_bytes = layout.get_text().encode("utf-8")
        physical_page = page_num if has_front_matter else page_num - 1
        page_lines = semantic_page_text.setdefault(physical_page, [])
        # The drawn em size, not the line height: tall diacritics and line
        # spacing would otherwise make invisible glyph boxes overlap the
        # neighbouring lines, and PDFKit then merges those lines.
        font_size = layout.get_font_description().get_size() / Pango.SCALE
        line_iter = layout.get_iter()
        while True:
            line = line_iter.get_line_readonly()
            _, layout_logical = line_iter.get_line_extents()
            visual = _visual_line_runs(rendered_bytes, line, synthetic, layout.get_context())
            if any(not char.isspace() for _, chars in visual for char, _ in chars):
                page_lines.append(
                    (
                        visual,
                        x + layout_logical.x / Pango.SCALE,
                        y + line_iter.get_baseline() / Pango.SCALE,
                        layout_logical.width / Pango.SCALE,
                        font_size,
                    )
                )
            if not line_iter.next_line():
                break
        source = cr.get_source()
        placements = _layout_glyph_placements(layout)
        if placements is None or not isinstance(source, cairo.SolidPattern):
            PangoCairo.layout_path(cr, layout)
            cr.fill()
            return
        rgba = source.get_rgba()
        cr.new_path()
        for font, font_key, glyph, dx, dy in placements:
            form = glyph_form(font, font_key, glyph, rgba)
            if form is None:
                continue
            cr.save()
            cr.translate(x + dx, y + dy)
            cr.set_source_surface(form, 0, 0)
            cr.paint()
            cr.restore()

    def glyph_form(font: Any, font_key: str, glyph: int, rgba: tuple) -> Any:
        """One recorded outline per (font, glyph, colour), reused by reference.

        Cairo's PDF surface writes a recording surface once as a Form
        XObject and draws every later use with ``cm`` + ``Do``, so a book
        holds each distinct glyph shape once instead of a full outline per
        occurrence. The form is an outline fill, never text, so the visible
        page still contributes nothing to copied or searched text.
        """
        key = (font_key, glyph, rgba)
        if key in glyph_forms:
            return glyph_forms[key]
        form = cairo.RecordingSurface(cairo.Content.COLOR_ALPHA, None)
        form_cr = cairo.Context(form)
        form_cr.set_scaled_font(PangoCairo.Font.get_scaled_font(font))
        form_cr.glyph_path([cairo.Glyph(glyph, 0, 0)])
        x1, y1, x2, y2 = form_cr.fill_extents()
        if x2 <= x1 or y2 <= y1:
            glyph_forms[key] = None
            return None
        form_cr.set_source_rgba(*rgba)
        form_cr.fill()
        glyph_forms[key] = form
        return form

    def apparatus_layout() -> Any:
        layout = make_layout(font_size=max(7, theme.size_body - 3), width=tw())
        layout.set_alignment(Pango.Alignment.LEFT)
        layout.set_justify(False)
        layout.set_line_spacing(1.15)
        return layout

    def apparatus_height(layout: Any, notes: list[str]) -> float:
        layout.set_text(protect_ltr_runs(" \u2022 ".join(notes)), -1)
        _, ext = layout.get_pixel_extents()
        return ext.height

    def apparatus_reserve_height(notes: list[str]) -> float:
        clean_notes = [note.strip() for note in notes if note.strip()]
        if not clean_notes:
            return 0.0
        height = apparatus_height(apparatus_layout(), clean_notes)
        # The rule and breathing room belong to pages that actually carry a
        # note; reserving the theme maximum on every page leaves six blank
        # body lines in texts whose references have no apparatus stream.
        return min(theme.footnote_area_height, max(24.0, height + 16.0))

    def render_pending_apparatus_notes(whole_page: bool = False) -> None:
        """Draw as much pending apparatus as fits; carry the rest forward.

        No source text is ever dropped: a note too long for this page is cut
        at a word boundary and its remainder opens the next page's apparatus.
        ``whole_page`` gives a notes-only page its full body area.
        """
        if page_num <= 0 or not pending_apparatus_notes:
            return
        notes = [note.strip() for note in pending_apparatus_notes if note.strip()]
        if not notes:
            pending_apparatus_notes.clear()
            return

        if whole_page:
            rule_y = theme.margin_top
        else:
            rule_y = H - theme.margin_bottom - apparatus_reserve_height(notes) + 6
        text_y = rule_y + 8
        max_note_h = max(18, (H - theme.margin_bottom / 2 - 8) - text_y)

        selected: list[str] = []
        remaining = list(notes)
        layout = apparatus_layout()

        while remaining:
            if apparatus_height(layout, [*selected, remaining[0]]) <= max_note_h:
                selected.append(remaining.pop(0))
                continue
            words = remaining[0].split(" ")
            lo, hi, best = 1, len(words) - 1, 0
            while lo <= hi:
                mid = (lo + hi) // 2
                if apparatus_height(layout, [*selected, " ".join(words[:mid])]) <= max_note_h:
                    best, lo = mid, mid + 1
                else:
                    hi = mid - 1
            if not best and not selected:
                # Not even one word fits: draw it anyway so the stream advances.
                best = 1
            if best:
                selected.append(" ".join(words[:best]))
                rest = " ".join(words[best:]).strip()
                if rest:
                    remaining[0] = rest
                else:
                    remaining.pop(0)
            break

        cr.set_source_rgb(*theme.color_apparatus)
        cr.set_line_width(0.25)
        cr.move_to(ml(), rule_y)
        cr.line_to(ml() + tw() * 0.38, rule_y)
        cr.stroke()

        layout.set_text(protect_ltr_runs(" \u2022 ".join(selected)), -1)
        cr.move_to(ml(), text_y)
        paint_layout(layout)
        pending_apparatus_notes[:] = remaining

    def decorate_current_page(notes_only: bool = False) -> None:
        if page_num <= 0:
            return
        render_pending_apparatus_notes(whole_page=notes_only)
        num_str = str(page_num).translate(W2E)
        cr.set_source_rgb(*theme.color_ornament)
        num_layout = make_layout(font_size=theme.size_page_num, width=W)
        num_layout.set_alignment(Pango.Alignment.CENTER)
        num_layout.set_text(num_str, -1)
        cr.move_to(0, H - theme.margin_bottom / 2)
        paint_layout(num_layout)
        if theme.running_headers and current_chapter:
            cr.set_source_rgb(*theme.color_running_header)
            header_layout = make_layout(font_size=theme.size_running_header, width=tw())
            header_text = current_section or current_chapter
            if len(header_text) > 60:
                header_text = header_text[:57] + "..."
            header_layout.set_alignment(Pango.Alignment.CENTER)
            header_layout.set_text(header_text, -1)
            cr.move_to(ml(), theme.margin_top - 30)
            paint_layout(header_layout)
            cr.set_line_width(0.3)
            cr.move_to(ml(), theme.margin_top - 8)
            cr.line_to(ml() + tw(), theme.margin_top - 8)
            cr.stroke()

    def new_page() -> None:
        nonlocal y, page_num
        if page_num > 0:
            decorate_current_page()
        cr.show_page()
        page_num += 1
        y = theme.margin_top

    def max_y() -> float:
        reserve = apparatus_reserve_height(
            [*pending_apparatus_notes, *active_apparatus_notes]
        )
        return H - theme.margin_bottom - reserve

    def check_space(needed: float) -> None:
        if y + needed > max_y():
            new_page()

    def source_word_spans(
        source: str,
        char_bytes: list[int],
        decoration_words: int = 0,
        source_words: Optional[list[str]] = None,
        first_index: int = 0,
    ) -> list[tuple[int, int, str, int]]:
        """Locate each source word by its byte span in the drawn text.

        Returns (first byte, last character's byte, name, word index) per
        word. ``decoration_words`` leading words get no entry; synthetic
        tatweel never reaches a name.
        """
        spans = [match.span() for match in re.finditer(r"\S+", source)][decoration_words:]
        names = [_semantic_pdf_text(source[start:end]) for start, end in spans]
        if source_words is not None:
            if len(source_words) != len(names):
                raise ValueError(
                    f"drawn words {names!r} do not match source words {source_words!r}"
                )
            names = list(source_words)
        return [
            (char_bytes[start], char_bytes[end - 1], name, first_index + index)
            for index, ((start, end), name) in enumerate(zip(spans, names))
            if name
        ]

    def record_word_boxes(
        layout: Any, words: list[tuple[int, int, str, int]], origin_x: float, origin_y: float
    ) -> None:
        """Append one box per word of ``layout`` drawn at (origin_x, origin_y)."""
        for start_byte, last_char_byte, name, word_index in words:
            rect_start = layout.index_to_pos(start_byte)
            # Pango uses UTF-8 byte offsets, but each index must still be a
            # code-point boundary; the last character's own offset is one.
            rect_end = layout.index_to_pos(last_char_byte)
            # Pango returns values in Pango units (1/1024 pixel)
            py = rect_start.y / Pango.SCALE
            ph = rect_start.height / Pango.SCALE
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
                "text": name,
                "x": origin_x + px,
                "y": origin_y + py,
                "width": pw,
                "height": ph,
                "page": page_num,
                "block_index": current_block_index,
                "word_index": word_index,
            })

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
        decoration_words: int = 0,
        source_words: Optional[list[str]] = None,
        _allow_split: bool = True,
        _words: Optional[list[tuple[int, int, str, int]]] = None,
        _synthetic: frozenset[int] = frozenset(),
        _min_after_break: int = 2,
    ) -> None:
        """Lay out and paint one block of text, flowing across pages.

        The word stream names source words only: ``decoration_words`` leading
        drawn words (entry markers, labels) get no box, and ``source_words``
        names the remaining drawn words when the drawing rewrites them (for
        example Arabic-Indic ordinals). Words are located by their byte span
        in the source, so kashida and page or line breaks never split or
        rename a word.
        """
        nonlocal y, current_block_index
        if _words is None:
            source = text if centered else protect_ltr_runs(text)
            text = source
        layout = make_layout(font_size=font_size, bold=bold)
        # In Pango's bidirectional layout, LEFT aligns RTL text to the physical
        # right edge of the layout box; RIGHT sends it to the physical left.
        layout.set_alignment(Pango.Alignment.CENTER if centered else Pango.Alignment.LEFT)
        # Native Pango justification expands Arabic spaces unevenly and makes
        # mixed editorial apparatus look jagged. Keep body blocks flush-right
        # and leave true justification to a later shaping pass.
        layout.set_justify(False)
        if _words is not None:
            # A page-split chunk is already broken into the parent's lines.
            # Re-wrapping them can add lines (Pango re-breaks some lines laid
            # out alone, e.g. around " ، "), pushing text past the bottom.
            layout.set_wrap(Pango.WrapMode.NONE)
        layout.set_text(text, -1)
        if use_kashida and theme.kashida and not centered and _words is None:
            text = _per_line_kashida(
                layout, text, tw(),
                lambda t: measure(t, font_size),
                theme.kashida_max,
            )
            layout.set_wrap(Pango.WrapMode.NONE)
            layout.set_text(text, -1)
        layout.set_line_spacing(theme.line_height)

        if _words is None:
            char_bytes, _synthetic = _align_rendered_to_source(text, source)
            _words = (
                source_word_spans(source, char_bytes, decoration_words, source_words)
                if track_words
                else []
            )

        _, ext = layout.get_pixel_extents()
        spacing = spacing_after if spacing_after is not None else theme.size_body * 0.35

        overflows_page = y + ext.height + spacing > max_y()

        if _allow_split and overflows_page:
            encoded = text.encode("utf-8")
            line_spans = [
                (line.start_index, line.start_index + line.length)
                for line in layout.get_lines_readonly()
            ]
            lines = [encoded[start:end].decode("utf-8") for start, end in line_spans]
            if len(lines) > 1:

                def capacity(line_texts: list[str], available: float) -> int:
                    fitting = 0
                    pending: list[str] = []
                    for line_text in line_texts:
                        candidate = "\n".join([*pending, line_text])
                        candidate_layout = make_layout(font_size=font_size, bold=bold)
                        candidate_layout.set_alignment(
                            Pango.Alignment.CENTER if centered else Pango.Alignment.LEFT
                        )
                        candidate_layout.set_justify(False)
                        candidate_layout.set_wrap(Pango.WrapMode.NONE)
                        candidate_layout.set_line_spacing(theme.line_height)
                        candidate_layout.set_text(candidate, -1)
                        _, candidate_ext = candidate_layout.get_pixel_extents()
                        if pending and candidate_ext.height + spacing > available:
                            break
                        if not pending and candidate_ext.height + spacing > available:
                            return 0
                        pending.append(line_text)
                        fitting += 1
                    return fitting

                first_capacity = capacity(lines, max_y() - y)
                full_capacity = capacity(lines, max_y() - theme.margin_top)
                line_counts = _balanced_page_line_counts(
                    len(lines),
                    first_capacity,
                    full_capacity,
                    min_after_break=_min_after_break,
                )

                def chunk_offset(line_index: int, first: int, byte: int) -> int:
                    # Chunk text is its lines joined with "\n", one byte each.
                    before = sum(
                        len(lines[k].encode("utf-8")) + 1 for k in range(first, line_index)
                    )
                    return before + byte - line_spans[line_index][0]

                def line_of(byte: int) -> int:
                    for index, (start, end) in enumerate(line_spans):
                        if start <= byte < end:
                            return index
                    return -1

                rendered_chunk = False
                cursor = 0
                for chunk_index, count in enumerate(line_counts):
                    if count == 0:
                        new_page()
                        continue
                    first, last = cursor, cursor + count
                    cursor = last
                    chunk = "\n".join(lines[first:last])
                    chunk_words = []
                    for start, end, name, index in _words:
                        start_line = line_of(start)
                        if not first <= start_line < last:
                            continue
                        end_line = line_of(end)
                        if not first <= end_line < last:
                            # The word runs onto the next page: box the part
                            # drawn here.
                            end_line = start_line
                            end = line_spans[start_line][1] - 1
                            while end > start and (encoded[end] & 0xC0) == 0x80:
                                end -= 1
                        chunk_words.append(
                            (
                                chunk_offset(start_line, first, start),
                                chunk_offset(end_line, first, end),
                                name,
                                index,
                            )
                        )
                    chunk_synthetic = frozenset(
                        chunk_offset(line_of(byte), first, byte)
                        for byte in _synthetic
                        if first <= line_of(byte) < last
                    )
                    if rendered_chunk:
                        new_page()
                    is_last = chunk_index == len(line_counts) - 1
                    draw_text(
                        chunk,
                        font_size=font_size,
                        color=color,
                        centered=centered,
                        bold=bold,
                        justify=justify,
                        spacing_after=spacing if is_last else 0,
                        use_kashida=False,
                        track_words=track_words,
                        _allow_split=False,
                        _words=chunk_words,
                        _synthetic=chunk_synthetic,
                        _min_after_break=_min_after_break,
                    )
                    rendered_chunk = True
                return

        check_space(ext.height + spacing)
        if y + ext.height > max_y():
            new_page()

        record_word_boxes(layout, _words, ml(), y)

        cr.set_source_rgb(*(color or theme.color_body))
        cr.move_to(ml(), y)
        paint_layout(layout, _synthetic)
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

    def draw_verse_number(number: Optional[str], row_y: float) -> None:
        """Print a source verse number in the margin opposite the page markers, outside the word stream."""
        if not number:
            return
        cr.set_source_rgb(*theme.color_page_ref)
        number_layout = make_layout(font_size=theme.size_page_ref, width=30)
        number_layout.set_alignment(Pango.Alignment.CENTER)
        number_layout.set_text(f"({str(number).strip('()').translate(W2E)})", -1)
        # Page markers take the outer margin (right on even pages, left on
        # odd); verse numbers take the other one so the two never collide.
        x = ml() - 34 if page_num % 2 == 0 else W - mr() + 4
        cr.move_to(x, row_y + 2)
        paint_layout(number_layout)

    def draw_verse_pair(a: str, b: str, number: Optional[str] = None) -> None:
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
        # Word stream order is the block's: hemistich A (the right-hand,
        # first-read column) then B, numbered on from A's last word.
        a_words = source_word_spans(a, _char_byte_offsets(a))
        b_words = source_word_spans(b, _char_byte_offsets(b), first_index=len(a.split()))
        record_word_boxes(left_layout, a_words, ml() + col_w + 40, y)
        record_word_boxes(right_layout, b_words, ml(), y)
        cr.set_source_rgb(*theme.color_verse)
        cr.move_to(ml() + col_w + 40, y)
        paint_layout(left_layout)
        cr.set_source_rgb(*theme.color_ornament)
        ornament_layout = make_layout(font_size=theme.size_verse, width=40)
        ornament_layout.set_alignment(Pango.Alignment.CENTER)
        ornament_layout.set_text(theme.verse_ornament, -1)
        cr.move_to(ml() + col_w, y)
        paint_layout(ornament_layout)
        cr.set_source_rgb(*theme.color_verse)
        cr.move_to(ml(), y)
        paint_layout(right_layout)
        draw_verse_number(number, y)
        y += row_h + 4

    page_num = 0
    has_front_matter = bool((cover_metadata and cover_renderer is not None) or doc.title)
    if cover_metadata and cover_renderer is not None:
        if _accepts_keyword(cover_renderer, "paint_layout"):
            cover_renderer(cr, W, H, cover_metadata, cover_style, paint_layout=paint_layout)
        else:
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
            track_words=False,
        )
        if doc.author:
            draw_text(
                doc.author,
                font_size=theme.size_h2,
                color=theme.color_ornament,
                centered=True,
                spacing_after=20,
                track_words=False,
            )
        y += 5
        draw_line(0.4, 0.8)
    if has_front_matter:
        new_page()
    else:
        page_num = 1

    prev = None
    i = 0
    non_flowing_types = {
        BlockType.PAGE_REF,
        BlockType.MILESTONE,
        BlockType.APPARATUS_NOTE,
    }
    last_flowing_index = next(
        (
            index
            for index in range(len(doc.blocks) - 1, -1, -1)
            if doc.blocks[index].type not in non_flowing_types
        ),
        -1,
    )
    while i < len(doc.blocks):
        block = doc.blocks[i]

        if _is_placeholder_row(block):
            # A Shamela row of dots stands for a page whose text the source
            # omits; the page marker range below already records the gap.
            current_block_index += 1
            i += 1
            continue

        if block.type == BlockType.PAGE_REF:
            # Source pages with no main text between their markers share one
            # marker ("[ص ٦٣–٦٤]") instead of stacking in one spot.
            pages = [block.meta.get("page", 0)]
            j = i + 1
            while j < len(doc.blocks) and (
                doc.blocks[j].type in (BlockType.PAGE_REF, BlockType.MILESTONE)
                or _is_placeholder_row(doc.blocks[j])
            ):
                if doc.blocks[j].type == BlockType.PAGE_REF:
                    pages.append(doc.blocks[j].meta.get("page", 0))
                elif doc.blocks[j].type != BlockType.MILESTONE:
                    current_block_index += 1
                j += 1
            if theme.marginal_page_refs:
                ref = f"[ص {_page_range_label(pages).translate(W2E)}]"
                width = 50 if len(pages) == 1 else 62
                cr.set_source_rgb(*theme.color_page_ref)
                ref_layout = make_layout(font_size=theme.size_page_ref, width=width)
                ref_layout.set_alignment(Pango.Alignment.CENTER)
                ref_layout.set_text(ref, -1)
                # Centred where a single marker is centred.
                x = W - mr() + 33 if page_num % 2 == 0 else ml() - 25
                cr.move_to(x - width / 2, y - 5)
                paint_layout(ref_layout)
            i = j
            continue

        if block.type == BlockType.MILESTONE:
            i += 1
            continue

        attached_apparatus: list[str] = []
        next_i = i + 1
        while (
            next_i < len(doc.blocks)
            and doc.blocks[next_i].type == BlockType.APPARATUS_NOTE
        ):
            attached_apparatus.append(doc.blocks[next_i].text)
            next_i += 1
        active_apparatus_notes[:] = attached_apparatus

        if block.type == BlockType.TITLE:
            if prev and prev != BlockType.PAGE_REF:
                y += theme.size_body * 1.6
            is_book_title = block.text.strip().startswith("كتاب ")
            size = theme.size_h1 if is_book_title else theme.size_h2
            check_space(65 if is_book_title else 45)
            if is_book_title:
                current_chapter = block.text
                current_section = ""
            else:
                current_section = block.text
            # Titles are voiced like any heading, so their words get boxes.
            draw_text(
                block.text,
                font_size=size,
                color=theme.color_heading,
                centered=True,
                bold=True,
                spacing_after=10,
            )

        elif block.type == BlockType.HEADING_1:
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
                track_words=bool(block.text),
                source_words=block.text.split() if block.text else None,
            )

        elif block.type in ENTRY_MARKERS:
            if prev:
                y += theme.size_body * 0.5
            # An entry label is useful only with enough of its biography to
            # establish the subject. Four composed lines cover the label plus
            # three prose lines across the bundled Arabic themes.
            check_space(theme.size_body * 10)
            marker = ENTRY_MARKERS[block.type]
            color_key = ENTRY_COLORS.get(block.type, "color_body")
            color = getattr(theme, color_key, theme.color_body)
            heading = _format_entry_heading(block.text)
            draw_text(
                f"{marker}  {heading}",
                font_size=theme.size_body,
                color=color,
                bold=True,
                spacing_after=6,
                decoration_words=len(marker.split()),
                source_words=block.text.split(),
            )

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
            draw_verse_pair(block.hemistich_a, block.hemistich_b, block.meta.get("verse_number"))

        elif block.type == BlockType.VERSE_LINE:
            check_space(theme.size_verse * 2)
            draw_verse_number(block.meta.get("verse_number"), y)
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

        elif block.type == BlockType.APPARATUS_NOTE:
            if y > H - theme.margin_bottom - apparatus_reserve_height([block.text]):
                new_page()
            pending_apparatus_notes.append(block.text)

        elif block.type == BlockType.MORPHO_TAG:
            cat = block.meta.get("category", "?")
            draw_text(
                f"— {cat} —",
                font_size=theme.size_body - 2,
                color=theme.color_morpho,
                centered=True,
                spacing_after=4,
                track_words=False,
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
                decoration_words=len(f"{label}:".split()),
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
                decoration_words=len(f"{label}:".split()),
            )

        elif block.type == BlockType.LACUNA:
            draw_text(
                "[ . . . . . . ]",
                font_size=theme.size_body,
                color=theme.color_lacuna,
                centered=True,
                spacing_after=6,
                track_words=False,
            )

        elif block.type == BlockType.PARAGRAPH:
            draw_text(
                block.text,
                font_size=theme.size_body,
                color=theme.color_body,
                use_kashida=True,
                spacing_after=theme.size_body * 0.6,
                _min_after_break=6 if i == last_flowing_index else 2,
            )

        prev = block.type
        if attached_apparatus:
            pending_apparatus_notes.extend(attached_apparatus)
        active_apparatus_notes.clear()
        i = next_i
        if block.type not in (BlockType.PAGE_REF, BlockType.MILESTONE):
            current_block_index += 1

    decorate_current_page()
    # Apparatus still pending after the last body line continues on
    # notes-only pages; it is never dropped.
    while pending_apparatus_notes:
        cr.show_page()
        page_num += 1
        decorate_current_page(notes_only=True)

    surface.finish()
    _attach_semantic_text_layer(out_path, semantic_page_text)

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
