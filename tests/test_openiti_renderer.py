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
