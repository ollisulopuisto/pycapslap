from pathlib import Path

from app.views import tile_buttons


def test_the_chevron_file_is_written_once(qtbot):
    tile_buttons.chevron_url.cache_clear()
    path = Path(tile_buttons.chevron_url())
    assert path.is_file() and path.stat().st_size > 0
    stamp = path.stat().st_mtime_ns

    # A later start finds the file and leaves it alone.
    tile_buttons.chevron_url.cache_clear()
    assert Path(tile_buttons.chevron_url()) == path
    assert path.stat().st_mtime_ns == stamp


def test_icons_carry_every_mode(qtbot):
    icon = tile_buttons.icon("plus")
    assert not icon.isNull()
    assert icon.availableSizes(icon.Mode.Active) == icon.availableSizes(
        icon.Mode.Selected
    )
    assert icon.availableSizes(icon.Mode.Disabled)
