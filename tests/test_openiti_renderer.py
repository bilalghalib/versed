from versed import OPENITI_THEMES, OpenITIBookTheme, render_openiti_book


def test_openiti_renderer_exports():
    assert callable(render_openiti_book)
    assert "scholarly" in OPENITI_THEMES
    assert isinstance(OPENITI_THEMES["scholarly"], OpenITIBookTheme)
