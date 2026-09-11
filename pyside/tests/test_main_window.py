from pathlib import Path

from app.models.captions import CaptionSegment
from app.views.main_window import MainWindow


def test_main_window_init(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle().startswith("PyCapSlap")
    assert window.player is not None
    assert window.core is not None
    assert window.overlay is not None
    assert window.timeline is not None
    assert window.caption_panel is not None
    assert window.save_btn is not None
    assert window.render_btn is not None
    assert "Render" in window.render_btn.text()
    window.close()


def test_main_window_load_1080p_video(qtbot):
    repo_root = Path(__file__).resolve().parents[2]
    sample = str((repo_root / "rust" / "bin" / "test_input.mp4").resolve())
    assert Path(sample).exists(), "Sample 1080p video must exist"

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    window.load_video(sample)
    assert window.thumb_btn.isEnabled()
    assert window.render_btn.isEnabled()
    assert window.save_btn.isEnabled()
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


def test_main_window_save_action(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)

    temp_video = tmp_path / "dummy.mp4"
    temp_video.write_bytes(b"dummy")

    window.load_video(str(temp_video))
    seg = CaptionSegment(start_ms=0, end_ms=1000, text="Saved test")
    window.set_caption_segments([seg])

    window.save_btn.click()

    expected_sidecar = tmp_path / "dummy.mp4.capslap.json"
    assert expected_sidecar.exists()
    assert "Saved test" in expected_sidecar.read_text()
    window.close()
