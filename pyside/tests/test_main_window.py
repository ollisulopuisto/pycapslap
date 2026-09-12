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
    qtbot.waitUntil(lambda: window.thumb_btn.isEnabled(), timeout=5000)
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


def test_main_window_style_selection_and_sidecar(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)

    temp_video = tmp_path / "styled.mp4"
    temp_video.write_bytes(b"dummy")

    window.load_video(str(temp_video))

    # Switch template to karaoke
    idx = window.caption_panel.combo_template.findData("karaoke")
    window.caption_panel.combo_template.setCurrentIndex(idx)

    assert window.project.style.karaoke is True
    assert window.player.canvas.style.karaoke is True

    # Save and verify style in sidecar
    window.save_btn.click()
    sidecar = tmp_path / "styled.mp4.capslap.json"
    assert sidecar.exists()
    content = sidecar.read_text()
    assert "karaoke" in content
    window.close()


def test_main_window_clean_sidebar_layout(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    # The right sidebar widget should contain caption_panel as its primary child
    # and should NOT contain meta_box, thumb_box, or perf_box in its visible layout
    right_widget = window.caption_panel.parentWidget()
    assert right_widget is not None
    layout = right_widget.layout()
    assert layout is not None

    # Verify only caption_panel is added to the layout
    layout_widgets = [
        layout.itemAt(i).widget()
        for i in range(layout.count())
        if layout.itemAt(i).widget() is not None
    ]
    assert layout_widgets == [window.caption_panel]

    # Check that style section in caption panel starts collapsed
    assert not window.caption_panel.style_content.isVisible()
    window.close()


def test_main_window_core_progress_signal(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    # Normal progress event
    window._on_core_progress("op-render-12345", "Exporting...", 0.45)
    assert "45%" in window.status.currentMessage()
    assert "Exporting..." in window.status.currentMessage()

    # Inverted arguments safeguard
    window._on_core_progress("op-render-12345", 0.75, "Encoding...")
    assert "75%" in window.status.currentMessage()
    assert "Encoding..." in window.status.currentMessage()

    # String / invalid progress safeguard
    window._on_core_progress("op-render-12345", "Analyzing frames", "invalid")
    assert "Analyzing frames" in window.status.currentMessage()

    # Active render button text update
    window.render_btn.setEnabled(False)
    window.render_btn.setText("Rendering...")
    window._on_core_progress("op-render-12345", "Exporting...", 0.88)
    assert "88%" in window.render_btn.text()

    window.close()


def test_main_window_progress_bar_and_empty_segments_on_load(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert hasattr(window, "progress_bar")
    assert not window.progress_bar.isVisible()

    temp_video = tmp_path / "fresh_video.mp4"
    temp_video.write_bytes(b"dummy")

    window.load_video(str(temp_video))
    # Fresh video with no sidecar must start with clean empty segments!
    assert window.project.segments == []
    assert window.caption_panel.segments == []
    window.close()


def test_main_window_transcribe_params(qtbot, tmp_path):
    temp_video = tmp_path / "video.mp4"
    temp_video.write_bytes(b"dummy")

    called_method = None
    called_params = None

    from PySide6.QtCore import QObject, Signal

    class MockCore(QObject):
        progress = Signal(str, str, float)

        def call(self, method, params):
            nonlocal called_method, called_params
            called_method = method
            called_params = params
            from concurrent.futures import Future

            f = Future()
            f.set_result({"transcription": {"segments": []}})
            return f

        def close(self):
            pass

    window = MainWindow(core_client=MockCore())
    qtbot.addWidget(window)
    window.load_video(str(temp_video))

    window._on_transcribe_requested()
    assert called_method == "transcribe"
    assert "exportFormats" in called_params
    assert isinstance(called_params["exportFormats"], list)
    window.close()
