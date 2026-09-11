from app.fonts import init_app_fonts


def test_init_app_fonts(qapp):
    fonts = init_app_fonts()
    assert isinstance(fonts, list)
    assert len(fonts) > 0
    # Must contain key app fonts
    assert any("Montserrat" in f for f in fonts)
    assert any("Komika" in f for f in fonts)
