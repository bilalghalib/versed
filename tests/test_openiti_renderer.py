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
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        out_path = f.name
    try:
        result = render_book(doc, out_path)
        assert "word_coordinates" in result, "render_book must return word_coordinates"
        coords = result["word_coordinates"]
        # Filter to content pages (page > 0, cover is page 0)
        content_coords = [wc for wc in coords if wc["page"] > 0]
        assert len(content_coords) == 4, f"Expected 4 Arabic words, got {len(content_coords)}"
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


def test_short_paragraph_moves_whole_to_next_page():
    from versed.openiti_parser import Block, BlockType, ParsedDocument
    from versed.openiti_renderer import render_book

    doc = ParsedDocument(
        blocks=[
            Block(BlockType.PARAGRAPH, " ".join(["كلمة"] * 380)),
            Block(BlockType.PARAGRAPH, " ".join(["قصير"] * 50)),
        ],
    )
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as output:
        out_path = output.name
    try:
        result = render_book(doc, out_path)
        second_paragraph = [
            word
            for word in result["word_coordinates"]
            if word["block_index"] == 1
        ]
        assert len(second_paragraph) == 50
        assert {word["page"] for word in second_paragraph} == {2}
    finally:
        os.unlink(out_path)
