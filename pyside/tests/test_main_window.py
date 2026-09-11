from pathlib import Path

from app.models.captions import CaptionSegment
from app.views.main_window import MainWindow


def test_main_window_init(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle().startswith("CapSlap")
    assert window.player is not None
    assert window.core is not None
    assert window.overlay is not None
    assert window.timeline is not None
    assert window.caption_panel is not None
    window.close()


def test_main_window_load_1080p_video(qtbot):
    sample = str(Path("../rust/bin/test_input.mp4").resolve())
    assert Path(sample).exists(), "Sample 1080p video must exist"

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    window.load_video(sample)
    assert window.thumb_btn.isEnabled()
    assert "test_input.mp4" in window.meta_lbl.text()

    # Test seek
    window.player.seek_to_ms(2000)
    assert window.player.slider.value() >= 0

    window.close()


def test_main_window_caption_sync(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    seg1 = CaptionSegment(start_ms=1000, end_ms=3000, text="Synchronized cue")
    window.set_caption_segments([seg1])

    assert len(window.timeline.segments) == 1
    assert len(window.caption_panel.segments) == 1
    assert window.caption_panel.cue_table.rowCount() == 1

    # Simulate playhead moving inside seg1 (pos = 2000)
    window._on_position_changed(2000)
    assert window.overlay.current_segment == seg1

    # Simulate moving outside seg1 (pos = 4000)
    window._on_position_changed(4000)
    assert window.overlay.current_segment is None

    # Test dragging overlay anchor
    window.overlay.set_segment(seg1, 80.0)
    window._on_overlay_anchor_changed(45.0)
    assert window.project.get_anchor_y_for_segment(seg1) == 45.0
    assert window.caption_panel.slider_anchor.value() == 45

    window.close()
