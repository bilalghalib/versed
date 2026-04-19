from versed import OPENITI_THEMES, OpenITIBookTheme, render_openiti_book


def test_openiti_renderer_exports():
    assert callable(render_openiti_book)
    assert "scholarly" in OPENITI_THEMES
    assert isinstance(OPENITI_THEMES["scholarly"], OpenITIBookTheme)


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
        assert len(coords) == 4, f"Expected 4 words, got {len(coords)}"
        for wc in coords:
            assert "text" in wc
            assert "x" in wc and "y" in wc
            assert "width" in wc and "height" in wc
            assert "page" in wc
            assert wc["width"] > 0 and wc["height"] > 0
    finally:
        os.unlink(out_path)
