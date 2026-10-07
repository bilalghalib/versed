import pytest

from versed import OPENITI_THEMES, OpenITIBookTheme, render_openiti_book


def test_openiti_renderer_exports():
    assert callable(render_openiti_book)
    assert "scholarly" in OPENITI_THEMES
    assert isinstance(OPENITI_THEMES["scholarly"], OpenITIBookTheme)


def test_ltr_reference_keeps_its_opening_parenthesis_in_the_isolate():
    from versed.openiti_renderer import LRI, PDI, protect_ltr_runs

    text = protect_ltr_runs("ربيعة (2) بن حارثة")
    assert text == f"ربيعة {LRI}(2){PDI} بن حارثة"


def test_macos_renderer_selects_searchable_fontconfig_backend():
    from versed.openiti_renderer import _configure_pango_backend

    env = {}
    _configure_pango_backend(platform="darwin", environ=env)
    assert env == {"PANGOCAIRO_BACKEND": "fc"}

    explicit = {"PANGOCAIRO_BACKEND": "coretext"}
    _configure_pango_backend(platform="darwin", environ=explicit)
    assert explicit == {"PANGOCAIRO_BACKEND": "coretext"}

    linux_env = {}
    _configure_pango_backend(platform="linux", environ=linux_env)
    assert linux_env == {}


def test_entry_heading_uses_arabic_indic_ordinal():
    from versed.openiti_renderer import _format_entry_heading

    assert _format_entry_heading("12 - إبراهيم النخعي") == "١٢ - إبراهيم النخعي"


def test_page_line_balancing_avoids_widows_without_gtk():
    from versed.openiti_renderer import _balanced_page_line_counts

    assert _balanced_page_line_counts(5, 3, 40) == [3, 2]
    assert _balanced_page_line_counts(4, 3, 40) == [0, 4]
    assert _balanced_page_line_counts(41, 40, 40) == [39, 2]
    assert _balanced_page_line_counts(44, 2, 40) == [0, 40, 4]
    assert _balanced_page_line_counts(32, 30, 30, min_after_break=6) == [26, 6]


def test_render_book_returns_word_coordinates():
    """Rendered book should include per-word bounding boxes."""
    from versed.openiti_parser import ParsedDocument, Block, BlockType
    from versed.openiti_renderer import render_book

    doc = ParsedDocument(
        title="Test",
        author="Author",
        blocks=[
            Block(BlockType.PARAGRAPH, "بسم الله الرحمن الرحيم"),
        ],
    )
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        out_path = f.name
    try:
        result = render_book(doc, out_path)
        assert "word_coordinates" in result, "render_book must return word_coordinates"
        coords = result["word_coordinates"]
        # Filter to content pages (page > 0, cover is page 0)
        content_coords = [wc for wc in coords if wc["page"] > 0]
        assert len(content_coords) == 4, (
            f"Expected 4 Arabic words, got {len(content_coords)}"
        )
        for wc in content_coords:
            assert "text" in wc
            assert "x" in wc and "y" in wc
            assert "width" in wc and "height" in wc
            assert "page" in wc
            assert wc["width"] > 0 and wc["height"] > 0
    finally:
        os.unlink(out_path)


def test_render_without_front_matter_has_no_blank_leading_page():
    fitz = pytest.importorskip("fitz")
    from versed.openiti_parser import Block, BlockType, ParsedDocument
    from versed.openiti_renderer import render_book

    doc = ParsedDocument(
        blocks=[Block(BlockType.PARAGRAPH, "بسم الله الرحمن الرحيم")],
    )
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as output:
        out_path = output.name
    try:
        result = render_book(doc, out_path)
        with fitz.open(out_path) as pdf:
            assert pdf.page_count == 1
            assert len(pdf[0].get_text()) > 10
        assert result["pages"] == 1
    finally:
        os.unlink(out_path)


def test_long_paragraph_flows_across_pages_with_sequential_word_indices():
    fitz = pytest.importorskip("fitz")
    from versed.openiti_parser import Block, BlockType, ParsedDocument
    from versed.openiti_renderer import render_book

    words = ["كلمة"] * 900
    doc = ParsedDocument(blocks=[Block(BlockType.PARAGRAPH, " ".join(words))])
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as output:
        out_path = output.name
    try:
        result = render_book(doc, out_path)
        coords = result["word_coordinates"]
        with fitz.open(out_path) as pdf:
            assert pdf.page_count > 1
        assert len(coords) == len(words)
        assert [word["word_index"] for word in coords] == list(range(len(words)))
        assert len({word["page"] for word in coords}) > 1
    finally:
        os.unlink(out_path)


def test_prose_uses_unreserved_body_area_when_there_are_no_apparatus_notes():
    from versed.openiti_parser import Block, BlockType, ParsedDocument
    from versed.openiti_renderer import render_book

    doc = ParsedDocument(
        blocks=[Block(BlockType.PARAGRAPH, " ".join(["كلمة"] * 900))],
    )
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as output:
        out_path = output.name
    try:
        result = render_book(doc, out_path)
        first_page_words = [
            word for word in result["word_coordinates"] if word["page"] == 1
        ]
        assert first_page_words
        assert max(word["y"] for word in first_page_words) > 700
    finally:
        os.unlink(out_path)


def test_biography_heading_stays_with_three_lines_of_prose():
    from versed.openiti_parser import Block, BlockType, ParsedDocument
    from versed.openiti_renderer import render_book

    doc = ParsedDocument(
        blocks=[
            Block(BlockType.PARAGRAPH, " ".join(["تمهيد"] * 400)),
            Block(BlockType.BIO_MAN, "14 - الأفليلي"),
            Block(BlockType.PARAGRAPH, " ".join(["متن"] * 80)),
        ],
    )
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as output:
        out_path = output.name
    try:
        result = render_book(doc, out_path)
        heading_page = next(
            word["page"]
            for word in result["word_coordinates"]
            if word["block_index"] == 1
        )
        following_lines = {
            round(word["y"], 1)
            for word in result["word_coordinates"]
            if word["block_index"] == 2 and word["page"] == heading_page
        }
        assert len(following_lines) >= 3
    finally:
        os.unlink(out_path)


def test_attached_apparatus_reserves_space_on_its_page():
    fitz = pytest.importorskip("fitz")
    from versed.openiti_parser import Block, BlockType, ParsedDocument
    from versed.openiti_renderer import render_book

    doc = ParsedDocument(
        blocks=[
            Block(BlockType.PARAGRAPH, " ".join(["كلمة"] * 900)),
            Block(BlockType.APPARATUS_NOTE, "تنبيه: هذه ملاحظة تحريرية قصيرة."),
        ],
    )
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as output:
        out_path = output.name
    try:
        result = render_book(doc, out_path)
        with fitz.open(out_path) as pdf:
            note_page = next(
                page_number
                for page_number, page in enumerate(pdf, 1)
                if "تنبيه" in page.get_text()
            )
        body_bottom = max(
            word["y"] + word["height"]
            for word in result["word_coordinates"]
            if word["page"] == note_page
        )
        assert body_bottom < 754
    finally:
        os.unlink(out_path)


# ---------------------------------------------------------------------------
# Archive-gate invariants (C3/T3): text layer, word stream, apparatus, bounds.
# ---------------------------------------------------------------------------

import os
import re
import shutil
import subprocess
import sys
import unicodedata

# Diacritics (including line-final vowels), shadda, dagger alif, maddah
# above, hamza seats, alif wasla, lam-alef, brackets, guillemets and Arabic
# question mark; long enough to wrap over several lines.
ARABIC_FIXTURE = (
    "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ قَالَ ابْنُ سِينَا فِي الْمَسْأَلَةِ الْمُؤَخَّرَةِ "
    "لَا إِلَٰهَ إِلَّا اللَّهُ وَقَالَ ( عِبَارَةٌ ) «ثُمَّ» مَضَى؟ وَالسُّؤَالِ الْأَوَّلِ "
    "سُوٓءٍ أَإِنَّكَ ٱلْكِتَٰبُ وَتَأَخَّرَ الْقَوْلُ فِي ذٰلِكَ إِلَى آخِرِ الْبَابِ "
    "وَذَكَرَ أَهْلُ الْعِلْمِ أَنَّ هَٰذِهِ الْمَسْأَلَةَ مِنْ أُمَّهَاتِ الْمَسَائِلِ."
)
# Poppler moves the space before an Arabic comma or colon to after it (its
# bidi pass does not treat them as right-to-left), so this one is compared
# without whitespace.
ARABIC_PUNCTUATION_FIXTURE = "قَالَ الشَّيْخُ: لَا إِلَٰهَ إِلَّا اللَّهُ، وَحْدَهُ؛ أَلَيْسَ كَذَٰلِكَ؟ بَلَىٰ."

_BIDI_CONTROLS = dict.fromkeys(map(ord, "‎‏‪‫‬‭‮⁦⁧⁨⁩"))

_PDFKIT_SWIFT = r"""
import Foundation
import PDFKit
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let doc = PDFDocument(url: url) else { exit(2) }
var out = ""
for i in 0..<doc.pageCount { out += (doc.page(at: i)?.string ?? "") + "\n" }
FileHandle.standardOutput.write(out.data(using: .utf8)!)
"""


def _norm_ws(text):
    return " ".join(text.translate(_BIDI_CONTROLS).split())


def _render(doc, tmp_path, name="book.pdf", **kwargs):
    from versed.openiti_renderer import render_book

    out_path = str(tmp_path / name)
    return out_path, render_book(doc, out_path, **kwargs)


def _mupdf_text(path):
    fitz = pytest.importorskip("fitz")
    with fitz.open(path) as pdf:
        return "\n".join(page.get_text() for page in pdf)


def _poppler_text(path):
    if not shutil.which("pdftotext"):
        pytest.skip("poppler pdftotext is not installed")
    return subprocess.run(
        ["pdftotext", "-enc", "UTF-8", path, "-"],
        check=True, capture_output=True, text=True,
    ).stdout


def _pdfkit_text(path, tmp_path):
    if sys.platform != "darwin" or not shutil.which("swift"):
        pytest.skip("macOS PDFKit is not available")
    script = tmp_path / "pdfkit_text.swift"
    script.write_text(_PDFKIT_SWIFT)
    return subprocess.run(
        ["swift", str(script), path],
        check=True, capture_output=True, text=True, timeout=300,
    ).stdout


@pytest.mark.parametrize("extractor", ["mupdf", "poppler", "pdfkit"])
def test_text_layer_round_trips_arabic_on_vector_pages(tmp_path, extractor):
    fitz = pytest.importorskip("fitz")
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    doc = ParsedDocument(blocks=[Block(BlockType.PARAGRAPH, ARABIC_FIXTURE)])
    path, _ = _render(doc, tmp_path)

    with fitz.open(path) as pdf:
        for page in pdf:
            # The body stays the Cairo vector page: no page-sized raster.
            assert page.get_images() == []
            assert page.get_drawings() or page.get_text("rawdict")["blocks"]

    text = {
        "mupdf": lambda: _mupdf_text(path),
        "poppler": lambda: _poppler_text(path),
        "pdfkit": lambda: _pdfkit_text(path, tmp_path),
    }[extractor]()
    assert _norm_ws(ARABIC_FIXTURE) in _norm_ws(text)


@pytest.mark.parametrize("extractor", ["mupdf", "poppler", "pdfkit"])
def test_text_layer_keeps_arabic_punctuation_in_place(tmp_path, extractor):
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    doc = ParsedDocument(blocks=[Block(BlockType.PARAGRAPH, ARABIC_PUNCTUATION_FIXTURE)])
    path, _ = _render(doc, tmp_path)
    text = {
        "mupdf": lambda: _mupdf_text(path),
        "poppler": lambda: _poppler_text(path),
        "pdfkit": lambda: _pdfkit_text(path, tmp_path),
    }[extractor]()
    squeeze = lambda value: "".join(_norm_ws(value).split())
    assert squeeze(ARABIC_PUNCTUATION_FIXTURE) in squeeze(text)


def test_mupdf_search_finds_logical_arabic_phrase(tmp_path):
    fitz = pytest.importorskip("fitz")
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    doc = ParsedDocument(blocks=[Block(BlockType.PARAGRAPH, ARABIC_FIXTURE)])
    path, _ = _render(doc, tmp_path)
    with fitz.open(path) as pdf:
        assert pdf[0].search_for("الْمَسْأَلَةِ الْمُؤَخَّرَةِ")


def _filled_contours(path):
    """Closed contours of a Cairo path as rounded tuples (bare move_tos dropped)."""
    import cairo

    contours, current = [], []
    for kind, points in path:
        if kind == cairo.PathDataType.MOVE_TO and current:
            contours.append(current)
            current = []
        current.append((int(kind), tuple(round(value, 6) for value in points)))
    contours.append(current)
    return sorted(tuple(contour) for contour in contours if len(contour) > 1)


@pytest.mark.parametrize("justify", [False, True])
def test_glyph_placements_reproduce_layout_path_exactly(justify):
    """Per-glyph forms sit exactly where Pango's own outline path puts them."""
    cairo = pytest.importorskip("cairo")
    gi = pytest.importorskip("gi")
    from versed.openiti_renderer import (
        TATWEEL, _configure_pango_backend, _layout_glyph_placements, protect_ltr_runs,
    )

    _configure_pango_backend()
    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    surface = cairo.RecordingSurface(cairo.Content.COLOR_ALPHA, None)
    cr = cairo.Context(surface)
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription.from_string("Amiri 13"))
    layout.set_width(int(300 * Pango.SCALE))
    layout.set_wrap(Pango.WrapMode.WORD)
    layout.set_auto_dir(True)
    layout.set_justify(justify)
    kashida = f"قا{TATWEEL * 5}ل الله تعا{TATWEEL * 3}لى"
    layout.set_text(
        protect_ltr_runs(f"{ARABIC_FIXTURE} {kashida} سنة (681هـ/1282م)، abc ﴿الحمد لله﴾"), -1
    )

    origin_x, origin_y = 41.25, 73.5
    cr.move_to(origin_x, origin_y)
    PangoCairo.layout_path(cr, layout)
    expected = _filled_contours(cr.copy_path())
    cr.new_path()

    placements = _layout_glyph_placements(layout)
    assert placements
    for font, _, glyph, dx, dy in placements:
        cr.set_scaled_font(PangoCairo.Font.get_scaled_font(font))
        cr.glyph_path([cairo.Glyph(glyph, origin_x + dx, origin_y + dy)])
    assert _filled_contours(cr.copy_path()) == expected


def test_visible_glyphs_are_shared_forms_not_text_or_repeated_outlines(tmp_path):
    """Each glyph shape is stored once; pages hold only ``cm``/``Do`` references.

    1.3.0/1.3.1 filled a full outline per glyph occurrence (a 48-page book
    was 20 MB). The visible layer must also stay text-free, so the only
    extractable text is the semantic layer's.
    """
    fitz = pytest.importorskip("fitz")
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    blocks = [Block(BlockType.PARAGRAPH, ARABIC_FIXTURE) for _ in range(40)]
    path, _ = _render(ParsedDocument(blocks=blocks), tmp_path)

    curve = re.compile(rb"(?:^|\s)c(?:\s|$)")
    with fitz.open(path) as pdf:
        assert pdf.page_count >= 3
        forms = [
            xref for xref in range(1, pdf.xref_length())
            if "/Subtype/Form" in pdf.xref_object(xref, compressed=True)
        ]
        # A few hundred distinct glyph shapes at most, shared by every page.
        assert 0 < len(forms) < 400
        for page in pdf:
            content = page.read_contents()
            assert b" Do" in content
            assert not curve.search(content), "page repeats glyph outlines inline"
            # Only the invisible semantic layer's fonts: no Cairo font, no
            # Type 3 font, nothing in the visible layer that could be read.
            fonts = {font[4] for font in page.get_fonts(full=True)}
            assert fonts and all(name.startswith("VersedText") for name in fonts), fonts
        page_count = pdf.page_count
    assert os.path.getsize(path) < 40_000 * page_count


def _assert_words_are_source_tokens(coords, blocks):
    """Every drawn box names a source token, in source order."""
    tokens = [
        token
        for block in blocks
        for field in ("text", "hemistich_a", "hemistich_b", "isnad_text", "matn_text", "hukm_text")
        for token in (getattr(block, field, "") or "").split()
    ]
    cursor = 0
    for box in coords:
        while cursor < len(tokens) and tokens[cursor] != box["text"]:
            cursor += 1
        assert cursor < len(tokens), f"drawn word not in source: {box['text']!r}"
        cursor += 1


def test_word_stream_holds_only_source_words(tmp_path):
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    blocks = [
        Block(BlockType.BIO_MAN, "12 - إبراهيم النخعي"),
        Block(BlockType.PARAGRAPH, "كان فقيها من أهل الكوفة"),
        Block(BlockType.EDITORIAL_SECTION, "مقدمة المحقق"),
        Block(BlockType.ADMIN_DIVISION, "الشام", meta={"admin_type": "REG1"}),
        Block(BlockType.ROUTE, "ثلاثة أيام", meta={"route_type": "DIST"}),
        Block(BlockType.MORPHO_TAG, "", meta={"category": "fiqh"}),
        Block(BlockType.LACUNA, ""),
        Block(BlockType.DIC_NISBA, "3 - الكوفي نسبة إلى الكوفة"),
    ]
    doc = ParsedDocument(title="عنوان", author="مؤلف", blocks=blocks)
    _, result = _render(doc, tmp_path)

    coords = result["word_coordinates"]
    _assert_words_are_source_tokens(coords, blocks)
    texts = [box["text"] for box in coords]
    assert "◆" not in texts and "▸" not in texts
    assert "12" in texts and "إبراهيم" in texts and "3" in texts


def test_page_split_never_cuts_a_source_token_into_two_words(tmp_path):
    # 1370AhmadSamihKhalidi.MacahidMisriyya: Pango may wrap "(681هـ/1282م)،"
    # at the slash; joining split lines with "\n" turned it into two words.
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    tokens = []
    for index in range(600):
        tokens += ["الملك"] * (index % 5) + [f"(6{index % 90:02d}ه/12{index % 97:02d}م)،"]
    blocks = [Block(BlockType.PARAGRAPH, " ".join(tokens))]
    _, result = _render(ParsedDocument(blocks=blocks), tmp_path)

    coords = result["word_coordinates"]
    assert len({box["page"] for box in coords}) > 1
    assert [box["text"] for box in coords] == tokens
    assert [box["word_index"] for box in coords] == list(range(len(tokens)))


def test_word_stream_and_text_layer_carry_no_synthetic_kashida(tmp_path):
    from versed.openiti_parser import Block, BlockType, ParsedDocument
    from versed.openiti_renderer import TATWEEL

    # Literary theme justifies with kashida; source "هـ" keeps its tatweel.
    text = " ".join(["قال الله تعالى في كتابه العزيز سنة 681هـ"] * 60)
    blocks = [Block(BlockType.QURAN_CITATION, text)]
    path, result = _render(ParsedDocument(blocks=blocks), tmp_path, theme_name="literary")

    coords = result["word_coordinates"]
    assert [box["text"] for box in coords] == text.split()
    layer = _mupdf_text(path)
    assert layer.count(TATWEEL) == text.count(TATWEEL)


def test_huge_apparatus_note_loses_no_source_text(tmp_path):
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    letters = "بتثجحخدذرزسشصضطظعغفقكلمنهوي"
    words = [a + b + c for a in letters[:12] for b in letters[:12] for c in letters[:12]][:1500]
    note = "تنبيه: " + " ".join(words)
    blocks = [
        Block(BlockType.PARAGRAPH, " ".join(["متن"] * 200)),
        Block(BlockType.APPARATUS_NOTE, note),
        Block(BlockType.PARAGRAPH, "خاتمة الكتاب"),
    ]
    path, _ = _render(ParsedDocument(blocks=blocks), tmp_path)

    layer = _mupdf_text(path)
    extracted = layer.split()
    assert "..." not in layer and "…" not in layer
    for word in words:
        assert extracted.count(word) == 1, word


def test_paragraph_taller_than_a_page_stays_inside_the_body_area(tmp_path):
    # Released 1.2.6 drew a paragraph taller than one page past the bottom
    # margin; it must flow onto following pages instead.
    fitz = pytest.importorskip("fitz")
    from versed.openiti_parser import Block, BlockType, ParsedDocument
    from versed.openiti_renderer import THEMES

    theme = THEMES["scholarly"]
    words = [f"كلمة{chr(0x0628 + index % 20)}" for index in range(2500)]
    blocks = [Block(BlockType.PARAGRAPH, " ".join(words))]
    path, result = _render(ParsedDocument(blocks=blocks), tmp_path)

    coords = result["word_coordinates"]
    assert len(coords) == len(words)
    with fitz.open(path) as pdf:
        assert pdf.page_count >= 3
        for box in coords:
            assert box["page"] - 1 < pdf.page_count
            assert box["y"] + box["height"] <= theme.page_h - theme.margin_bottom + 0.5


def test_page_split_chunks_do_not_rewrap_past_the_bottom_margin(tmp_path):
    # 0983IbnMuhammadSahgirAkhdari.MukhtasarFiCibadat: lines with " ، " re-wrap
    # when a page chunk is laid out again, so a 28-line chunk drew 39 lines
    # and ran off the page (main and 1.2.6 alike).
    from versed.openiti_parser import Block, BlockType, ParsedDocument
    from versed.openiti_renderer import THEMES

    theme = THEMES["scholarly"]
    import random

    vocabulary = (
        "ساهيا أو عامدا ، ولا يضحك في صلاته إلا غافل متلاعب والمؤمن إذا قام "
        "للصلاة أعرض بقلبه وعظمته ويرتعد قلبه وترهب نفسه من هيبة الله جل جلاله "
        "فهذه قليلا ثم تيقن الطهارة فلا شيء عليه ومن التفت"
    ).split()
    rng = random.Random(2)  # a seed that overflowed before the fix
    words = [rng.choice(vocabulary) for _ in range(1200)]
    _, result = _render(ParsedDocument(blocks=[Block(BlockType.PARAGRAPH, " ".join(words))]), tmp_path)

    coords = result["word_coordinates"]
    assert [box["text"] for box in coords] == words
    for box in coords:
        assert box["y"] + box["height"] <= theme.page_h - theme.margin_bottom + 0.5
    pages = sorted({box["page"] for box in coords})
    assert pages == list(range(pages[0], pages[-1] + 1)), "a split left an empty page"


# Mixed-direction lines. The text layer stores UAX #9 visual order of the
# isolate-free text, so readers that re-run bidi on the glyph stream (PDFKit)
# round-trip exactly. Poppler and MuPDF use their own reordering; the cases
# they cannot satisfy are marked xfail with what they return (a Chrome-printed
# PDF of the same text extracts the same way in both).
MIXED_FIXTURES = {
    "paren_footnote": "قَالَ ابْنُ سِينَا (2) فِي كِتَابِهِ",
    "western_digits": "مَاتَ سَنَةَ 681 بِدِمَشْقَ",
    "indic_digits": "مَاتَ سَنَةَ ٦٨١ بِدِمَشْقَ",
    "hijri_year": "تُوُفِّيَ سَنَةَ 902هـ بِالْقَاهِرَةِ",
    "latin_title": "وَقَرَأَ كِتَابَ The Canon of Medicine عَلَى شَيْخِهِ",
    "comma_after_digit": "فِي الْجُزْءِ 3، الصَّفْحَةِ ١٢، وَغَيْرِهَا",
}

_POPPLER_EXACT = {"hijri_year"}
# Poppler's RTL dump moves the space beside a number to its other side.
_POPPLER_SPACING_ONLY = {"western_digits", "indic_digits"}


def _mixed_text(extractor, fixture, tmp_path):
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    doc = ParsedDocument(blocks=[Block(BlockType.PARAGRAPH, MIXED_FIXTURES[fixture])])
    path, _ = _render(doc, tmp_path)
    return {
        "mupdf": lambda: _mupdf_text(path),
        "poppler": lambda: _poppler_text(path),
        "pdfkit": lambda: _pdfkit_text(path, tmp_path),
    }[extractor]()


@pytest.mark.parametrize("fixture", sorted(MIXED_FIXTURES))
def test_pdfkit_round_trips_digits_brackets_and_latin_in_arabic(tmp_path, fixture):
    text = _mixed_text("pdfkit", fixture, tmp_path)
    assert _norm_ws(MIXED_FIXTURES[fixture]) in _norm_ws(text)


@pytest.mark.parametrize("fixture", sorted(MIXED_FIXTURES))
def test_poppler_mixed_direction_lines(tmp_path, fixture, request):
    text = _mixed_text("poppler", fixture, tmp_path)
    source = MIXED_FIXTURES[fixture]
    if fixture in _POPPLER_EXACT:
        assert _norm_ws(source) in _norm_ws(text)
    elif fixture in _POPPLER_SPACING_ONLY:
        squeeze = lambda value: "".join(_norm_ws(value).split())
        assert squeeze(source) in squeeze(text)
    else:
        request.node.add_marker(pytest.mark.xfail(reason="Poppler reorders brackets/marks next to LTR runs"))
        assert _norm_ws(source) in _norm_ws(text)


def test_render_fails_loudly_when_the_body_font_is_substituted(tmp_path, monkeypatch):
    # This Mac rendered "Amiri" with AlNile / DecoType Naskh for months because
    # fontconfig had no Amiri; the renderer must refuse instead.
    from versed.openiti_parser import Block, BlockType, ParsedDocument
    from versed import openiti_renderer

    theme = openiti_renderer.BookTheme(name="missing", font_body="Versed No Such Face")
    monkeypatch.setitem(openiti_renderer.THEMES, "missing_face", theme)
    doc = ParsedDocument(blocks=[Block(BlockType.PARAGRAPH, "بسم الله الرحمن الرحيم")])
    with pytest.raises(RuntimeError, match="Versed No Such Face"):
        _render(doc, tmp_path, theme_name="missing_face")


def test_bundled_themes_resolve_their_requested_faces():
    from versed.openiti_renderer import THEMES, _resolved_font_family

    for theme in THEMES.values():
        for family in {theme.font_body, theme.font_heading}:
            assert _resolved_font_family(family).lower() == family.lower()


def test_verse_numbers_and_page_markers_use_opposite_margins(tmp_path, monkeypatch):
    # 0466IbnSinanKhafaji.Diwan: "(١٢)" was drawn over "[ص ١٦٧]".
    from versed import openiti_renderer
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    captured = {}
    original = openiti_renderer._attach_semantic_text_layer

    def capture(out_path, page_text):
        captured.update(page_text)
        return original(out_path, page_text)

    monkeypatch.setattr(openiti_renderer, "_attach_semantic_text_layer", capture)
    blocks = []
    for number in range(1, 80):
        blocks.append(Block(BlockType.PAGE_REF, "", meta={"vol": 1, "page": number}))
        blocks.append(Block(
            BlockType.VERSE_PAIR, "", hemistich_a="قفا نبك من ذكرى حبيب ومنزل",
            hemistich_b="بسقط اللوى بين الدخول فحومل", meta={"verse_number": str(number)},
        ))
    _render(ParsedDocument(blocks=blocks), tmp_path)

    def boxes(lines, test):
        found = []
        for runs, x, baseline, width, font_size in lines:
            text = "".join(char for _, run in runs for char, _ in run)
            if test(text):
                found.append((x, baseline - font_size, x + width, baseline))
        return found

    checked = 0
    for lines in captured.values():
        refs = boxes(lines, lambda text: "ص" in text)
        numbers = boxes(lines, lambda text: "(" in text and "ص" not in text)
        for ref in refs:
            for number in numbers:
                checked += 1
                overlap = (
                    min(ref[2], number[2]) > max(ref[0], number[0])
                    and min(ref[3], number[3]) > max(ref[1], number[1])
                )
                assert not overlap, (ref, number)
    assert checked


def _extract(extractor, path, tmp_path):
    return {
        "mupdf": lambda: _mupdf_text(path),
        "poppler": lambda: _poppler_text(path),
        "pdfkit": lambda: _pdfkit_text(path, tmp_path),
    }[extractor]()


def _ink_in_box(pixmap, box, scale):
    x0, y0 = max(0, int(box["x"] * scale)), max(0, int(box["y"] * scale))
    x1 = min(pixmap.width, int((box["x"] + box["width"]) * scale) + 1)
    y1 = min(pixmap.height, int((box["y"] + box["height"]) * scale) + 1)
    samples, stride = pixmap.samples, pixmap.stride
    return sum(
        1 for yy in range(y0, y1) for xx in range(x0, x1) if samples[yy * stride + xx] < 110
    )


def test_verse_pairs_box_every_hemistich_word_in_reading_order(tmp_path):
    # 0466IbnSinanKhafaji.Diwan: verse was drawn without boxes, so only
    # 55/1,607 timed words had a place on the page.
    fitz = pytest.importorskip("fitz")
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    pairs = [
        ("قفا نبك من ذكرى حبيب ومنزل", "بسقط اللوى بين الدخول فحومل"),
        ("فتوضح فالمقراة لم يعف رسمها", "لما نسجتها من جنوب وشمأل"),
    ] * 30
    blocks = [Block(BlockType.PARAGRAPH, "قال الشاعر")]
    for number, (a, b) in enumerate(pairs, 1):
        blocks.append(Block(
            BlockType.VERSE_PAIR, "", hemistich_a=a, hemistich_b=b,
            meta={"verse_number": str(number)},
        ))
    path, result = _render(ParsedDocument(blocks=blocks), tmp_path)
    coords = result["word_coordinates"]

    # Every hemistich word, A before B, numbered across the block.
    expected = ["قال", "الشاعر"] + [word for a, b in pairs for word in (a + " " + b).split()]
    assert [box["text"] for box in coords] == expected
    _assert_words_are_source_tokens(coords, blocks)
    for index, (a, b) in enumerate(pairs, 1):
        verse = [box for box in coords if box["block_index"] == index]
        n_a = len(a.split())
        assert [box["word_index"] for box in verse] == list(range(n_a + len(b.split())))
        # Hemistich A is the right-hand column, B the left-hand one, and
        # within each the words run right to left.
        a_boxes, b_boxes = verse[:n_a], verse[n_a:]
        assert min(box["x"] for box in a_boxes) > max(box["x"] + box["width"] for box in b_boxes)
        for column in (a_boxes, b_boxes):
            xs = [box["x"] for box in column]
            assert xs == sorted(xs, reverse=True)
    assert len({box["page"] for box in coords}) > 1

    scale = 2.0
    with fitz.open(path) as pdf:
        pixmaps = {}
        for box in coords:
            page = box["page"] - 1  # no front matter: page numbers start at 1
            if page not in pixmaps:
                pixmaps[page] = pdf[page].get_pixmap(
                    matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False
                )
            assert _ink_in_box(pixmaps[page], box, scale) > 10, box


COVER_TITLE = "السر المكتوم في الفرق بين المالين المحمود والمذموم"
COVER_AUTHOR = "السخاوي"


def _cover_renderer(calls):
    def render_cover(cr, width, height, metadata, style, paint_layout=None):
        import gi

        gi.require_version("Pango", "1.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Pango, PangoCairo

        calls.append(paint_layout)
        y = 200.0
        for text, size, spacing in (
            (metadata["title_ar"], 26, 0),
            (metadata["author_ar"], 16, 0),
            (metadata["author_en"].upper(), 9, 3000),
        ):
            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(Pango.FontDescription.from_string(f"Amiri {size}"))
            layout.set_width(int((width - 72) * Pango.SCALE))
            layout.set_alignment(Pango.Alignment.CENTER)
            layout.set_wrap(Pango.WrapMode.WORD)
            if spacing:
                attrs = Pango.AttrList()
                attrs.insert(Pango.attr_letter_spacing_new(spacing))
                layout.set_attributes(attrs)
            layout.set_text(text, -1)
            cr.set_source_rgb(0.2, 0.1, 0.05)
            cr.move_to(36, y)
            if paint_layout is None:
                PangoCairo.show_layout(cr, layout)
            else:
                paint_layout(layout)
            y += layout.get_pixel_extents()[1].height + 20

    return render_cover


@pytest.mark.parametrize("extractor", ["mupdf", "poppler", "pdfkit"])
def test_cover_text_copies_as_logical_text(tmp_path, extractor):
    # Cairo's own cover text copied as visual-order Arabic ("يواخسلا") and
    # letter-spaced Latin as "S AK H AW I".
    fitz = pytest.importorskip("fitz")
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    calls = []
    path, _ = _render(
        ParsedDocument(blocks=[Block(BlockType.PARAGRAPH, "بسم الله الرحمن الرحيم")]),
        tmp_path,
        cover_metadata={"title_ar": COVER_TITLE, "author_ar": COVER_AUTHOR, "author_en": "Sakhawi"},
        cover_renderer=_cover_renderer(calls),
    )
    assert calls and callable(calls[0])
    with fitz.open(path) as pdf:
        cover = pdf[0]
        # Drawn glyphs are outlines: the only text is the invisible layer.
        fonts = {font[4] for font in cover.get_fonts(full=True)}
        assert fonts and all(name.startswith("VersedText") for name in fonts), fonts
        cover_text = cover.get_text() if extractor == "mupdf" else None

    text = cover_text if extractor == "mupdf" else _extract(extractor, path, tmp_path)
    cover_part = text.split("بسم الله")[0]
    flat = _norm_ws(cover_part)
    assert _norm_ws(COVER_TITLE) in flat
    assert COVER_AUTHOR in flat
    assert "SAKHAWI" in flat


def test_cover_renderer_without_the_hook_is_still_called(tmp_path):
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    calls = []

    def legacy(cr, width, height, metadata, style):
        calls.append(style)

    _, result = _render(
        ParsedDocument(blocks=[Block(BlockType.PARAGRAPH, "بسم الله")]),
        tmp_path,
        cover_metadata={"title_ar": "عنوان"},
        cover_renderer=legacy,
    )
    assert calls == ["auto"] and result["pages"] == 1


# 0902Sakhawi.SirrMaktum p.1: an undiacritized paragraph, a marginal page
# marker, then a fully diacritized paragraph. PDFKit spliced the last line of
# the first paragraph, the marker and the next line into one.
_PLAIN_PARAGRAPH = (
    "في «رسالة منسوبة للحسن البصري» رحمه الله في الفريضة السابعة مما يجب على المؤمن من "
    "الفرائض في اليوم والليلة وهو أن النبي صلى الله عليه وسلم قال «اللهم من أحبني فارزقه "
    "الكفاف ومن أبغضني فأكثر ماله وولده»"
)
_VOCALIZED_PARAGRAPH = (
    "أَهُوَ صَحِيحٌ أَمْ لَا؟ وَبِمَاذَا يُجْمَعُ بِهِ بَيْنَهُ وَبَيْنَ دُعَائِهِ صَلَّى اللَّهُ عَلَيْهِ "
    "وَسَلَّمَ لِخَادِمِهِ سَيِّدِنَا أَنَسِ بْنِ مَالِكٍ رَضِيَ اللَّهُ عَنْهُ حَسْبَمَا اتَّفَقَ عَلَيْهِ "
    "الشَّيْخَانِ بِكَثْرَةِ الْمَالِ وَالْوَلَدِ فَقُلْتُ أَمَّا الْحَدِيثُ فَقَدْ أَخْبَرَتْنِي بِهِ "
    "خَاتِمَةُ مُسْنَدِي مِصْرَ أُمُّ مُحَمَّدٍ ابْنَةُ عُمَرَ ابْنُ الْعِزِّ بْنِ جَمَاعَةَ"
)


@pytest.mark.parametrize("extractor", ["mupdf", "poppler", "pdfkit"])
def test_each_drawn_line_extracts_as_its_own_line_in_order(tmp_path, monkeypatch, extractor):
    from versed import openiti_renderer
    from versed.openiti_parser import Block, BlockType, ParsedDocument

    captured = {}
    original = openiti_renderer._attach_semantic_text_layer

    def capture(out_path, page_text):
        captured.update(page_text)
        return original(out_path, page_text)

    monkeypatch.setattr(openiti_renderer, "_attach_semantic_text_layer", capture)
    blocks = [
        Block(BlockType.PARAGRAPH, _PLAIN_PARAGRAPH),
        Block(BlockType.PAGE_REF, "", meta={"vol": 1, "page": 62}),
        Block(BlockType.PARAGRAPH, _VOCALIZED_PARAGRAPH),
        Block(BlockType.PAGE_REF, "", meta={"vol": 1, "page": 63}),
        Block(BlockType.PARAGRAPH, _PLAIN_PARAGRAPH),
    ]
    path, _ = _render(ParsedDocument(blocks=blocks), tmp_path)

    squeeze = lambda value: "".join(_norm_ws(value).split())
    body_lines = []
    for runs, *_ in captured[0]:
        chars = sorted((offset, char) for _, run in runs for char, offset in run if offset >= 0)
        line = "".join(char for _, char in chars)
        if "ص" in line and "[" in line:
            continue  # the marginal page marker
        body_lines.append(squeeze(line))
    assert len(body_lines) >= 8

    out_lines = [squeeze(line) for line in _extract(extractor, path, tmp_path).splitlines()]
    positions = []
    for line in body_lines:
        assert line in out_lines, (line, out_lines)
        positions.append(out_lines.index(line, positions[-1] + 1 if positions else 0))
    assert positions == sorted(positions)
