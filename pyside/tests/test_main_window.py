from pathlib import Path

import pytest

from app.models.captions import CaptionSegment
from app.views.main_window import MainWindow


def _make_video_file(path: Path) -> str:
    path.write_bytes(b"dummy")
    return str(path)


# The two tests below (load a "video" — real or garbage, tried both — into a
# real MainWindow, then QPushButton.click() the save button) hang
# indefinitely under pytest specifically: the exact same sequence in a bare
# script (no pytest, no qtbot) completes in well under a second, every time.
# Even running just one of these two tests alone under pytest (not the full
# suite, no other MainWindow created first) reproduces the hang, so it isn't
# cross-test state or CI-only either — something about pytest-qt's fixture
# machinery plus this specific load-then-click sequence. See
# CONTRIBUTING.md for what's been ruled out. Skipped unconditionally until
# someone gets to the bottom of it.
_skip_hangs = pytest.mark.skip(
    reason="hangs under pytest — see CONTRIBUTING.md",
)


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


@_skip_hangs
def test_main_window_save_action(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)

    temp_video = tmp_path / "dummy.mp4"
    _make_video_file(temp_video)

    window.load_video(str(temp_video))
    seg = CaptionSegment(start_ms=0, end_ms=1000, text="Saved test")
    window.set_caption_segments([seg])

    window.save_btn.click()

    expected_sidecar = tmp_path / "dummy.mp4.capslap.json"
    assert expected_sidecar.exists()
    assert "Saved test" in expected_sidecar.read_text()
    window.close()


@_skip_hangs
def test_main_window_style_selection_and_sidecar(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)

    temp_video = tmp_path / "styled.mp4"
    _make_video_file(temp_video)

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
    _make_video_file(temp_video)

    window.load_video(str(temp_video))
    # Fresh video with no sidecar must start with clean empty segments!
    assert window.project.segments == []
    assert window.caption_panel.segments == []
    window.close()


def test_main_window_transcribe_params(qtbot, tmp_path):
    temp_video = tmp_path / "video.mp4"
    _make_video_file(temp_video)

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


def test_preview_layout_reaches_canvas_from_reader_thread(qtbot):
    """The core answers on its own reader thread, not the GUI thread.

    The layout has to be handed over with a thread hop that actually fires
    there; when it doesn't, the canvas silently keeps drawing its stand-in
    layout — one flowing line, no karaoke highlight — no matter what the
    style panel says.
    """
    import threading
    import time
    from concurrent.futures import Future

    from PySide6.QtCore import QObject, Signal

    cue = {
        "startMs": 0,
        "endMs": 2000,
        "lines": [
            {"words": [{"text": "JA", "isHighlighted": True}], "fontSizePx": 44},
            {"words": [{"text": "SITTEN", "isHighlighted": False}], "fontSizePx": 52},
        ],
        "yPct": 88.0,
        "anchor": "bottom",
    }

    class MockCore(QObject):
        progress = Signal(str, str, float)
        proc = None  # the telemetry timer looks for one

        def call(self, method, params):
            f: Future = Future()
            if method == "previewLayout":
                # Answer with a beat's delay so the caller has attached its
                # callback first: a Future that is already done runs the
                # callback inline on the GUI thread, and the test would pass
                # without ever crossing a thread boundary.
                def answer():
                    time.sleep(0.05)
                    f.set_result({"cues": [cue]})

                threading.Thread(target=answer, daemon=True).start()
            else:
                f.set_result({})
            return f

        def close(self):
            pass

    window = MainWindow(core_client=MockCore())
    qtbot.addWidget(window)
    window.set_caption_segments(
        [CaptionSegment(start_ms=0, end_ms=2000, text="Ja sitten")]
    )
    # Only the explicit call below should reach the mock; the debounced
    # refresh set_caption_segments queued would answer on the GUI thread.
    window._layout_timer.stop()
    window._request_preview_layout()

    qtbot.waitUntil(lambda: window._preview_cues == [cue], timeout=2000)
    assert window.overlay.layout_cue == cue
    window.close()


def _mock_core_with_layer(cue, layer_png):
    """A core that answers previewLayout with `cue` and hands back `layer_png`."""
    import threading
    import time
    from concurrent.futures import Future

    from PySide6.QtCore import QObject, Signal

    calls: list[tuple[str, dict]] = []

    class MockCore(QObject):
        progress = Signal(str, str, float)
        proc = None

        def call(self, method, params):
            calls.append((method, params))
            f: Future = Future()
            if method == "previewLayout":

                def answer():
                    time.sleep(0.05)
                    f.set_result({"cues": [cue]})

                threading.Thread(target=answer, daemon=True).start()
            elif method == "generatePreviewFrame":

                def answer_frame():
                    time.sleep(0.05)
                    f.set_result({"imageData": "data:image/png;base64," + layer_png})

                threading.Thread(target=answer_frame, daemon=True).start()
            else:
                f.set_result({})
            return f

        def close(self):
            pass

    return MockCore(), calls


def test_caption_layer_is_fetched_and_cached_per_cue(qtbot):
    """The preview shows libass's pixels, and asks for each cue only once."""
    import base64

    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage

    img = QImage(8, 8, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 255, 0, 255))
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    png_b64 = base64.b64encode(bytes(buf.data())).decode()

    cue = {
        "startMs": 0,
        "endMs": 2000,
        "lines": [{"words": [{"text": "JA", "isHighlighted": True}], "fontSizePx": 44}],
        "yPct": 88.0,
        "anchor": "bottom",
    }
    core, calls = _mock_core_with_layer(cue, png_b64)

    window = MainWindow(core_client=core)
    qtbot.addWidget(window)
    from app.models.captions import VideoMetadata

    window.project.video = VideoMetadata(
        path="/tmp/does-not-need-to-exist.mp4", width=1080, height=1920
    )
    window.set_caption_segments(
        [CaptionSegment(start_ms=0, end_ms=2000, text="Ja sitten")]
    )
    window._layout_timer.stop()
    window._request_preview_layout()

    qtbot.waitUntil(lambda: window.overlay.caption_layer is not None, timeout=3000)

    frame_calls = [c for c in calls if c[0] == "generatePreviewFrame"]
    assert len(frame_calls) == 1
    params = frame_calls[0][1]
    assert params["renderMode"] == "captions"
    assert params["exportFormat"] == "source"
    # Rendered past the karaoke pop, inside the cue.
    assert cue["startMs"] <= params["timestampMs"] < cue["endMs"]

    # Same cue again: served from cache, no second render.
    window._apply_preview_layout()
    assert len([c for c in calls if c[0] == "generatePreviewFrame"]) == 1

    # A style change invalidates every rendered cue.
    window._invalidate_caption_layers()
    assert window.overlay.caption_layer is None
    assert window._layer_cache == {}
    window.close()


def test_block_prefetch_renders_every_karaoke_window_once(qtbot):
    """One window on screen pulls in the whole block, a few renders at a time.

    Karaoke shows a caption one word at a time; without this, playback would
    fall back to the painted approximation for every window the user has not
    stopped on.
    """
    import base64

    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage

    img = QImage(4, 4, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 255, 0, 255))
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    png_b64 = base64.b64encode(bytes(buf.data())).decode()

    words = ["JA", "SITTEN", "ON", "ERIKSEEN", "KANNETTAVA", "TIETOKONE"]
    cues = [
        {
            "startMs": i * 300,
            "endMs": (i + 1) * 300,
            "lines": [
                {
                    "words": [{"text": w, "isHighlighted": w == word} for w in words],
                    "fontSizePx": 44,
                }
            ],
            "yPct": 88.0,
            "anchor": "bottom",
            "groupStartMs": 0,
            "groupEndMs": 1800,
        }
        for i, word in enumerate(words)
    ]
    core, calls = _mock_core_with_layer(cues[0], png_b64)

    window = MainWindow(core_client=core)
    qtbot.addWidget(window)
    from app.models.captions import VideoMetadata

    window.project.video = VideoMetadata(path="/tmp/nope.mp4", width=1080, height=1920)
    window.project.segments = [
        CaptionSegment(start_ms=0, end_ms=1800, text=" ".join(words))
    ]
    window._preview_cues = cues
    window._layout_timer.stop()

    window._sync_caption_layer(cues[0])
    # Never more than a few ffmpeg pairs at once.
    assert len(window._layer_pending) <= 3

    def rendered():
        return {c[1]["timestampMs"] for c in calls if c[0] == "generatePreviewFrame"}

    qtbot.waitUntil(lambda: len(window._layer_cache) == len(cues), timeout=5000)
    # Every window rendered, each exactly once.
    frame_calls = [c for c in calls if c[0] == "generatePreviewFrame"]
    assert len(frame_calls) == len(cues)
    assert len(rendered()) == len(cues)

    # Coming back to a window in the block costs nothing.
    window._sync_caption_layer(cues[3])
    assert window.overlay.caption_layer is not None
    assert len([c for c in calls if c[0] == "generatePreviewFrame"]) == len(cues)
    window.close()


def test_export_format_drives_layout_layer_and_render(qtbot):
    """One canvas for the preview and the burn, chosen in the editor."""
    from PySide6.QtCore import QObject, Signal

    calls: list[tuple[str, dict]] = []

    class MockCore(QObject):
        progress = Signal(str, str, float)
        proc = None

        def call(self, method, params):
            from concurrent.futures import Future

            calls.append((method, params))
            f: Future = Future()
            f.set_result({"cues": [], "frameWidth": 1920, "frameHeight": 3414})
            return f

        def close(self):
            pass

    window = MainWindow(core_client=MockCore())
    qtbot.addWidget(window)
    from app.models.captions import VideoMetadata

    window.project.video = VideoMetadata(path="/tmp/nope.mp4", width=1920, height=1080)
    window.project.segments = [CaptionSegment(start_ms=0, end_ms=2000, text="Ja")]

    index = window.format_combo.findData("9:16")
    assert index >= 0
    window.format_combo.setCurrentIndex(index)
    window._layout_timer.stop()
    window._request_preview_layout()

    layout_calls = [c for c in calls if c[0] == "previewLayout"]
    assert layout_calls[-1][1]["exportFormat"] == "9:16"
    # The renderer's answer decides the canvas the editor draws.
    qtbot.waitUntil(lambda: window._canvas_size is not None, timeout=2000)
    assert window._canvas_size == (1920, 3414)
    assert window.player.canvas.export_canvas_size == (1920, 3414)

    # And the layer for a cue is rendered on that same canvas.
    window._request_caption_layer({"startMs": 0, "endMs": 2000})
    frame_calls = [c for c in calls if c[0] == "generatePreviewFrame"]
    assert frame_calls[-1][1]["exportFormat"] == "9:16"
    window.close()
